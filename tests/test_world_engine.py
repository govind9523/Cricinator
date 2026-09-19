import unittest

from engine import Engine


class WorldEngineTests(unittest.TestCase):
    def test_multiple_international_teams_and_historical_eras(self):
        players = [
            {
                "id": "a",
                "name": "A",
                "countries": ["England", "Ireland"],
                "born": 1870,
                "debut": 1890,
            },
            {"id": "b", "name": "B", "countries": ["India"], "born": 1980, "debut": 2000},
            {"id": "c", "name": "C", "countries": ["Ireland"], "born": 2000, "debut": 2020},
        ]
        engine = Engine(players)
        self.assertTrue(engine.truth(players[0], engine.by_id["country:Ireland"]))
        self.assertTrue(engine.truth(players[0], engine.by_id["country:England"]))
        self.assertTrue(any(q["field"] == "born" and q["value"] < 1965 for q in engine.questions))

    def test_missing_format_is_not_a_negative_fact(self):
        q = {"field": "formats", "op": "contains", "value": "Test"}
        self.assertIsNone(Engine.truth({"formats": ["T20I"]}, q))
        self.assertFalse(Engine.truth({"formats": ["T20I"], "formats_complete": True}, q))

    def test_vectorized_posterior_matches_scalar_likelihood(self):
        players = [
            {
                "id": str(i),
                "name": str(i),
                "country": "India" if i % 2 else "England",
                "born": 1970 + i,
            }
            for i in range(12)
        ]
        engine = Engine(players)
        history = [("country:India", "probably"), ("born:1975", "no")]
        weights = {
            p["id"]: engine.likelihood(p, engine.by_id[history[0][0]], history[0][1])
            * engine.likelihood(p, engine.by_id[history[1][0]], history[1][1])
            for p in players
        }
        total = sum(weights.values())
        for player, posterior in engine.rank(history):
            self.assertAlmostEqual(posterior, weights[player["id"]] / total, places=7)


if __name__ == "__main__":
    unittest.main()


class StatsTests(unittest.TestCase):
    def test_stats_missing_is_unknown_and_zero_is_known(self):
        q = {"op": "stats", "field": "stats", "format": "Test", "metric": "wickets", "value": 25}
        self.assertIsNone(Engine.truth({"stats": {}}, q))
        self.assertFalse(Engine.truth({"stats": {"Test": {"wickets": 0}}}, q))
        self.assertTrue(Engine.truth({"stats": {"Test": {"wickets": 25}}}, q))
