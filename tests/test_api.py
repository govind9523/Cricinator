import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import create_app


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = dict(
            TESTING=True,
            SECRET_KEY="test-only",
            DATABASE=self.tmp.name + "/db.sqlite",
            DATABASE_URL=None,
            RATE_LIMIT_ENABLED=False,
            ROSTERS={
                "classic": json.loads(
                    (Path(__file__).resolve().parents[1] / "data/players.json").read_text()
                )["players"]
            },
        )
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.headers = {"X-Cricinator": "1"}

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, data=None, key=None, client=None):
        return (client or self.client).post(
            "/api/" + path,
            json=data or {},
            headers={**self.headers, **({"Idempotency-Key": key} if key else {})},
        )

    def test_validation_and_revision_replay(self):
        self.assertEqual(self.client.post("/api/start", json={}).status_code, 403)
        self.assertEqual(
            self.client.post("/api/start", json=[], headers=self.headers).status_code, 400
        )
        self.assertEqual(
            self.client.post(
                "/api/start", json={}, headers={**self.headers, "Origin": "https://evil.test"}
            ).status_code,
            403,
        )
        state = self.post("start", key="start").get_json()
        self.assertEqual(state["engine_path"], "bayesian_ai")
        self.assertIn("confidence", state)
        self.assertEqual(self.post("start", key="start").get_json(), state)
        payload = dict(revision=state["revision"], question=state["question"]["id"], answer="yes")
        self.assertEqual(self.post("answer", {**payload, "answer": []}).status_code, 400)
        next_state = self.post("answer", payload, "answer").get_json()
        self.assertEqual(self.post("answer", payload, "answer").get_json(), next_state)
        self.assertEqual(self.post("answer", payload).status_code, 409)
        self.assertEqual(
            self.post("answer", {**payload, "answer": "no"}, "answer").status_code, 409
        )
        with self.client.session_transaction() as cookie:
            self.assertEqual(set(cookie), {"sid"})
        restarted = create_app(self.config).test_client()
        restarted.set_cookie("session", self.client.get_cookie("session").value)
        self.assertEqual(restarted.get("/api/state").get_json(), next_state)
        undone = self.post("undo", {"revision": next_state["revision"]}).get_json()
        self.assertEqual(undone["count"], 0)
        self.assertEqual(self.post("undo", {"revision": next_state["revision"]}).status_code, 409)

    def test_feedback_is_once_pending_and_completed_is_immutable(self):
        state = self.post("start").get_json()
        engine = self.app.extensions["engine"]
        player = engine.players[0]
        while state["phase"] == "question":
            q = engine.by_id[state["question"]["id"]]
            truth = engine.truth(player, q)
            answer = "unknown" if truth is None else "yes" if truth else "no"
            response = self.post(
                "answer", dict(revision=state["revision"], question=q["id"], answer=answer)
            )
            self.assertEqual(response.status_code, 200)
            state = response.get_json()
        self.assertEqual(state["phase"], "guess")
        payload = dict(revision=state["revision"], player=player["id"])
        complete = self.post("feedback", payload, "feedback").get_json()
        self.assertEqual(complete["phase"], "complete")
        self.assertEqual(self.post("feedback", payload, "feedback").get_json(), complete)
        for action in ("undo", "reject", "feedback", "answer"):
            self.assertEqual(
                self.post(
                    action, dict(revision=complete["revision"], player=player["id"])
                ).status_code,
                409,
            )
        with self.app.extensions["store"].connect() as db:
            rows = db.execute("SELECT status FROM feedback").fetchall()
            self.assertEqual(rows, [("pending",)])
        self.assertEqual(engine.counts, {})

    def test_simultaneous_answers_only_apply_once(self):
        state = self.post("start").get_json()
        cookie = self.client.get_cookie("session").value
        payload = dict(
            revision=state["revision"], question=state["question"]["id"], answer="unknown"
        )

        def submit(_):
            client = self.app.test_client()
            client.set_cookie("session", cookie)
            return self.post("answer", payload, client=client).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(submit, range(2))), [200, 409])
        self.assertEqual(self.client.get("/api/state").get_json()["count"], 1)

    def test_rejection_limit_and_health(self):
        self.post("start")
        with self.client.session_transaction() as cookie:
            sid = cookie["sid"]
        store = self.app.extensions["store"]
        with store.game(sid) as (db, state):
            state["history"] = [
                [q["id"], "unknown"] for q in self.app.extensions["engine"].questions[:20]
            ]
            store.save(db, sid, state)
        state = self.client.get("/api/state").get_json()
        for _ in range(3):
            self.assertEqual(state["phase"], "guess")
            state = self.post("reject", {"revision": state["revision"]}).get_json()
        self.assertEqual(state["phase"], "miss")
        self.assertEqual(self.post("reject", {"revision": state["revision"]}).status_code, 409)
        self.assertEqual(self.client.get("/api/state").get_json()["phase"], "miss")
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/readyz").status_code, 200)

    def test_research_report_is_backed_by_local_evaluation_files(self):
        report = self.client.get("/api/research").get_json()
        self.assertEqual(report["paper"]["doi"], "10.1109/DISCOVER66922.2025.11259006")
        self.assertIn("Bayesian inference", report["implemented_methods"])
        self.assertEqual(report["classic"]["players"], 138)
        self.assertEqual(report["classic"]["clean_first_guess"], "138/138")
        self.assertEqual(report["classic"]["noisy_first_guess"], "250/276")
        self.assertEqual(report["world"]["records"], 12559)
        self.assertEqual(report["world"]["sample_accuracy"], "23.33%")
        self.assertGreater(report["world"]["ambiguous_records"], 7000)
        self.assertFalse(report["claims"]["independent_human_accuracy"])
        self.assertFalse(report["claims"]["deployed_reinforcement_policy"])

    def test_api_reports_legacy_fallback_when_candidates_are_ambiguous(self):
        app = create_app(
            {
                **self.config,
                "ROSTERS": {
                    "classic": [
                        dict(id="a", name="A", country="India", batting="Right", born=1980),
                        dict(id="b", name="B", country="India", batting="Right", born=1980),
                        dict(id="c", name="C", country="Australia", batting="Left", born=1990),
                        dict(id="d", name="D", country="England", batting="Left", born=2000),
                    ]
                },
            }
        )
        client = app.test_client()
        headers = self.headers
        state = client.post("/api/start", json={"mode": "classic"}, headers=headers).get_json()
        answer = client.post(
            "/api/answer",
            json={
                "revision": state["revision"],
                "question": "country:India",
                "answer": "yes",
            },
            headers=headers,
        ).get_json()
        self.assertEqual(answer["engine_path"], "legacy_fallback")
        self.assertIn("low confidence", answer["fallback_reason"])

    def test_production_requires_stable_secret(self):
        with self.assertRaises(RuntimeError):
            create_app({**self.config, "PRODUCTION": True, "SECRET_KEY": None})


if __name__ == "__main__":
    unittest.main()
