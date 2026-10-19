import sqlite3
import time

import pytest
from fastapi import HTTPException

from production_ai.memory import Memory


def test_memory_is_scoped_by_owner_and_retains_only_configured_turns(tmp_path):
    memory = Memory(tmp_path / "memory.sqlite3", turns=1, ttl=3600, max_sessions=10)

    memory.append("alice", "session", "first", "reply 1")
    memory.append("alice", "session", "second", "reply 2")

    assert memory.read("alice", "session") == [
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply 2"},
    ]
    assert memory.read("bob", "session") == []


def test_expired_memory_is_removed_on_read(tmp_path):
    path = tmp_path / "memory.sqlite3"
    memory = Memory(path, turns=2, ttl=60, max_sessions=10)
    memory.append("alice", "session", "hello", "reply")

    with sqlite3.connect(path) as db:
        db.execute("UPDATE sessions SET updated = ?", (time.time() - 61,))

    assert memory.read("alice", "session") == []


def test_new_sessions_are_rejected_at_capacity(tmp_path):
    memory = Memory(tmp_path / "memory.sqlite3", turns=2, ttl=3600, max_sessions=1)
    memory.append("alice", "first", "hello", "reply")

    with pytest.raises(HTTPException) as error:
        memory.append("alice", "second", "hello", "reply")

    assert error.value.status_code == 503
