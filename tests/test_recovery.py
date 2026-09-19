import tempfile
import unittest

from app import create_app


class RecoveryTests(unittest.TestCase):
    def test_retired_round_can_restart_without_cookie_clearing(self):
        with tempfile.TemporaryDirectory() as folder:
            players = [
                {"id": "a", "name": "A", "country": "India", "role": "Batter"},
                {"id": "b", "name": "B", "country": "England", "role": "Bowler"},
            ]
            app = create_app(
                {
                    "TESTING": True,
                    "SECRET_KEY": "test-only",
                    "DATABASE": folder + "/db",
                    "DATABASE_URL": None,
                    "RATE_LIMIT_ENABLED": False,
                    "ROSTERS": {"classic": players},
                }
            )
            client = app.test_client()
            headers = {"X-Cricinator": "1"}
            state = client.post("/api/start", json={}, headers=headers).get_json()
            with client.session_transaction() as cookie:
                sid = cookie["sid"]
            store = app.extensions["store"]
            with store.game(sid) as (db, round_state):
                round_state["model_version"] = "old-model"
                store.save(db, sid, round_state)
            recovered = client.get("/api/state")
            self.assertEqual(recovered.status_code, 200)
            self.assertEqual(recovered.get_json()["revision"], state["revision"])
            restarted = client.post(
                "/api/start", json={"revision": state["revision"]}, headers=headers
            )
            self.assertEqual(restarted.status_code, 200)


if __name__ == "__main__":
    unittest.main()
