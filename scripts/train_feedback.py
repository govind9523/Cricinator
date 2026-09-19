"""Operator-only review/export; never promote public feedback automatically."""

import argparse
import collections
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storage import Database


def review(store, game, decision):
    if decision not in ("approved", "rejected"):
        raise ValueError("Unsupported review decision")
    with store.connect() as db:
        count = store.execute(
            db,
            "UPDATE feedback SET status=? WHERE game=? AND status=?",
            (decision, game, "pending"),
        ).rowcount
    if not count:
        raise ValueError("Feedback not found or already reviewed")


def export_model(store, versions):
    if not versions:
        raise ValueError("Choose reviewed source model versions explicitly")
    counts = collections.Counter()
    with store.connect() as db:
        rows = store.execute(
            db, "SELECT player,history,model_version FROM feedback WHERE status='approved'"
        ).fetchall()
    used = 0
    for player, history, version in rows:
        if version not in versions:
            continue
        used += 1
        for question, answer in json.loads(history):
            if answer != "unknown":
                counts[(player, question, answer)] += 1
    return {
        "schema": 1,
        "source_versions": sorted(versions),
        "reviewed_games": used,
        "counts": [
            dict(player=p, question=q, answer=a, count=n) for (p, q, a), n in sorted(counts.items())
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["pending", "approve", "reject", "export"])
    parser.add_argument("--game")
    parser.add_argument("--source-version", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    store = Database(
        os.environ.get("DATABASE_URL")
        or os.environ.get("DATABASE_PATH", str(ROOT / "instance/world.sqlite"))
    )
    if args.action == "pending":
        with store.connect() as db:
            rows = store.execute(
                db,
                "SELECT game,player,history,model_version FROM feedback WHERE status='pending' ORDER BY created LIMIT 100",
            ).fetchall()
        print(
            json.dumps(
                [
                    dict(game=g, player=p, history=json.loads(h), model_version=v)
                    for g, p, h, v in rows
                ],
                indent=2,
            )
        )
        return
    if args.action in ("approve", "reject"):
        if not args.game:
            parser.error("--game is required")
        review(store, args.game, "approved" if args.action == "approve" else "rejected")
        print("Review saved.")
        return
    if not args.output or not args.source_version:
        parser.error("--output and --source-version are required")
    model = export_model(store, set(args.source_version))
    if not model["reviewed_games"]:
        parser.error("No approved games for selected versions")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(model, indent=2) + "\n")
    temporary.replace(args.output)
    print(
        f"Exported {model['reviewed_games']} reviewed games. Evaluate the candidate before setting MODEL_PATH."
    )


if __name__ == "__main__":
    main()
