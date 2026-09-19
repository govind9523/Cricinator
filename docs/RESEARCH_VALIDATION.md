# Research Validation

Cricinator is an Akinator-style cricket guessing game with a local AI pipeline:

1. Source-attributed player facts are loaded into Classic and World rosters.
2. Facts are encoded into a question matrix.
3. Each answer updates player probabilities with Bayesian inference.
4. The next question is selected by expected information gain.
5. If confidence is weak and top candidates are close, the legacy splitter asks a deterministic high-split question across the leading candidates.
6. A guess is made when confidence is high enough or the question limit is reached.
7. Corrections are queued for human review before they can become a learned model artifact.

## Runtime Evidence

The public app exposes `/api/research`. The homepage AI Lab renders this endpoint instead of duplicating the numbers in HTML. The endpoint reads:

- `data/evaluation.json` for Classic validation and noisy-answer robustness.
- `data/world-evaluation.json` for World beta scale, ambiguity and latency metrics.
- `data/coverage.json` for catalog source-page coverage.

This keeps the project honest during interviews: if evaluation files change, the UI changes with them.

## Current Results

| Track | Result |
| --- | --- |
| Classic clean simulation | 138/138 correct first guesses, mean 7.93 questions |
| Classic noisy simulation | 250/276 correct first guesses, 90.58%, mean 11.01 questions |
| World beta sample | 28/120 correct first guesses, 23.33%, mean 19.5 questions |
| World catalog scale | 12,559 playable source records and 574 generated questions |

These are synthetic evaluations generated from the same fact base used by the model. They validate model consistency and robustness under controlled noise. They are not independent human-accuracy measurements.

## Paper Link

Publication: Govind Kumar and S. Thenmozhi, **"Cricinator: An AI-Driven Cricketer Guessing Game Leveraging Reinforcement Learning," IEEE DISCOVER 2025**. DOI: https://doi.org/10.1109/DISCOVER66922.2025.11259006

This repository implements the production-style web application around the research idea with Bayesian inference, information-gain questions, a low-confidence legacy fallback, reviewed feedback learning and reproducible evaluation. It does not claim that a reinforcement-learning policy is deployed in production.
