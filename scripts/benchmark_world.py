"""Measure catalog inference cost and synthetic sample accuracy, not human accuracy."""

import collections
import hashlib
import json
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import Engine
from roster import load_rosters

if __name__ == "__main__":
    rosters = load_rosters(ROOT)
    players = rosters["world"]
    start = time.perf_counter()
    engine = Engine(players)
    build = time.perf_counter() - start
    groups = collections.Counter(
        hashlib.sha256(engine.matrix[:, i].tobytes()).hexdigest() for i in range(len(players))
    )
    rng = random.Random(20260917)
    sample = rng.sample(players, min(120, len(players)))
    timings = []
    correct = 0
    lengths = []
    failures = []
    for target in sample:
        history = []
        for _ in range(20):
            ranked = engine.rank(history)
            if len(history) >= 4 and ranked[0][1] >= 0.93:
                break
            start = time.perf_counter()
            q = engine.next_question(history)
            timings.append(time.perf_counter() - start)
            if not q:
                break
            truth = engine.truth(target, q)
            history.append((q["id"], "unknown" if truth is None else "yes" if truth else "no"))
        guessed = engine.rank(history)[0][0]
        lengths.append(len(history))
        correct += guessed["id"] == target["id"]
        if guessed["id"] != target["id"]:
            failures.append({"target": target["name"], "guess": guessed["name"]})
    report = {
        "kind": "Synthetic sample using same source snapshot as inference; no independent human validation. Counts are source identities, not deduplicated people.",
        "seed": 20260917,
        "records": len(players),
        "questions": len(engine.questions),
        "matrix_megabytes": round(
            (engine.matrix.nbytes + engine.yes.nbytes + engine.no.nbytes) / 1e6, 2
        ),
        "engine_build_seconds": round(build, 3),
        "distinct_feature_signatures": len(groups),
        "ambiguous_records": sum(n for n in groups.values() if n > 1),
        "sample_games": len(sample),
        "correct_first_guesses": correct,
        "sample_accuracy": round(correct / len(sample), 4),
        "mean_questions": round(statistics.mean(lengths), 2),
        "p95_question_ms": round(sorted(timings)[int(0.95 * (len(timings) - 1))] * 1000, 2),
        "failures": failures,
    }
    (ROOT / "data/world-evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=2))
