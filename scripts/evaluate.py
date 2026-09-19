"""Reproducible model-consistency simulations; NOT a human accuracy estimate."""

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import Engine


def evaluate(players, noise, unknown, repeats, seed):
    rng = random.Random(seed)
    engine = Engine(players)
    wins = 0
    lengths = []
    failures = []
    for target in players:
        for _ in range(repeats):
            history = []
            for turn in range(20):
                ranked = engine.rank(history)
                if turn >= 4 and ranked[0][1] >= 0.93:
                    break
                q = engine.next_question(history)
                if not q:
                    break
                truth = engine.truth(target, q)
                roll = rng.random()
                if truth is None or roll < unknown:
                    answer = "unknown"
                else:
                    if rng.random() < noise:
                        truth = not truth
                    answer = "yes" if truth else "no"
                history.append((q["id"], answer))
            guess = engine.rank(history)[0][0]
            ok = guess["id"] == target["id"]
            wins += ok
            lengths.append(len(history))
            if not ok:
                failures.append({"target": target["name"], "guess": guess["name"]})
    return {
        "games": len(lengths),
        "correct_first_guess": wins,
        "accuracy": round(wins / len(lengths), 4),
        "mean_questions": round(statistics.mean(lengths), 2),
        "max_questions": max(lengths),
        "answer_flip_probability": noise,
        "unknown_probability": unknown,
        "failures": failures,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    players = json.loads((ROOT / "data/players.json").read_text())["players"]
    result = {
        "method": "Truth generated from the same knowledge base as inference. Measures consistency and synthetic robustness, not independent factual or human validation. No learning updates during evaluation.",
        "seed": 42,
        "players": len(players),
        "clean": evaluate(players, 0, 0, 1, 42),
        "noisy": evaluate(players, 0.05, 0.15, args.repeats, 42),
    }
    (ROOT / "data/evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
