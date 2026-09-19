# Cricinator World

Think of a cricketer. Answer up to 20 questions. Let Scout take a guess.

A Python guessing game with a WebGL cricket stadium, animated host, accessible five-choice questions, undo, restart-safe game sessions and an in-app AI lab that reports the model pipeline and evaluation metrics from local artifacts. Classic is the recommended mode; World is an experimental expansion.

[Research paper](https://doi.org/10.1109/DISCOVER66922.2025.11259006) · [GitHub](https://github.com/govind9523/Cricinator)

## Play locally

Use Python 3.12 (the deployment runtime).

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:7861. No model API key is required. Assets and the dataset are local; the game makes no third-party inference calls. Set a stable `SECRET_KEY` to retain sessions across restarts. Environment variables must be exported; `.env` is not automatically loaded.

## Coverage and measured accuracy

| Mode | Scope | Reproducible result |
| --- | --- | --- |
| Classic | 138 enriched player profiles | 138/138 clean synthetic games; mean 7.93 questions |
| Classic with noise | Same 138 profiles, two games each | 250/276 correct first guesses (90.58%); mean 11.01 questions |
| World beta | 12,559 playable records after merging curated profiles | 28/120 correct first guesses (23.33%); mean 19.5 questions |

These simulations generate answers from the same facts used by inference. **They are not independent human accuracy measurements.** Classic noise uses seed 42, 15% unknown answers and otherwise 5% flipped answers. World uses a fixed random sample with seed 20260917. Saved results include failures in `data/evaluation.json` and `data/world-evaluation.json`.

The source catalog contains **12,556 source identities** from 277 international list pages: men's and women's Test, ODI and T20I, including historical and associate teams. Its 118 team labels include historical and composite teams, not 118 countries. Of these identities, 5,407 lack canonical profile links and can overlap across formats. Counts must not be described as unique people or every international player ever.

World has 7,469 distinct fact signatures; 7,300 records share their signature with another record. More verified distinguishing facts and identity resolution are necessary before a broad accuracy claim. World remains beta, with Classic selected by default. See [data provenance](docs/DATA_SOURCES.md).

## How guessing and learning work

A NumPy-backed hybrid engine updates candidate probabilities after each answer. The primary path uses Bayesian inference and information-gain questions. When confidence is low and top candidates are close, the app switches to a deterministic legacy splitter that asks the best remaining question across the leading candidates. Unknown answers leave probabilities unchanged; absent player facts stay unknown. The UI shows the active engine path and confidence for each round.

The app exposes the implemented research pipeline at `/api/research` and renders it in the AI Lab section of the homepage. That report is generated from `data/evaluation.json`, `data/world-evaluation.json` and `data/coverage.json`, so the visible claims stay tied to reproducible files instead of hand-written marketing text. See [research validation](docs/RESEARCH_VALIDATION.md).

The current model is Bayesian inference with bounded, reviewed statistical learning. It is not a deployed reinforcement-learning policy. Anonymous feedback enters a pending queue and cannot automatically alter live predictions. An operator reviews reports, exports a candidate model, evaluates it, then deploys it explicitly:

```sh
python scripts/train_feedback.py pending
python scripts/train_feedback.py approve --game GAME_ID
python scripts/train_feedback.py export --source-version MODEL_VERSION --output private/candidate.json
```

Set `MODEL_PATH` only after reviewing the candidate against a held-out evaluation. The included baseline simulation scripts evaluate the base model, not an exported candidate; they do not establish learned improvement. Feedback never overwrites source facts. The 2025 paper and this implementation are separate artifacts.

## Verification

```sh
python -W error -m unittest discover -s tests
node web/frontend-check.cjs
python scripts/evaluate.py --repeats 2
python scripts/benchmark_world.py
```

Tests cover inference, catalog parsing, roster merging, reviewed feedback, SQLite durability, concurrent updates, stale revisions, idempotency, immutable completed games, request validation and the research report contract. The frontend check covers mode selection, restart revision, recovery, correction-list contracts, AI Lab bindings and DOM consistency. WebGL has a CSS fallback, reduced-motion support and a capped rendering resolution.

## Free-first deployment

Upload these files to the root of your personal Cricinator repository. Create a Render Blueprint using `render.yaml`. Supply your personal managed PostgreSQL connection string as the secret `DATABASE_URL`; the blueprint generates `SECRET_KEY` and uses `/readyz` for readiness.

Production startup requires PostgreSQL and a stable secret. This avoids silently losing sessions and feedback on an ephemeral filesystem. A provider's free PostgreSQL tier can be used within its current quotas; confirm cost and retention before creating it. Free compute can sleep and has no always-on guarantee. No paid service is created by this repository.

**Release boundary:** PostgreSQL support is implemented but has not been tested against a live database in this environment. A public deployment, restart/durability smoke test and independent human evaluation are still required. This release must not be represented as a verified production deployment. See [operations and deployment checks](docs/OPERATIONS.md).

## Security and data

Server-side sessions use signed opaque cookies, monotonic revisions and transactional updates. Mutations require same-origin JSON requests. Shared rate limits, payload limits, secure production cookies and a content security policy protect the application. Public feedback is pending until reviewed. The application stores game answers and chosen identities, not accounts or raw IP addresses; rate limits use short-lived HMAC identifiers. Hosting logs are separate.

Keep database files, feedback exports, `.env` and credentials out of Git. The `private/` directory is ignored. Establish feedback retention and backups before a public launch.

Player facts are attributed to their source pages; unknowns and source limitations remain explicit. No player photographs are bundled. Three.js is vendored under its MIT license in `web/vendor/`. Catalog refresh tooling and attribution are documented in `docs/DATA_SOURCES.md`.

## Publication

Govind Kumar and S. Thenmozhi. **Cricinator: An AI-Driven Cricketer Guessing Game Leveraging Reinforcement Learning.** IEEE DISCOVER 2025. [DOI: 10.1109/DISCOVER66922.2025.11259006](https://doi.org/10.1109/DISCOVER66922.2025.11259006).

Publication is distinct from the current game's evaluation; it does not establish the accuracy or production readiness of this release.
