import unittest

from roster import merge_rosters


class RosterTests(unittest.TestCase):
    def test_merges_source_identity_without_overwriting_known_countries(self):
        base = [
            {
                "id": "known",
                "name": "Known",
                "source": "https://en.wikipedia.org/wiki/Known",
                "country": "England",
                "born": 1980,
                "role": "Batter",
            }
        ]
        catalog = [
            {
                "id": "wiki123",
                "name": "Known",
                "profile_url": base[0]["source"],
                "countries": ["England", "Ireland"],
                "formats": ["ODI"],
                "gender": "men",
                "debut": 2000,
                "last_year": 2020,
                "sources": ["https://example.test/list"],
            }
        ]
        rosters = merge_rosters(base, catalog)
        self.assertEqual(len(rosters["world"]), 1)
        p = rosters["world"][0]
        self.assertEqual(p["countries"], ["England", "Ireland"])
        self.assertEqual(p["id"], "known")
        self.assertEqual(p["born"], 1980)

    def test_sparse_players_remain_unknown(self):
        catalog = [
            {
                "id": "world1",
                "name": "Other",
                "profile_url": None,
                "countries": ["Nepal"],
                "formats": ["T20I"],
                "gender": "men",
                "debut": None,
                "last_year": None,
                "sources": ["https://example.test/list"],
            }
        ]
        p = merge_rosters([], catalog)["world"][0]
        self.assertIsNone(p["role"])
        self.assertIsNone(p["born"])
        self.assertEqual(p["source"], "https://example.test/list")


if __name__ == "__main__":
    unittest.main()
