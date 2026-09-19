"""Refresh attributed public infobox facts; never invent missing attributes."""

import concurrent.futures
import datetime
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "Sir Don Bradman": "Don Bradman",
    "Sir Garfield Sobers": "Garfield Sobers",
    "Sir Vivian Richards": "Viv Richards",
    "Mehidy Hasan": "Mehidy Hasan Miraz",
    "Najmul Hossain": "Najmul Hossain Shanto",
    "Mohammad Nawaz": "Mohammad Nawaz (cricketer)",
    "George Dockrell": "George Dockrell",
    "Mark Wood": "Mark Wood (cricketer)",
    "Sean Williams": "Sean Williams (cricketer)",
    "Matt Henry": "Matt Henry (cricketer)",
    "Kyle Mayers": "Kyle Mayers",
    **{
        n: n + " (cricketer)"
        for n in [
            "Steve Smith",
            "David Warner",
            "Tom Latham",
            "James Anderson",
            "Fakhar Zaman",
            "Hasan Ali",
        ]
    },
    "Daryl Mitchell": "Daryl Mitchell (New Zealand cricketer)",
}


def collect(row):
    name = row["fullname"]
    title = ALIASES.get(name, name).replace(" ", "_")
    url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "CricinatorPortfolio/1.0 (public cricket infobox research)"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read()
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    soup = BeautifulSoup(html, "html.parser")
    box = soup.select_one("table.infobox")
    if not box:
        raise ValueError("Missing infobox: " + name)
    for node in box.select("sup"):
        node.decompose()
    fields = {}
    for tr in box.select("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th and td:
            fields[th.get_text(" ", strip=True)] = td.get_text(" ", strip=True)
    born = box.select_one(".bday")
    born = int(born.get_text()[:4]) if born else None
    batting = fields.get("Batting", "")
    bowling = fields.get("Bowling", "")
    role = fields.get("Role", "")
    if not born or not batting or not role:
        raise ValueError("Incomplete identity: " + name + " " + str(fields))
    teams = []
    domestic = False
    for tr in box.select("tr"):
        line = tr.get_text(" ", strip=True)
        if "Domestic team information" in line:
            domestic = True
            continue
        if domestic and ("Career statistics" in line or "International information" in line):
            domestic = False
        cells = tr.find_all(["th", "td"], recursive=False)
        if domestic and len(cells) >= 2:
            team = cells[1].get_text(" ", strip=True)
            team = re.sub(r"\s*\(.*", "", team).strip()
            if team and team != "Team":
                teams.append(team)
    debut = []
    for k, v in fields.items():
        if "debut" in k.lower():
            debut.extend(int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", v))
    national = fields.get("National side", fields.get("National sides", ""))
    country = re.sub(r"\s*\(.*", "", national).strip()
    if country not in {
        "India",
        "Australia",
        "England",
        "Afghanistan",
        "Bangladesh",
        "New Zealand",
        "Pakistan",
        "South Africa",
        "Sri Lanka",
        "Ireland",
        "West Indies",
        "Zimbabwe",
    }:
        raise ValueError("Review national side: " + name + " " + national)
    raw_role = role
    role = (
        "Wicketkeeper"
        if "keeper" in role.lower()
        else "All-rounder"
        if ("round" in role.lower())
        else "Bowler"
        if role.lower() == "bowler"
        else "Batter"
    )
    return {
        "id": re.sub("[^a-z0-9]+", "-", name.lower()).strip("-"),
        "name": name,
        "country": country,
        "born": born,
        "batting": "Left" if "left" in batting.lower() else "Right",
        "bowling": bowling or None,
        "role": role,
        "source_role": raw_role,
        "debut": min(debut) if debut else None,
        "teams": sorted(set(teams)),
        "source": url,
        "retrieved": datetime.date.today().isoformat(),
    }


if __name__ == "__main__":
    rows = [{"fullname": name} for name in json.loads((ROOT / "data/roster.json").read_text())]
    cache = ROOT / "data/players.json"
    players = (
        json.loads(cache.read_text())["players"]
        if cache.exists() and "--refresh" not in sys.argv
        else []
    )
    known = {p["name"] for p in players}
    rows = [r for r in rows if r["fullname"] not in known]
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(collect, r): r["fullname"] for r in rows}
        for future in concurrent.futures.as_completed(futures):
            try:
                players.append(future.result())
            except Exception as e:
                errors.append({"name": futures[future], "error": str(e)[:250]})
    players.sort(key=lambda p: p["name"])
    output = {
        "version": 1,
        "attribution": "Wikipedia contributors; source links per player. Text facts extracted from public infoboxes. Country labels extracted from national side fields. Role spellings normalized; team history may be incomplete.",
        "players": players,
        "errors": errors,
    }
    (ROOT / "data/players.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"players": len(players), "errors": errors}, indent=2))
    sys.exit(bool(errors))
