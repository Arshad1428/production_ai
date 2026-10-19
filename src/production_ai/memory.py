from contextlib import contextmanager
import json
import sqlite3
import time
from fastapi import HTTPException

class Memory:
    """Bounded SQLite conversations, isolated by authenticated identity and session UUID."""
    def __init__(self, path, turns, ttl, max_sessions):
        self.path, self.turns, self.ttl, self.max_sessions = path, turns, ttl, max_sessions
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                owner TEXT NOT NULL, session TEXT NOT NULL, updated REAL NOT NULL,
                messages TEXT NOT NULL, PRIMARY KEY(owner, session))""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def cleanup(self, db):
        db.execute("DELETE FROM sessions WHERE updated < ?", (time.time()-self.ttl,))

    def read(self, owner, session):
        with self.connect() as db:
            self.cleanup(db)
            row = db.execute("SELECT messages FROM sessions WHERE owner=? AND session=?",
                             (owner, session)).fetchone()
            return json.loads(row[0]) if row else []

    def append(self, owner, session, user, assistant):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.cleanup(db)
            row = db.execute("SELECT messages FROM sessions WHERE owner=? AND session=?",
                             (owner, session)).fetchone()
            if not row and db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= self.max_sessions:
                raise HTTPException(503, "Conversation capacity reached; delete a session or retry after expiry")
            history = json.loads(row[0]) if row else []
            history.extend([{"role":"user", "content":user}, {"role":"assistant", "content":assistant}])
            history = history[-self.turns*2:]
            db.execute("INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?)",
                       (owner, session, time.time(), json.dumps(history)))

    def delete(self, owner, session):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE owner=? AND session=?", (owner, session))
