"""Refresh attributed international cap lists; cached HTML is never distributed."""

import argparse
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

BASE = "https://en.wikipedia.org/wiki/"
FORMATS = {"Test": "Test", "ODI": "One_Day_International", "T20I": "Twenty20_International"}
ROOT = Path(__file__).resolve().parents[1]


def canonical(url):
    p = urlsplit(urljoin(BASE, url))
    if p.hostname != "en.wikipedia.org" or not p.path.startswith("/wiki/"):
        return None
    title = unquote(p.path[6:]).replace(" ", "_")
    if ":" in title or not title:
        return None
    return BASE + quote(title, safe="_()'!,-")


def discover(html, fmt, gender):
    found = {}
    pattern = r"^List_of_(.+?)_(Test|ODI|One_Day_International|Twenty20_International)_cricketers$"
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        url = canonical(a["href"])
        if not url:
            continue
        match = re.match(pattern, unquote(url.split("/wiki/")[-1]))
        if not match:
            continue
        team, token = match.groups()
        is_women = "_women" in team
        actual_fmt = (
            "ODI"
            if token in ("ODI", "One_Day_International")
            else "T20I"
            if token == "Twenty20_International"
            else "Test"
        )
        if actual_fmt != fmt or is_women != (gender == "women"):
            continue
        country = team.replace("_women's", "").replace("_women", "").replace("_", " ")
        found[url] = {"url": url, "country": country, "format": fmt, "gender": gender}
    return list(found.values())


def clean(cell):
    text = cell.get_text(" ", strip=True)
    return re.sub(r"\[[^\]]*\]", "", text).strip()


def year(text):
    years = re.findall(r"\b(?:18|19|20)\d{2}\b", text)
    return int(years[0]) if years else None


def table_rows(table):
    pending = {}
    for tr in table.select("tr"):
        direct = tr.find_all(["th", "td"], recursive=False)
        if direct and direct[0].name == "td" and re.match(r"^\d", clean(direct[0])):
            pending = {i: value for i, value in pending.items() if value[0].name != "th"}
        grid = {i: cell for i, (cell, remaining) in pending.items()}
        pending = {
            i: (cell, remaining - 1) for i, (cell, remaining) in pending.items() if remaining > 1
        }
        col = 0
        for cell in tr.find_all(["th", "td"], recursive=False):
            while col in grid:
                col += 1
            for i in range(col, col + int(cell.get("colspan") or 1)):
                grid[i] = cell
                if int(cell.get("rowspan") or 1) > 1:
                    pending[i] = (cell, int(cell["rowspan"]) - 1)
            col += int(cell.get("colspan") or 1)
        yield [grid[i] for i in sorted(grid)]


def parse_players(html, url, country, fmt, gender, retrieved):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for table in soup.select("table.wikitable"):
        header = None
        for cells in table_rows(table):
            labels = [clean(c).lower().strip(". ") for c in cells]
            if any(x in ("name", "player") for x in labels) and any(
                x in ("cap", "cap no", "no", "number", "#") for x in labels
            ):
                # A cap table has career or cricket statistics; exclude captain/official tables.
                if any(x in labels for x in ("won", "lost", "win%")):
                    header = None
                    continue
                all_text = table.get_text(" ", strip=True).lower()
                if not any(
                    x in all_text for x in ("debut", "first", "career", "span", "runs", "wickets")
                ):
                    continue
                header = labels
                continue
            if header is None or len(cells) < len(header):
                continue
            ni = next(i for i, x in enumerate(header) if x in ("name", "player"))
            ci = next(
                i for i, x in enumerate(header) if x in ("cap", "cap no", "no", "number", "#")
            )
            if not re.match(r"^\d+", clean(cells[ci])):
                continue
            cell = cells[ni]
            name = clean(cell).rstrip("*†‡ ").strip()
            if not name or len(name) > 100 or name.lower() in ("total", "totals", "overall"):
                continue
            links = [
                canonical(a["href"])
                for a in cell.select("a[href]")
                if "new" not in a.get("class", []) and not a["href"].startswith("#")
            ]
            profile = next((x for x in links if x), None)
            # Honorary England cap: the source footnote says his match lost Test status.
            if profile == BASE + "Alan_Jones_(cricketer,_born_1938)":
                continue
            identity = profile or url + "#" + name
            debut = last = None
            for i, label in enumerate(header):
                value = clean(cells[i])
                if label in (
                    "first",
                    "debut",
                    "first match",
                    "first test",
                    "first odi",
                    "first t20i",
                ):
                    debut = year(value)
                if label in ("last", "last match", "last test", "last odi", "last t20i"):
                    last = year(value)
                if label in ("span", "career", "years", "playing career"):
                    years = re.findall(r"\b(?:18|19|20)\d{2}\b", value)
                    if years:
                        debut, last = int(years[0]), int(years[-1])
            stats = {}
            for key, labels in (
                ("matches", ("mat", "matches", "match")),
                ("runs", ("runs",)),
                ("wickets", ("wkt", "wkts", "wickets")),
            ):
                index = next((i for i, label in enumerate(header) if label in labels), None)
                if index is not None:
                    raw = clean(cells[index]).replace(",", "")
                    if re.fullmatch(r"\d+", raw):
                        stats[key] = int(raw)
            out.append(
                {
                    "stats": {fmt: stats} if stats else {},
                    "id": "wiki-" + hashlib.sha256(identity.encode()).hexdigest()[:16],
                    "name": name,
                    "countries": [country],
                    "formats": [fmt],
                    "gender": gender,
                    "debut": debut,
                    "last_year": last,
                    "profile_url": profile,
                    "sources": [url],
                    "retrieved": retrieved,
                }
            )
    return out


def merge_players(rows):
    merged = {}
    for row in rows:
        if row["id"] not in merged:
            merged[row["id"]] = dict(row)
            continue
        dest = merged[row["id"]]
        for fmt, stats in row.get("stats", {}).items():
            if fmt in dest.get("stats_ambiguous", []):
                continue
            previous = dest.setdefault("stats", {}).get(fmt)
            if previous is not None and previous != stats:
                dest["stats"].pop(fmt, None)
                dest.setdefault("stats_ambiguous", []).append(fmt)
            else:
                dest["stats"][fmt] = stats
        for key in ("countries", "formats", "sources"):
            dest[key] = sorted(set(dest[key] + row[key]))
        for key, operation in (("debut", min), ("last_year", max)):
            vals = [v for v in (dest[key], row[key]) if v is not None]
            dest[key] = operation(vals) if vals else None
    return sorted(merged.values(), key=lambda p: (p["name"].casefold(), p["id"]))


def fetch(url, cache, refresh=False):
    path = cache / (hashlib.sha256(url.encode()).hexdigest() + ".html")
    if path.exists() and not refresh:
        return path.read_text()
    time.sleep(0.25)
    req = Request(
        url,
        headers={
            "User-Agent": "CricinatorCatalog/1.0 (public educational cricket catalog; bounded cached retrieval)"
        },
    )
    with urlopen(req, timeout=40) as response:
        html = response.read().decode("utf-8")
    path.write_text(html)
    return html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("/tmp/cricinator-world-source-cache"))
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.now(timezone.utc).isoformat()
    indexes, sources, records = [], {}, []
    for gender in ("men", "women"):
        for fmt, token in FORMATS.items():
            url = (
                BASE + "Lists_of_" + ("women_" if gender == "women" else "") + token + "_cricketers"
            )
            entry = {"url": url, "gender": gender, "format": fmt}
            try:
                found = discover(fetch(url, args.cache, args.refresh), fmt, gender)
                entry.update(status="ok" if found else "empty", discovered=len(found))
                sources.update({p["url"]: p for p in found})
            except Exception as exc:
                entry.update(status="failed", error=str(exc))
            indexes.append(entry)
            print("index", gender, fmt, entry.get("discovered", entry.get("error")), flush=True)

    def ingest(source):
        source = dict(source)
        try:
            html = fetch(source["url"], args.cache, args.refresh)
            players = parse_players(
                html,
                source["url"],
                source["country"],
                source["format"],
                source["gender"],
                retrieved,
            )
            cached = args.cache / (hashlib.sha256(source["url"].encode()).hexdigest() + ".html")
            source.update(
                status="ok" if players else "empty",
                rows=len(players),
                content_sha256=hashlib.sha256(html.encode()).hexdigest(),
                fetched_at=datetime.fromtimestamp(cached.stat().st_mtime, timezone.utc).isoformat(),
            )
            return source, players
        except Exception as exc:
            source.update(status="failed", error=str(exc), rows=0)
            return source, []

    with ThreadPoolExecutor(max_workers=3) as pool:
        for source, players in pool.map(ingest, sources.values()):
            records.extend(players)
            sources[source["url"]] = source
            print(
                source["status"],
                source["country"],
                source["gender"],
                source["format"],
                len(players),
                flush=True,
            )
    players = merge_players(records)
    manifest = {
        "retrieved": retrieved,
        "license": "CC BY-SA 4.0",
        "license_url": "https://en.wikipedia.org/wiki/Wikipedia:Copyrights",
        "indexes": indexes,
        "sources": list(sources.values()),
    }
    coverage = {
        "retrieved": retrieved,
        "catalog_players": len(players),
        "countries": sorted({c for p in players for c in p["countries"]}),
        "by_gender": {g: sum(p["gender"] == g for p in players) for g in ("men", "women")},
        "by_format": {f: sum(f in p["formats"] for p in players) for f in FORMATS},
        "source_pages": len(sources),
        "parsed_pages": sum(s["status"] == "ok" for s in sources.values()),
        "failed_pages": [s for s in sources.values() if s["status"] != "ok"],
        "unknown_debut": sum(p["debut"] is None for p in players),
        "unknown_last_year": sum(p["last_year"] is None for p in players),
        "unlinked_profiles": sum(p["profile_url"] is None for p in players),
        "complete": False,
        "limitations": [
            "Source-index coverage is not proof of every international player ever.",
            "Wikipedia pages differ in update date and may omit recent debutants.",
            "Unlinked names stay source-scoped and may duplicate people across formats.",
            "Profile redirect aliases are not resolved; identical names never imply identical people.",
            "Earliest known source year is not guaranteed actual international debut; last year does not establish retirement.",
            "Catalog-only profiles do not have verified role, batting, bowling, club or award facts.",
        ],
    }
    for filename, data in (
        ("catalog.json", {"version": 1, "retrieved": retrieved, "players": players}),
        ("source-manifest.json", manifest),
        ("coverage.json", coverage),
    ):
        (ROOT / "data" / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in coverage.items()
                if k not in ("countries", "failed_pages", "limitations")
            }
        )
    )


if __name__ == "__main__":
    main()
