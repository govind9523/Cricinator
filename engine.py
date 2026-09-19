"""Bayesian identification with information-gain questions and bounded learning."""

import math
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

ENGINE_VERSION = "world-bayes-2"

ANSWERS = ("yes", "probably", "unknown", "probably_not", "no")


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS games (id TEXT PRIMARY KEY, player TEXT NOT NULL, created REAL NOT NULL); CREATE TABLE IF NOT EXISTS answers (game TEXT, question TEXT, answer TEXT, PRIMARY KEY(game,question), FOREIGN KEY(game) REFERENCES games(id));"
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, game, player, history):
        with self.connect() as db:
            added = db.execute(
                "INSERT OR IGNORE INTO games VALUES (?,?,?)",
                (game, player, time.time()),
            ).rowcount
            if not added:
                return False
            db.executemany("INSERT INTO answers VALUES (?,?,?)", [(game, q, a) for q, a in history])
        return True

    def counts(self):
        with self.connect() as db:
            return {
                (p, q, a): n
                for p, q, a, n in db.execute(
                    "SELECT player,question,answer,COUNT(*) FROM answers JOIN games ON games.id=answers.game GROUP BY player,question,answer"
                )
            }

    def total(self):
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM games").fetchone()[0]


class Engine:
    """Immutable question matrix; create once per published roster/model version."""

    def __init__(self, players, counts=None):
        if not players or len({p["id"] for p in players}) != len(players):
            raise ValueError("A roster needs players with unique IDs")
        self.players = players
        self.counts = counts or {}
        self.player_index = {p["id"]: i for i, p in enumerate(players)}
        self.questions = []
        templates = {
            "country": "Has your player represented {value} internationally?",
            "batting": "Does your player bat {value}-handed?",
            "role": "Is your player primarily {value}?",
            "teams": "Has your player played for {value}?",
            "gender": "Does your player play in {value}'s international cricket?",
            "formats": "Has your player appeared in {value} cricket?",
        }
        for field, template in templates.items():
            values = set()
            for player in players:
                if field == "country":
                    value = player.get("countries") or [player.get("country")]
                else:
                    value = player.get(field)
                values.update(v for v in (value if isinstance(value, list) else [value]) if v)
            for value in sorted(values):
                if field == "gender" and value != "women":
                    continue
                label = value
                if field == "role":
                    label = ("an " if value == "All-rounder" else "a ") + value.lower()
                elif field == "batting":
                    label = value.lower()
                elif field == "formats":
                    label = {"ODI": "One Day International", "T20I": "Twenty20 International"}.get(
                        value, value
                    )
                self.questions.append(
                    {
                        "id": field + ":" + value,
                        "field": field,
                        "value": value,
                        "op": "contains" if field in ("teams", "formats") else "eq",
                        "text": template.format(value=label),
                    }
                )
        for field in ("born", "debut", "last_year"):
            years = [p[field] for p in players if isinstance(p.get(field), int)]
            if not years:
                continue
            for year in range((min(years) // 5) * 5 + 5, max(years) + 5, 5):
                text = {
                    "born": f"Was your player born before {year}?",
                    "debut": f"Did your player make their international debut before {year}?",
                    "last_year": f"Did your player appear in international cricket in {year} or later?",
                }[field]
                self.questions.append(
                    {
                        "id": f"{field}:{year}",
                        "field": field,
                        "value": year,
                        "op": "gte" if field == "last_year" else "lt",
                        "text": text,
                    }
                )
        for format_name in ("Test", "ODI", "T20I"):
            for metric, thresholds in (
                ("matches", (10, 50, 100, 200)),
                ("runs", (500, 2000, 5000, 10000)),
                ("wickets", (25, 100, 250, 400)),
            ):
                for threshold in thresholds:
                    phrase = (
                        f"played at least {threshold} matches"
                        if metric == "matches"
                        else f"scored at least {threshold:,} runs"
                        if metric == "runs"
                        else f"taken at least {threshold} wickets"
                    )
                    self.questions.append(
                        {
                            "id": f"stats:{format_name}:{metric}:{threshold}",
                            "field": "stats",
                            "format": format_name,
                            "metric": metric,
                            "value": threshold,
                            "op": "stats",
                            "text": f"Has your player {phrase} in {format_name} cricket?",
                        }
                    )
        for value, label in (
            ("left", "left-arm"),
            ("right", "right-arm"),
            ("fast", "pace"),
            ("spin", "spin"),
        ):
            self.questions.append(
                {
                    "id": "bowling:" + value,
                    "field": "bowling",
                    "value": value,
                    "op": "bowling",
                    "text": f"When bowling (even occasionally), does your player bowl {label}?",
                }
            )
        questions = []
        rows = []
        for q in self.questions:
            row = np.fromiter(
                (0 if (truth := self.truth(p, q)) is None else 1 if truth else -1 for p in players),
                dtype=np.int8,
                count=len(players),
            )
            # A question needs known positive and negative examples to be informative.
            if np.any(row == 1) and np.any(row == -1):
                questions.append(q)
                rows.append(row)
        self.questions = questions
        self.by_id = {q["id"]: q for q in questions}
        self.question_index = {q["id"]: i for i, q in enumerate(questions)}
        self.matrix = np.stack(rows) if rows else np.empty((0, len(players)), dtype=np.int8)
        self.yes = (self.matrix == 1).astype(np.float32)
        self.no = (self.matrix == -1).astype(np.float32)
        self.positive = np.array([0.86, 0.10, 0.025, 0.015], dtype=np.float64)
        self.answer_index = {a: i for i, a in enumerate(("yes", "probably", "probably_not", "no"))}
        self._adjustments = {}
        self._build_adjustments()

    @staticmethod
    def truth(player, q):
        field = q["field"]
        if field == "country":
            countries = player.get("countries") or (
                [player["country"]] if player.get("country") else None
            )
            return q["value"] in countries if countries else None
        if q["op"] == "stats":
            value = player.get("stats", {}).get(q["format"], {}).get(q["metric"])
            return value >= q["value"] if isinstance(value, (int, float)) else None
        value = player.get(field)
        if value is None or value == "":
            return None
        if q["op"] == "contains":
            if q["value"] in value:
                return True
            if field == "formats" and not player.get("formats_complete", False):
                return None
            return False
        if q["op"] == "lt":
            return value < q["value"]
        if q["op"] == "gte":
            return value >= q["value"]
        if q["op"] == "bowling":
            value = value.lower()
            if q["value"] == "fast":
                return "fast" in value or "medium" in value
            if q["value"] == "spin":
                return any(x in value for x in ("spin", "break", "orthodox"))
            return q["value"] in value
        return value == q["value"]

    def _base_distribution(self, truth):
        return (
            self.positive
            if truth == 1
            else self.positive[::-1]
            if truth == -1
            else np.full(4, 0.25)
        )

    def _build_adjustments(self):
        grouped = {}
        for (pid, qid, answer), number in self.counts.items():
            if (
                pid not in self.player_index
                or qid not in self.question_index
                or answer not in self.answer_index
            ):
                continue
            if not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0:
                raise ValueError("Invalid learned count")
            key = (self.question_index[qid], self.player_index[pid])
            grouped.setdefault(key, np.zeros(4))[self.answer_index[answer]] += number
        for (qi, pi), counts in grouped.items():
            total = float(counts.sum())
            scale = min(1, 20 / max(1, total))
            old = self._base_distribution(self.matrix[qi, pi])
            new = (40 * old + counts * scale) / (40 + total * scale)
            self._adjustments.setdefault(qi, []).append((pi, old, new))

    def likelihood(self, player, q, answer):
        if answer == "unknown":
            return 1.0
        qi = self.question_index[q["id"]]
        pi = self.player_index[player["id"]]
        ai = self.answer_index[answer]
        for idx, _, new in self._adjustments.get(qi, []):
            if idx == pi:
                return float(new[ai])
        return float(self._base_distribution(self.matrix[qi, pi])[ai])

    def posterior(self, history, rejected=()):
        scores = np.zeros(len(self.players), dtype=np.float64)
        for qid, answer in history:
            if answer not in ANSWERS or qid not in self.question_index:
                raise ValueError("Unknown question or answer")
            if answer == "unknown":
                continue
            qi = self.question_index[qid]
            ai = self.answer_index[answer]
            row = self.matrix[qi]
            likelihood = np.where(
                row == 1, self.positive[ai], np.where(row == -1, self.positive[3 - ai], 0.25)
            )
            for pi, _, new in self._adjustments.get(qi, []):
                likelihood[pi] = new[ai]
            scores += np.log(likelihood)
        for pid in rejected:
            if pid in self.player_index:
                scores[self.player_index[pid]] = -np.inf
        if not np.any(np.isfinite(scores)):
            return np.zeros(len(self.players))
        weights = np.exp(scores - np.max(scores))
        return weights / weights.sum()

    def rank(self, history, rejected=()):
        weights = self.posterior(history, rejected)
        return sorted(
            ((p, float(weights[i])) for i, p in enumerate(self.players) if weights[i] > 0),
            key=lambda item: (-item[1], item[0]["id"]),
        )

    def next_question(self, history, rejected=()):
        if not self.questions:
            return None
        weights = self.posterior(history, rejected)
        if not np.any(weights):
            return None
        positive = np.einsum("ij,j->i", self.yes, weights, dtype=np.float64, optimize=False)
        negative = np.einsum("ij,j->i", self.no, weights, dtype=np.float64, optimize=False)
        unknown = np.clip(1 - positive - negative, 0, 1)
        mixtures = (
            positive[:, None] * self.positive
            + negative[:, None] * self.positive[::-1]
            + unknown[:, None] * 0.25
        )
        conditional = (positive + negative) * (
            -np.sum(self.positive * np.log2(self.positive))
        ) + unknown * 2
        for qi, adjustments in self._adjustments.items():
            for pi, old, new in adjustments:
                mixtures[qi] += weights[pi] * (new - old)
                conditional[qi] += weights[pi] * (
                    -np.sum(new * np.log2(new)) + np.sum(old * np.log2(old))
                )
        gain = -np.sum(mixtures * np.log2(np.clip(mixtures, 1e-15, 1)), axis=1) - conditional
        asked = {qid for qid, _ in history}
        for i, q in enumerate(self.questions):
            if q["id"] in asked:
                gain[i] = -np.inf
            elif q["field"] == "teams":
                gain[i] *= 0.85
        best = int(np.argmax(gain))
        return self.questions[best] if gain[best] > 1e-6 else None


class HybridEngine:
    """Bayesian engine with a deterministic split fallback for ambiguous states."""

    def __init__(self, players, counts=None):
        self.ai = Engine(players, counts)
        self.players = self.ai.players
        self.questions = self.ai.questions
        self.by_id = self.ai.by_id

    def __getattr__(self, name):
        return getattr(self.ai, name)

    def rank(self, history, rejected=()):
        return self.ai.rank(history, rejected)

    def diagnostics(self, history, rejected=()):
        ranked = self.rank(history, rejected)
        confidence = ranked[0][1] if ranked else 0.0
        margin = confidence - ranked[1][1] if len(ranked) > 1 else confidence
        fallback = bool(history) and confidence < 0.72 and margin < 0.18
        return {
            "confidence": round(confidence, 4),
            "margin": round(margin, 4),
            "engine_path": "legacy_fallback" if fallback else "bayesian_ai",
            "fallback_reason": (
                "AI has low confidence and top candidates are close; using legacy splitter."
                if fallback
                else ""
            ),
        }

    def next_question(self, history, rejected=()):
        details = self.diagnostics(history, rejected)
        if details["engine_path"] == "legacy_fallback":
            question = self._legacy_question(history, rejected)
        else:
            question = self.ai.next_question(history, rejected)
        return dict(question, **details) if question else None

    def _legacy_question(self, history, rejected):
        asked = {qid for qid, _ in history}
        ranked = self.rank(history, rejected)[: min(24, len(self.players))]
        if not ranked:
            return None
        ids = [player["id"] for player, _ in ranked]
        idx = np.array([self.ai.player_index[pid] for pid in ids])
        weights = np.array([prob for _, prob in ranked], dtype=np.float64)
        weights /= weights.sum()
        best, best_score = None, -1.0
        for qi, question in enumerate(self.questions):
            if question["id"] in asked:
                continue
            row = self.ai.matrix[qi, idx]
            known = row != 0
            if not np.any(row == 1) or not np.any(row == -1):
                continue
            yes = float(weights[row == 1].sum())
            no = float(weights[row == -1].sum())
            known_weight = float(weights[known].sum())
            score = known_weight * (1 - abs(yes - no))
            if question["field"] == "teams":
                score *= 0.85
            if score > best_score:
                best, best_score = question, score
        return best if best_score > 0 else self.ai.next_question(history, rejected)
