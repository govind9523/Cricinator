import json
import unittest
from pathlib import Path

from engine import Engine


class DataTests(unittest.TestCase):
    def test_roster_integrity_and_distinguishability(self):
        data = json.loads((Path(__file__).resolve().parents[1] / "data/players.json").read_text())
        players = data["players"]
        self.assertGreaterEqual(len(players), 100)
        self.assertEqual(data["errors"], [])
        self.assertEqual(len(players), len({p["id"] for p in players}))
        engine = Engine(players)
        signatures = {}
        for player in players:
            self.assertTrue(player["source"].startswith("https://en.wikipedia.org/wiki/"))
            self.assertTrue(1800 < player["born"] < 2020)
            signature = tuple(engine.truth(player, q) for q in engine.questions)
            self.assertNotIn(
                signature,
                signatures,
                f"Indistinguishable: {player['name']} and {signatures.get(signature)}",
            )
            signatures[signature] = player["name"]

    def test_learning_changes_likelihood_but_remains_bounded(self):
        p = [
            dict(id="a", name="A", country="India"),
            dict(id="b", name="B", country="Australia"),
        ]
        baseline = Engine(p)
        q = baseline.by_id["country:India"]
        learned = Engine(p, {("a", q["id"], "no"): 100000})
        self.assertGreater(learned.likelihood(p[0], q, "no"), baseline.likelihood(p[0], q, "no"))
        self.assertLess(learned.likelihood(p[0], q, "no"), 0.35)
        self.assertAlmostEqual(
            sum(learned.likelihood(p[0], q, a) for a in ["yes", "probably", "probably_not", "no"]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
