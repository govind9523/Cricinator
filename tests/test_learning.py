import tempfile
import unittest

from engine import Engine
from scripts.train_feedback import export_model, review
from storage import Database


class LearningTests(unittest.TestCase):
    def test_review_is_required_before_learning_export(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Database(folder + "/db")
            game = {
                "game_id": "g",
                "model_version": "version1",
                "history": [["country:India", "no"]],
            }
            with store.connect() as db:
                store.queue(db, game, "a")
            self.assertEqual(export_model(store, {"version1"})["counts"], [])
            review(store, "g", "approved")
            with self.assertRaises(ValueError):
                review(store, "g", "approved")
            model = export_model(store, {"version1"})
            self.assertEqual(model["reviewed_games"], 1)
            counts = {
                (r["player"], r["question"], r["answer"]): r["count"] for r in model["counts"]
            }
            players = [
                dict(id="a", name="A", country="India"),
                dict(id="b", name="B", country="England"),
            ]
            base = Engine(players)
            learned = Engine(players, counts)
            q = base.by_id["country:India"]
            self.assertGreater(
                learned.likelihood(players[0], q, "no"), base.likelihood(players[0], q, "no")
            )
            self.assertEqual(export_model(store, {"other"})["reviewed_games"], 0)


if __name__ == "__main__":
    unittest.main()
