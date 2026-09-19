import tempfile
import unittest

from storage import Database


class StorageTests(unittest.TestCase):
    def test_transaction_rollback_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = d + "/db.sqlite"
            store = Database(path)
            with store.game("sid") as (db, state):
                state.update(revision=1, history=[["q", "yes"]])
                store.save(db, "sid", state)
            with self.assertRaises(RuntimeError):
                with store.game("sid") as (db, state):
                    state["revision"] = 2
                    store.save(db, "sid", state)
                    raise RuntimeError("rollback")
            self.assertEqual(Database(path).read("sid")["revision"], 1)
            self.assertTrue(store.allow("hashed-route", 1, 60))
            self.assertFalse(Database(path).allow("hashed-route", 1, 60))
