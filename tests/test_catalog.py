import unittest

from scripts.catalog import discover, merge_players, parse_players


class CatalogTests(unittest.TestCase):
    def test_caps_only_and_identity(self):
        html = """<table class="wikitable"><tr><th>Cap</th><th>Name</th><th>First</th><th>Last</th></tr><tr><td>1</td><td><a href="/wiki/A_Player">A Player</a><sup>[1]</sup></td><td>1999</td><td>2002</td></tr><tr><td>2</td><td>Unlinked Person</td><td>–</td><td>–</td></tr></table><table class="wikitable"><tr><th>No.</th><th>Name</th><th>Year</th><th>Won</th></tr><tr><td>1</td><td>Coach</td><td>1990</td><td>1</td></tr></table>"""
        rows = parse_players(
            html,
            "https://en.wikipedia.org/wiki/List_of_India_Test_cricketers",
            "India",
            "Test",
            "men",
            "2026-09-17",
        )
        self.assertEqual([p["name"] for p in rows], ["A Player", "Unlinked Person"])
        self.assertEqual(rows[0]["debut"], 1999)
        self.assertIsNone(rows[1]["profile_url"])
        second = dict(rows[0], countries=["England"], formats=["ODI"])
        merged = merge_players(rows + [second])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["countries"], ["England", "India"])

    def test_rowspan_stats_and_captain_table_exclusion(self):
        html = """<table class="wikitable"><tr><th rowspan="2">Cap</th><th rowspan="2">Name</th><th rowspan="2">Career</th><th rowspan="2">Mat</th><th colspan="2">Batting</th></tr><tr><th>Runs</th><th>HS</th></tr><tr><td>1</td><td><a class="new" href="/w/index.php?redlink=1">New Person</a></td><td>2012–2020</td><td>14</td><td>1,234</td><td>100</td></tr></table><table class="wikitable"><tr><th>No.</th><th>Name</th><th>First</th><th>Last</th><th>Matches</th><th>Won</th></tr><tr><td>1</td><td>Captain Person</td><td>2000</td><td>2004</td><td>5</td><td>3</td></tr></table>"""
        rows = parse_players(
            html, "https://en.wikipedia.org/wiki/List_of_Test", "India", "Test", "men", "now"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stats"], {"Test": {"matches": 14, "runs": 1234}})
        self.assertEqual(rows[0]["debut"], 2012)
        self.assertEqual(rows[0]["last_year"], 2020)
        self.assertIsNone(rows[0]["profile_url"])

    def test_malformed_source_spans_and_honorary_cap(self):
        html = """<table class="wikitable"><tr><th rowspan="2">Cap</th><th rowspan="2">Name</th><th colspan="">First</th><th>Last</th><th>Mat</th></tr><tr><td>1</td><td>Real Player</td><td>2000</td><td>2001</td><td>2</td></tr><tr><td>696</td><td><a href="/wiki/Alan_Jones_(cricketer,_born_1938)">Alan Jones</a></td><td>–</td><td>–</td><td>–</td></tr></table>"""
        rows = parse_players(
            html,
            "https://en.wikipedia.org/wiki/List_of_England_Test_cricketers",
            "England",
            "Test",
            "men",
            "now",
        )
        self.assertEqual([p["name"] for p in rows], ["Real Player"])
        self.assertEqual(rows[0]["stats"], {"Test": {"matches": 2}})

    def test_conflicting_stats_remain_unknown(self):
        base = {
            "id": "one",
            "name": "Player",
            "countries": ["India"],
            "formats": ["ODI"],
            "sources": ["a"],
            "debut": 2000,
            "last_year": 2002,
            "stats": {"ODI": {"matches": 10}},
        }
        other = dict(base, countries=["England"], sources=["b"], stats={"ODI": {"matches": 20}})
        player = merge_players([base, other])[0]
        self.assertEqual(player["stats"], {})
        self.assertEqual(player["stats_ambiguous"], ["ODI"])

    def test_discovery_separates_gender_and_format(self):
        html = '<a href="/wiki/List_of_India_Test_cricketers">x</a><a href="/wiki/List_of_India_women_Test_cricketers">x</a><a href="/wiki/List_of_India_ODI_cricketers">x</a>'
        self.assertEqual(len(discover(html, "Test", "men")), 1)
        self.assertEqual(len(discover(html, "Test", "women")), 1)


if __name__ == "__main__":
    unittest.main()
