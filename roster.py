"""Join sourced identities without conflating name matches or inventing profile facts."""

import json
from urllib.parse import unquote, urlsplit


def identity(url):
    return unquote(urlsplit(url).path).replace(" ", "_").rstrip("/") if url else None


def merge_rosters(profiles, catalog):
    by_source = {identity(p.get("source")): p for p in profiles}
    world = []
    matched = set()
    for record in catalog:
        profile = by_source.get(identity(record.get("profile_url")))
        countries = record.get("countries", [])
        player = {
            "id": record["id"],
            "name": record["name"],
            "countries": countries,
            "country": " / ".join(countries),
            "gender": record.get("gender"),
            "formats": record.get("formats", []),
            "formats_complete": False,
            "born": None,
            "batting": None,
            "bowling": None,
            "role": None,
            "teams": None,
            "debut": record.get("debut"),
            "last_year": record.get("last_year"),
            "stats": record.get("stats", {}),
            "source": record.get("profile_url") or record["sources"][0],
            "sources": record.get("sources", []),
            "enriched": False,
        }
        if profile:
            player.update(profile)
            player["countries"] = countries or [profile["country"]]
            player["country"] = " / ".join(player["countries"])
            player["enriched"] = True
            matched.add(profile["id"])
        world.append(player)
    # Keep existing profiles whose source aliases weren't found. They remain separate,
    # explicitly source-identified records pending a reviewed alias crosswalk.
    for profile in profiles:
        if profile["id"] not in matched:
            world.append(dict(profile, countries=[profile["country"]], enriched=True))
    return {"classic": profiles, "world": world}


def load_rosters(root):
    profiles = json.loads((root / "data/players.json").read_text())["players"]
    path = root / "data/catalog.json"
    if not path.exists():
        return {"classic": profiles}
    return merge_rosters(profiles, json.loads(path.read_text())["players"])
