"""Persistent Flask API with server-side rounds and transactional revision checks."""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix

from engine import ANSWERS, ENGINE_VERSION, HybridEngine
from roster import load_rosters
from storage import Database

ROOT = Path(__file__).resolve().parent


class APIError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status


def create_app(config=None):
    app = Flask(__name__, static_folder="web", static_url_path="/static")
    production = (
        os.environ.get("APP_ENV") == "production"
        or os.environ.get("FLASK_ENV") == "production"
        or bool(os.environ.get("RENDER"))
    )
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        PRODUCTION=production,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        MAX_CONTENT_LENGTH=4096,
        DATABASE=os.environ.get("DATABASE_PATH", str(ROOT / "instance/world.sqlite")),
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        DB_TIMEOUT=5,
        TRUST_PROXY_HOPS=int(os.environ.get("TRUST_PROXY_HOPS", "0")),
        RATE_LIMIT_ENABLED=True,
    )
    if config:
        app.config.update(config)
    if app.config["PRODUCTION"] and (
        not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32
    ):
        raise RuntimeError(
            "Production requires a stable SECRET_KEY of at least 32 characters on every host."
        )
    if app.config["PRODUCTION"] and not (app.config["DATABASE_URL"] or "").startswith(
        ("postgres://", "postgresql://")
    ):
        raise RuntimeError("Production requires a persistent PostgreSQL DATABASE_URL.")
    app.config["SECRET_KEY"] = app.config["SECRET_KEY"] or secrets.token_hex(32)
    hops = app.config["TRUST_PROXY_HOPS"]
    if hops:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=0)
    raw = (ROOT / "data/players.json").read_bytes()
    players = json.loads(raw)["players"]
    rosters = app.config.get("ROSTERS") or load_rosters(ROOT)
    counts = {}
    model_path = app.config.get("MODEL_PATH") or os.environ.get("MODEL_PATH")
    if model_path:
        model = json.loads(Path(model_path).read_text())
        if model.get("schema") != 1:
            raise RuntimeError("Unsupported model schema")
        counts = {
            (row["player"], row["question"], row["answer"]): row["count"] for row in model["counts"]
        }
    engines = {mode: HybridEngine(items, counts) for mode, items in rosters.items()}
    learned = sorted([list(key) + [value] for key, value in counts.items()])
    versions = {
        mode: ENGINE_VERSION
        + "-"
        + hashlib.sha256(json.dumps([items, learned], sort_keys=True).encode()).hexdigest()[:16]
        for mode, items in rosters.items()
    }
    engine = engines["classic"]
    model_version = versions["classic"]
    store = Database(app.config["DATABASE_URL"] or app.config["DATABASE"], app.config["DB_TIMEOUT"])
    app.extensions.update(
        engine=engine, engines=engines, rosters=rosters, store=store, model_version=model_version
    )

    @app.before_request
    def boundary():
        if not request.path.startswith("/api/"):
            return
        if request.method == "POST":
            if not request.is_json:
                raise APIError("Send JSON.", 415)
            if request.headers.get("X-Cricinator") != "1":
                raise APIError("Request verification failed.", 403)
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                raise APIError("Cross-site request denied.", 403)
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
                raise APIError("Origin mismatch.", 403)
            if not isinstance(request.get_json(), dict):
                raise APIError("Expected a JSON object.", 400)
        if app.config["RATE_LIMIT_ENABLED"]:
            group = (
                "start"
                if request.path == "/api/start"
                else "write"
                if request.method == "POST"
                else "read"
            )
            identity = hmac.new(
                str(app.config["SECRET_KEY"]).encode(),
                (request.remote_addr or "unknown").encode(),
                hashlib.sha256,
            ).hexdigest()
            if not store.allow(
                identity + ":" + group, {"start": 12, "write": 120, "read": 180}[group], 60
            ):
                raise APIError("Too many requests. Try again in one minute.", 429)

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if response.status_code == 429:
            response.headers["Retry-After"] = "60"
        return response

    @app.errorhandler(APIError)
    def api_error(error):
        return jsonify(error=error.message), error.status

    @app.errorhandler(400)
    @app.errorhandler(413)
    @app.errorhandler(415)
    def invalid(error):
        return jsonify(
            error="Request too large." if error.code == 413 else "Invalid JSON request."
        ), error.code

    def unavailable(error):
        app.logger.error("Database unavailable: %s", type(error).__name__)
        return jsonify(error="Storage temporarily unavailable. Retry later."), 503

    app.register_error_handler(sqlite3.Error, unavailable)
    try:
        import psycopg

        app.register_error_handler(psycopg.Error, unavailable)
    except ImportError:
        pass

    @app.get("/")
    def home():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/healthz")
    def health():
        return jsonify(status="ok")

    @app.get("/readyz")
    def ready():
        if not store.ready():
            return jsonify(status="unavailable"), 503
        return jsonify(status="ready", players=len(players), model_version=model_version)

    @app.get("/api/roster")
    def roster():
        mode = request.args.get("mode", "classic")
        if mode not in rosters:
            raise APIError("Unknown game mode.", 400)
        return jsonify(
            players=[
                {
                    "id": p["id"],
                    "name": p["name"],
                    "country": p.get("country", ""),
                    "role": p.get("role") or "International cricketer",
                }
                for p in rosters[mode]
            ]
        )

    catalog_path = ROOT / "data/catalog.json"
    catalog = (
        json.loads(catalog_path.read_text())
        if catalog_path.exists()
        else {"players": [], "retrieved": None}
    )
    coverage_path = ROOT / "data/coverage.json"
    coverage = json.loads(coverage_path.read_text()) if coverage_path.exists() else {}
    playable_sources = {p.get("source") for p in players}

    @app.get("/api/coverage")
    def coverage_info():
        return jsonify(
            catalog_count=len(catalog["players"]),
            playable_count=len(players),
            world_count=len(rosters.get("world", [])),
            countries=coverage.get("countries", []),
            updated=catalog.get("retrieved"),
            limitations=coverage.get("limitations", []),
            unlinked_records=coverage.get("unlinked_profiles", 0),
            complete=False,
        )

    evaluation = json.loads((ROOT / "data/evaluation.json").read_text())
    world_evaluation = json.loads((ROOT / "data/world-evaluation.json").read_text())

    def pct(value):
        return f"{value * 100:.2f}%"

    @app.get("/api/research")
    def research_report():
        clean = evaluation["clean"]
        noisy = evaluation["noisy"]
        return jsonify(
            paper={
                "title": "Cricinator: An AI-Driven Cricketer Guessing Game Leveraging Reinforcement Learning",
                "venue": "IEEE DISCOVER 2025",
                "doi": "10.1109/DISCOVER66922.2025.11259006",
                "url": "https://ieeexplore.ieee.org/document/11259006/",
            },
            implemented_methods=[
                "Bayesian inference",
                "entropy-based question selection",
                "low-confidence legacy fallback",
                "adaptive five-answer Q&A",
                "reviewed feedback learning queue",
                "reproducible synthetic evaluation",
            ],
            pipeline=[
                "source-attributed player facts",
                "feature matrix",
                "posterior probability update",
                "information-gain next question",
                "legacy fallback when confidence is weak",
                "guess or feedback review",
            ],
            classic={
                "players": evaluation["players"],
                "clean_first_guess": f'{clean["correct_first_guess"]}/{clean["games"]}',
                "clean_accuracy": pct(clean["accuracy"]),
                "mean_questions": clean["mean_questions"],
                "noisy_first_guess": f'{noisy["correct_first_guess"]}/{noisy["games"]}',
                "noisy_accuracy": pct(noisy["accuracy"]),
                "noise_model": "15% unknown answers; otherwise 5% flipped answers; seed 42",
            },
            world={
                "records": world_evaluation["records"],
                "questions": world_evaluation["questions"],
                "sample_first_guess": f'{world_evaluation["correct_first_guesses"]}/{world_evaluation["sample_games"]}',
                "sample_accuracy": pct(world_evaluation["sample_accuracy"]),
                "mean_questions": world_evaluation["mean_questions"],
                "p95_question_ms": world_evaluation["p95_question_ms"],
                "distinct_feature_signatures": world_evaluation["distinct_feature_signatures"],
                "ambiguous_records": world_evaluation["ambiguous_records"],
                "catalog_source_identities": coverage.get("catalog_players", len(catalog["players"])),
                "parsed_source_pages": coverage.get("parsed_pages", 0),
            },
            claims={
                "independent_human_accuracy": False,
                "deployed_reinforcement_policy": False,
                "world_records_are_unique_people": False,
                "production_database_verified_here": False,
            },
        )

    @app.get("/api/catalog")
    def catalog_search():
        query = request.args.get("q", "").strip().casefold()
        if len(query) > 100:
            raise APIError("Search is too long.", 400)
        try:
            limit = int(request.args.get("limit", 60))
            offset = int(request.args.get("offset", 0))
        except ValueError:
            raise APIError("Invalid pagination.", 400)
        if not 1 <= limit <= 100 or offset < 0:
            raise APIError("Invalid pagination.", 400)
        matched = [
            p
            for p in catalog["players"]
            if query in (p["name"] + " " + " ".join(p["countries"])).casefold()
        ]
        return jsonify(
            total=len(matched),
            players=[
                dict(p, playable=p.get("profile_url") in playable_sources)
                for p in matched[offset : offset + limit]
            ],
        )

    def view(state):
        if not state.get("game_id"):
            return {"phase": "home"}
        mode = state.get("mode", "classic")
        engine = engines.get(mode)
        if state["model_version"] != versions.get(mode):
            raise APIError("This model version has retired. Start a new round.")
        players = rosters[mode]
        index = {p["id"]: p for p in players}
        history, rejected = state["history"], state["rejected"]
        diagnostics = engine.diagnostics(history, rejected)
        result = dict(
            count=len(history),
            limit=20,
            roster_size=len(players),
            can_undo=bool(history) and not state.get("complete"),
            revision=state["revision"],
            game_id=state["game_id"],
            model_version=state["model_version"],
            mode=mode,
            **diagnostics,
        )
        if state.get("complete"):
            return dict(
                result, phase="complete", player=index[state["complete"]], feedback_status="pending"
            )
        if len(rejected) >= 3:
            return dict(
                result,
                phase="miss",
                message="You beat me this round. Choose the player below to leave feedback.",
            )
        ranked = engine.rank(history, rejected)
        if not ranked:
            return dict(result, phase="miss", message="No supported candidates remain.")
        candidate, prob = ranked[0]
        q = engine.next_question(history, rejected)
        if not q or len(history) >= 20 or (len(history) >= 4 and prob >= 0.93):
            return dict(result, phase="guess", player=candidate, uncertain=prob < 0.93)
        return dict(result, phase="question", question={"id": q["id"], "text": q["text"]})

    @app.get("/api/state")
    def resume():
        state = store.read(session["sid"]) if session.get("sid") else {}
        if state.get("game_id") and state.get("model_version") != versions.get(
            state.get("mode", "classic")
        ):
            return jsonify(
                phase="home",
                revision=state["revision"],
                game_id=state["game_id"],
                notice="The roster has been updated. Start a new round.",
            )
        return jsonify(view(state))

    def mutate(action):
        data = request.get_json()
        if not session.get("sid"):
            if action != "start":
                raise APIError("Start a game first.")
            session["sid"] = secrets.token_urlsafe(32)
        key = request.headers.get("Idempotency-Key")
        if key is not None and (not key or len(key) > 128):
            raise APIError("Idempotency-Key must contain 1 to 128 characters.", 400)
        fingerprint = hashlib.sha256(
            (action + json.dumps(data, sort_keys=True)).encode()
        ).hexdigest()
        with store.game(session["sid"]) as (db, state):
            receipts = state.get("receipts", {})
            if key in receipts:
                old = receipts[key]
                if old["fingerprint"] != fingerprint:
                    raise APIError("Idempotency-Key was already used for another request.")
                return jsonify(old["response"])
            if state.get("game_id"):
                if type(data.get("revision")) is not int or data["revision"] != state["revision"]:
                    raise APIError("Stale or missing revision. Resume your game.")
            elif action != "start":
                raise APIError("This game expired. Start a new round.")
            revision = state.get("revision", 0) + 1
            if action == "start":
                mode = data.get("mode", "classic")
                if not isinstance(mode, str) or mode not in rosters:
                    raise APIError("Choose an available mode: " + ", ".join(rosters), 400)
                state = dict(
                    game_id=secrets.token_hex(16),
                    model_version=versions[mode],
                    mode=mode,
                    history=[],
                    rejected=[],
                )
            else:
                current = view(state)
                if state.get("complete"):
                    raise APIError("This round is complete. Start a new round.")
                if action == "answer":
                    if not isinstance(data.get("answer"), str) or data["answer"] not in ANSWERS:
                        raise APIError("Choose one of the five answers.", 400)
                    if (
                        current["phase"] != "question"
                        or data.get("question") != current["question"]["id"]
                    ):
                        raise APIError("This question has changed. Resume your game.")
                    state["history"].append([data["question"], data["answer"]])
                elif action == "undo":
                    if not state["history"]:
                        raise APIError("There is no answer to undo.")
                    state["history"].pop()
                    state["rejected"] = []
                elif action == "reject":
                    if current["phase"] != "guess" or len(state["rejected"]) >= 3:
                        raise APIError("There is no guess to reject.")
                    state["rejected"].append(current["player"]["id"])
                elif action == "feedback":
                    player = data.get("player")
                    if not isinstance(player, str) or player not in {
                        p["id"] for p in rosters[state.get("mode", "classic")]
                    }:
                        raise APIError("Choose a player from the roster.", 400)
                    if current["phase"] not in ("guess", "miss") or len(state["history"]) < 3:
                        raise APIError("Finish a guessing round before giving feedback.")
                    store.queue(db, state, player)
                    state["complete"] = player
            state["revision"] = revision
            response = view(state)
            if key:
                receipts[key] = {"fingerprint": fingerprint, "response": response}
            state["receipts"] = dict(list(receipts.items())[-32:])
            store.save(db, session["sid"], state)
            return jsonify(response)

    for action in ("start", "answer", "undo", "reject", "feedback"):
        app.add_url_rule(
            "/api/" + action, action, lambda action=action: mutate(action), methods=["POST"]
        )
    return app


app = create_app()
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "7861")), debug=False)
