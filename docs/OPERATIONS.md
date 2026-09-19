# Backend operations

## Local run
Use Python 3.9+ and install `requirements.txt` in a virtual environment. Export a stable random `SECRET_KEY` (at least 32 characters), optionally `DATABASE_PATH`, then run `python app.py`. Use `PORT=7863` if the demo ports are occupied. Development without a key generates a process-local key; cookies stop working after restart and across workers. Set a key for persistence testing.

SQLite is the local fallback. Its parent directory is created automatically. Backup the database while stopped, or use SQLite's backup API. PostgreSQL is required in production; ephemeral hosted SQLite is not a persistence plan.

## Personal free-first hosting
Upload the source yourself, install requirements, and run the Gunicorn command in `render.yaml`. Set `APP_ENV=production`, a stable `SECRET_KEY` shared by every worker/host, and your own managed PostgreSQL `DATABASE_URL`. Use the provider's TLS connection string (typically `sslmode=require`) and a pooled endpoint when recommended. Do not put credentials in source control or chat. The blueprint deliberately requires the connection string rather than creating a paid database. Provider free tiers, sleep, quota, retention and availability can change; verify these before deploying. The service has no uptime promise.

Production startup fails without PostgreSQL configuration or an adequate secret. Rotating the secret invalidates cookies and changes the rate-limit salt. Database connect, lock and statement timeouts default to five seconds; `DB_TIMEOUT` in application config controls them. Each request transaction opens/closes its connection; use provider pooling if workload exceeds its connection budget.

`TRUST_PROXY_HOPS=0` ignores forwarded headers. Set the exact trusted proxy count only when requests cannot bypass those proxies. The Render blueprint assumes one trusted ingress proxy. Secure session cookies are enabled in production. Configure HTTPS before testing.

## Schema and durability
Startup applies the idempotent version-1 schema in `storage.py` (sessions, feedback, rate_limits, schema_version and expiry indexes). SQL is intentionally shared across SQLite/PostgreSQL except lock and parameter syntax. Deploy future schema changes as ordered, reviewed migrations; take a provider snapshot and test restoration first. Startup currently only supports version 1.

Cookies store only a signed opaque session id. History, mode, immutable model version, monotonically increasing revision and the last 32 idempotency receipts live in the database. Sessions expire seven days after their last successful mutation. Expired sessions and rate buckets are cleaned during API rate checks. Pending feedback is retained for review; establish a retention policy before a public launch. Schema content is game answers, selected player and model version, with no raw client IP. Rate buckets use HMAC-SHA256 of IP with the secret as salt and expire after one minute.

Session transactions use PostgreSQL row locks or SQLite `BEGIN IMMEDIATE`; revision checks and feedback insertion share the same transaction. One unique feedback row per game prevents duplicate training reports. Model versions are frozen for each round; if a deployment removes its model snapshot, mutations return 409 and GET /api/state returns a recoverable home screen with the current revision for restarting. Keep immutable model artifacts when adding model rollout support. Public feedback is **pending**, never used directly in live inference.

## Client contract
Keep the normal route payloads and additionally send `revision` from the last successful state on **all existing-round mutations**, including restart. A missing/stale revision returns 409; refresh `/api/state`. Initial `/api/start` accepts `{}` or `{ "mode": "classic" }`. Configured rosters may add `world`; the server rejects unavailable modes.

Send a fresh `Idempotency-Key` (1–128 characters) per logical action and reuse it with the identical body for transport retries. Replays return the stored response; a changed body returns 409. After the most recent 32 receipts, a stale revision still rejects a replay. A cookie-less first start cannot be recovered via idempotency alone if its Set-Cookie response was lost; fetch state before continuing. Terminal completed rounds cannot accept answers, undo, rejection or another feedback choice. Three rejected guesses force miss state; feedback requires a guess/miss and at least three answers.

POST requires JSON object bodies and `X-Cricinator: 1`. Same-origin checks reject cross-site requests. IP-based fixed windows allow 12 starts, 120 writes and 180 reads per minute. The shared bucket table caps at 10,000 active identities/routes and fails closed at capacity. PostgreSQL uses a short advisory transaction lock for bucket-cap insertion. This is a deliberately simple low-volume gate; an edge limiter is appropriate when sustained traffic makes that serialization a bottleneck. Shared NAT users share quotas.

## Health, tests and release boundary
`/healthz` checks the web process only. `/readyz` additionally checks schema connectivity and reports model version/catalog size. API database failures return a generic 503 without exposing connection credentials; errors are logged by exception class. Render readiness points at `/readyz`.

Run `python -m unittest tests.test_storage tests.test_api -v`. Tests cover SQLite rollback/restart, persistent rate windows, simultaneous answer races, stale revisions, idempotency, immutable completion, pending feedback, cookie minimalism, origin/body validation and rejection limits. PostgreSQL SQL/locking is implemented but **not live integration-tested in this environment**: neither Docker nor psql is installed and no database credentials were used. Run equivalent tests against a disposable PostgreSQL database before public release. SQLite passing does not establish PostgreSQL readiness or production readiness.
