import tempfile
import unittest
from pathlib import Path

from engine import Engine, HybridEngine, Store


class GameTests(unittest.TestCase):
    def setUp(self):
        self.players = [
            dict(id="a", name="A", country="India", batting="Right", born=1980),
            dict(id="b", name="B", country="Australia", batting="Left", born=1990),
            dict(id="c", name="C", country="India", batting="Left", born=2000),
        ]
        self.engine = Engine(self.players)

    def test_truthful_game_and_unknown(self):
        history = []
        initial = self.engine.rank(history)
        q = self.engine.next_question(history)
        self.assertEqual(initial, self.engine.rank([(q["id"], "unknown")]))
        for _ in range(10):
            q = self.engine.next_question(history)
            if not q:
                break
            history.append((q["id"], "yes" if self.engine.truth(self.players[1], q) else "no"))
        self.assertEqual(self.engine.rank(history)[0][0]["id"], "b")
        self.assertTrue(all(p > 0 for _, p in self.engine.rank(history)))

    def test_learning_persists_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "learn.db"
            store = Store(path)
            self.assertTrue(store.record("session", "b", [("batting:Left", "yes")]))
            self.assertFalse(store.record("session", "b", [("batting:Left", "yes")]))
            self.assertEqual(Store(path).counts()[("b", "batting:Left", "yes")], 1)

    def test_hybrid_engine_uses_legacy_fallback_when_confidence_is_weak(self):
        players = [
            dict(id="a", name="A", country="India", batting="Right", born=1980),
            dict(id="b", name="B", country="India", batting="Right", born=1980),
            dict(id="c", name="C", country="Australia", batting="Left", born=1990),
            dict(id="d", name="D", country="England", batting="Left", born=2000),
        ]
        hybrid = HybridEngine(players)
        q = hybrid.next_question([("country:India", "yes")])
        details = hybrid.diagnostics([("country:India", "yes")])
        self.assertEqual(q["engine_path"], "legacy_fallback")
        self.assertEqual(details["engine_path"], "legacy_fallback")
        self.assertIn("low confidence", details["fallback_reason"])
        self.assertLess(details["confidence"], 0.9)


if __name__ == "__main__":
    unittest.main()
