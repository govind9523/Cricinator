"""Small transactional storage adapter; SQL intentionally shared by SQLite/Postgres."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, location, timeout=5, ttl=604800):
        self.location, self.timeout, self.ttl = location, timeout, ttl
        self.postgres = location.startswith(("postgres://", "postgresql://"))
        if not self.postgres:
            Path(location).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            for sql in (
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)",
                "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, state TEXT NOT NULL, expires DOUBLE PRECISION NOT NULL)",
                "CREATE TABLE IF NOT EXISTS feedback (game TEXT PRIMARY KEY, player TEXT NOT NULL, history TEXT NOT NULL, model_version TEXT NOT NULL, status TEXT NOT NULL, created DOUBLE PRECISION NOT NULL)",
                "CREATE TABLE IF NOT EXISTS rate_limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires DOUBLE PRECISION NOT NULL)",
                "CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires)",
                "CREATE INDEX IF NOT EXISTS rates_expiry ON rate_limits(expires)",
                "INSERT INTO schema_version VALUES (1) ON CONFLICT DO NOTHING",
            ):
                self.execute(db, sql)
            if self.execute(
                db, "SELECT version FROM schema_version ORDER BY version"
            ).fetchall() != [(1,)]:
                raise RuntimeError("Unsupported database schema version; deploy matching code.")

    def execute(self, db, sql, args=()):
        return db.execute(sql.replace("?", "%s") if self.postgres else sql, args)

    @contextmanager
    def connect(self):
        if self.postgres:
            import psycopg

            db = psycopg.connect(
                self.location,
                connect_timeout=self.timeout,
                options=f"-c statement_timeout={self.timeout * 1000} -c lock_timeout={self.timeout * 1000}",
            )
        else:
            db = sqlite3.connect(self.location, timeout=self.timeout)
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def game(self, sid):
        with self.connect() as db:
            if not self.postgres:
                db.execute("BEGIN IMMEDIATE")
            self.execute(
                db,
                "INSERT INTO sessions VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                (sid, "{}", time.time() + self.ttl),
            )
            row = self.execute(
                db,
                "SELECT state, expires FROM sessions WHERE id=?"
                + (" FOR UPDATE" if self.postgres else ""),
                (sid,),
            ).fetchone()
            yield db, json.loads(row[0]) if row[1] > time.time() else {}

    def save(self, db, sid, state):
        self.execute(
            db,
            "UPDATE sessions SET state=?, expires=? WHERE id=?",
            (json.dumps(state), time.time() + self.ttl, sid),
        )

    def read(self, sid):
        with self.connect() as db:
            row = self.execute(
                db, "SELECT state FROM sessions WHERE id=? AND expires>?", (sid, time.time())
            ).fetchone()
            return json.loads(row[0]) if row else {}

    def queue(self, db, state, player):
        self.execute(
            db,
            "INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?)",
            (
                state["game_id"],
                player,
                json.dumps(state["history"]),
                state["model_version"],
                "pending",
                time.time(),
            ),
        )

    def allow(self, key, limit, seconds):
        now = time.time()
        with self.connect() as db:
            if self.postgres:
                # Serialize the capped bucket insert across hosts, not just each worker.
                db.execute("SELECT pg_advisory_xact_lock(72419631)")
            if not self.postgres:
                db.execute("BEGIN IMMEDIATE")
            self.execute(db, "DELETE FROM rate_limits WHERE expires<=?", (now,))
            self.execute(db, "DELETE FROM sessions WHERE expires<=?", (now,))
            # A bounded persistent table prevents unique-IP floods from growing storage indefinitely.
            self.execute(
                db,
                "INSERT INTO rate_limits SELECT ?, 0, ? WHERE (SELECT COUNT(*) FROM rate_limits)<10000 ON CONFLICT DO NOTHING",
                (key, now + seconds),
            )
            return (
                self.execute(
                    db,
                    "UPDATE rate_limits SET count=count+1 WHERE key=? AND count<? AND expires>?",
                    (key, limit, now),
                ).rowcount
                == 1
            )

    def ready(self):
        with self.connect() as db:
            return (
                self.execute(db, "SELECT version FROM schema_version WHERE version=1").fetchone()
                is not None
            )
