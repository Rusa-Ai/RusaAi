"""Durable local task queue with SQLite leases and an append-only event log.

This module stores task state only. It does not execute worker code, launch model
inference, or grant permissions to external tools.
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping


_STATES = ("QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
_TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
_MAX_ATTEMPTS = 100
_MAX_ERROR_LENGTH = 2000
_MAX_PAYLOAD_BYTES = 1024 * 1024
_MAX_PRIORITY = (2 ** 31) - 1


class QueueError(RuntimeError):
    """Base exception for task queue errors."""


class QueueConflict(QueueError):
    """Raised when a task transition is stale or conflicts with current state."""


@dataclass(frozen=True)
class Task:
    task_id: str
    task_type: str
    payload: dict[str, Any]
    state: str
    priority: int
    attempts: int
    max_attempts: int
    created_at: float
    updated_at: float
    available_at: float
    claimed_by: str | None
    lease_expires_at: float | None
    last_error: str | None


@dataclass(frozen=True)
class TaskEvent:
    event_id: int
    task_id: str
    event_type: str
    actor: str | None
    occurred_at: float
    details: dict[str, Any]


def _timestamp(value: float | None) -> float:
    result = time.time() if value is None else float(value)
    if not math.isfinite(result):
        raise ValueError("timestamp must be finite")
    return result


def _positive_duration(value: float, field_name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{field_name} must be a finite positive number")
    return result


class SQLiteTaskQueue:
    """SQLite-backed queue safe for independent local worker processes."""

    def __init__(self, database_path: str | Path, *, busy_timeout_seconds: float = 10.0):
        path = str(database_path)
        if not path or path == ":memory:":
            raise ValueError("use a file-backed SQLite database for durable queue state")
        expanded_path = Path(path).expanduser()
        expanded_path.parent.resolve().mkdir(parents=True, exist_ok=True)
        self.database_path = str(expanded_path)
        self.busy_timeout_seconds = _positive_duration(
            busy_timeout_seconds, "busy_timeout_seconds"
        )
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.busy_timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_seconds * 1000)}")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN
                        ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
                    priority INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    max_attempts INTEGER NOT NULL CHECK (max_attempts BETWEEN 1 AND 100),
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    available_at REAL NOT NULL,
                    claimed_by TEXT,
                    lease_expires_at REAL,
                    last_error TEXT,
                    CHECK (
                        (state = 'RUNNING' AND claimed_by IS NOT NULL AND lease_expires_at IS NOT NULL)
                        OR
                        (state != 'RUNNING' AND claimed_by IS NULL AND lease_expires_at IS NULL)
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_claim
                    ON tasks(state, available_at, priority DESC, created_at, task_id);

                CREATE TABLE IF NOT EXISTS task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    event_type TEXT NOT NULL,
                    actor TEXT,
                    occurred_at REAL NOT NULL,
                    details_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_task_events_task
                    ON task_events(task_id, event_id);

                CREATE TRIGGER IF NOT EXISTS task_events_prevent_update
                BEFORE UPDATE ON task_events
                BEGIN
                    SELECT RAISE(ABORT, 'task_events is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS task_events_prevent_delete
                BEFORE DELETE ON task_events
                BEGIN
                    SELECT RAISE(ABORT, 'task_events is append-only');
                END;
                """
            )
        finally:
            connection.close()

    @staticmethod
    def _serialize_payload(payload: Mapping[str, Any]) -> str:
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")
        try:
            serialized = json.dumps(
                dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must contain JSON-compatible finite values") from exc
        if len(serialized.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            raise ValueError("serialized payload must not exceed 1 MiB")
        return serialized

    @staticmethod
    def _task(row: sqlite3.Row | None) -> Task | None:
        if row is None:
            return None
        return Task(
            task_id=row["task_id"],
            task_type=row["task_type"],
            payload=json.loads(row["payload_json"]),
            state=row["state"],
            priority=row["priority"],
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            available_at=row["available_at"],
            claimed_by=row["claimed_by"],
            lease_expires_at=row["lease_expires_at"],
            last_error=row["last_error"],
        )

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        task_id: str,
        event_type: str,
        actor: str | None,
        occurred_at: float,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        details_json = json.dumps(
            dict(details or {}), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        connection.execute(
            """
            INSERT INTO task_events(task_id, event_type, actor, occurred_at, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, event_type, actor, occurred_at, details_json),
        )

    def enqueue(
        self,
        task_type: str,
        payload: Mapping[str, Any],
        *,
        task_id: str | None = None,
        priority: int = 0,
        max_attempts: int = 3,
        now: float | None = None,
    ) -> Task:
        if not isinstance(task_type, str) or not task_type.strip():
            raise ValueError("task_type must be a non-empty string")
        normalized_task_type = task_type.strip()
        if not isinstance(priority, int) or not -(2 ** 31) <= priority <= _MAX_PRIORITY:
            raise ValueError("priority must be a signed 32-bit integer")
        if not isinstance(max_attempts, int) or not 1 <= max_attempts <= _MAX_ATTEMPTS:
            raise ValueError(f"max_attempts must be between 1 and {_MAX_ATTEMPTS}")
        timestamp = _timestamp(now)
        serialized = self._serialize_payload(payload)
        identifier = str(uuid.uuid4()) if task_id is None else task_id
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("task_id must be a non-empty string")
        identifier = identifier.strip()

        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (identifier,)
            ).fetchone()
            if existing is not None:
                same_request = (
                    existing["task_type"] == normalized_task_type
                    and existing["payload_json"] == serialized
                    and existing["priority"] == priority
                    and existing["max_attempts"] == max_attempts
                )
                if not same_request:
                    raise QueueConflict("task_id already exists with a different task contract")
                return self._task(existing)  # Idempotent replay; do not append another event.

            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, task_type, payload_json, state, priority, attempts,
                    max_attempts, created_at, updated_at, available_at
                ) VALUES (?, ?, ?, 'QUEUED', ?, 0, ?, ?, ?, ?)
                """,
                (identifier, normalized_task_type, serialized, priority, max_attempts,
                 timestamp, timestamp, timestamp),
            )
            self._event(
                connection, identifier, "TASK_ENQUEUED", None, timestamp,
                {"priority": priority, "max_attempts": max_attempts},
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (identifier,)
            ).fetchone()
            return self._task(row)  # type: ignore[return-value]

    def _reclaim_expired_tx(self, connection: sqlite3.Connection, timestamp: float) -> list[str]:
        expired = connection.execute(
            """
            SELECT * FROM tasks
            WHERE state = 'RUNNING' AND lease_expires_at <= ?
            ORDER BY lease_expires_at, task_id
            """,
            (timestamp,),
        ).fetchall()
        reclaimed: list[str] = []
        for row in expired:
            retry = row["attempts"] < row["max_attempts"]
            new_state = "QUEUED" if retry else "FAILED"
            event_type = "LEASE_EXPIRED_REQUEUED" if retry else "LEASE_EXPIRED_FAILED"
            connection.execute(
                """
                UPDATE tasks
                SET state = ?, updated_at = ?, available_at = ?,
                    claimed_by = NULL, lease_expires_at = NULL,
                    last_error = 'worker lease expired'
                WHERE task_id = ? AND state = 'RUNNING'
                """,
                (new_state, timestamp, timestamp, row["task_id"]),
            )
            self._event(
                connection, row["task_id"], event_type, row["claimed_by"], timestamp,
                {"attempts": row["attempts"], "max_attempts": row["max_attempts"]},
            )
            reclaimed.append(row["task_id"])
        return reclaimed

    def reclaim_expired(self, *, now: float | None = None) -> list[str]:
        timestamp = _timestamp(now)
        with self._transaction() as connection:
            return self._reclaim_expired_tx(connection, timestamp)

    def claim(
        self,
        worker_id: str,
        *,
        lease_seconds: float = 60.0,
        now: float | None = None,
    ) -> Task | None:
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a non-empty string")
        if len(worker_id) > 128:
            raise ValueError("worker_id must be at most 128 characters")
        worker_id = worker_id.strip()
        lease = _positive_duration(lease_seconds, "lease_seconds")
        timestamp = _timestamp(now)

        with self._transaction() as connection:
            self._reclaim_expired_tx(connection, timestamp)
            row = connection.execute(
                """
                SELECT * FROM tasks
                WHERE state = 'QUEUED' AND available_at <= ?
                ORDER BY priority DESC, created_at ASC, task_id ASC
                LIMIT 1
                """,
                (timestamp,),
            ).fetchone()
            if row is None:
                return None
            expires_at = timestamp + lease
            updated = connection.execute(
                """
                UPDATE tasks
                SET state = 'RUNNING', attempts = attempts + 1, updated_at = ?,
                    claimed_by = ?, lease_expires_at = ?
                WHERE task_id = ? AND state = 'QUEUED'
                """,
                (timestamp, worker_id, expires_at, row["task_id"]),
            )
            if updated.rowcount != 1:
                raise QueueConflict("task was claimed concurrently; retry claim")
            self._event(
                connection, row["task_id"], "TASK_CLAIMED", worker_id, timestamp,
                {"lease_expires_at": expires_at, "attempt": row["attempts"] + 1},
            )
            current = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (row["task_id"],)
            ).fetchone()
            return self._task(current)

    def _owned_running_task(
        self, connection: sqlite3.Connection, task_id: str, worker_id: str, timestamp: float
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT * FROM tasks
            WHERE task_id = ? AND state = 'RUNNING' AND claimed_by = ?
              AND lease_expires_at > ?
            """,
            (task_id, worker_id, timestamp),
        ).fetchone()
        if row is None:
            raise QueueConflict("task is not owned by this worker or its lease has expired")
        return row

    def heartbeat(
        self,
        task_id: str,
        worker_id: str,
        *,
        lease_seconds: float = 60.0,
        now: float | None = None,
    ) -> Task:
        lease = _positive_duration(lease_seconds, "lease_seconds")
        timestamp = _timestamp(now)
        with self._transaction() as connection:
            self._owned_running_task(connection, task_id, worker_id, timestamp)
            expires_at = timestamp + lease
            connection.execute(
                "UPDATE tasks SET updated_at = ?, lease_expires_at = ? WHERE task_id = ?",
                (timestamp, expires_at, task_id),
            )
            self._event(
                connection, task_id, "WORKER_HEARTBEAT", worker_id, timestamp,
                {"lease_expires_at": expires_at},
            )
            return self._task(
                connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            )  # type: ignore[return-value]

    def complete(self, task_id: str, worker_id: str, *, now: float | None = None) -> Task:
        timestamp = _timestamp(now)
        with self._transaction() as connection:
            self._owned_running_task(connection, task_id, worker_id, timestamp)
            connection.execute(
                """
                UPDATE tasks
                SET state = 'COMPLETED', updated_at = ?, claimed_by = NULL,
                    lease_expires_at = NULL, last_error = NULL
                WHERE task_id = ?
                """,
                (timestamp, task_id),
            )
            self._event(connection, task_id, "TASK_COMPLETED", worker_id, timestamp)
            return self._task(
                connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            )  # type: ignore[return-value]

    def fail(
        self,
        task_id: str,
        worker_id: str,
        error: str,
        *,
        retry_delay_seconds: float = 0.0,
        now: float | None = None,
    ) -> Task:
        if not isinstance(error, str) or not error.strip():
            raise ValueError("error must be a non-empty string")
        retry_delay = float(retry_delay_seconds)
        if not math.isfinite(retry_delay) or retry_delay < 0:
            raise ValueError("retry_delay_seconds must be finite and non-negative")
        timestamp = _timestamp(now)
        with self._transaction() as connection:
            row = self._owned_running_task(connection, task_id, worker_id, timestamp)
            retry = row["attempts"] < row["max_attempts"]
            new_state = "QUEUED" if retry else "FAILED"
            connection.execute(
                """
                UPDATE tasks
                SET state = ?, updated_at = ?, available_at = ?,
                    claimed_by = NULL, lease_expires_at = NULL, last_error = ?
                WHERE task_id = ?
                """,
                (
                    new_state, timestamp, timestamp + retry_delay,
                    error.strip()[:_MAX_ERROR_LENGTH], task_id,
                ),
            )
            self._event(
                connection, task_id, "TASK_REQUEUED" if retry else "TASK_FAILED",
                worker_id, timestamp,
                {"retry": retry, "retry_delay_seconds": retry_delay},
            )
            return self._task(
                connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            )  # type: ignore[return-value]

    def cancel(self, task_id: str, *, reason: str = "cancelled", now: float | None = None) -> Task:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        timestamp = _timestamp(now)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise QueueError("task does not exist")
            if row["state"] == "CANCELLED":
                return self._task(row)  # Idempotent cancellation.
            if row["state"] in _TERMINAL_STATES:
                raise QueueConflict(f"cannot cancel task in terminal state {row['state']}")
            connection.execute(
                """
                UPDATE tasks
                SET state = 'CANCELLED', updated_at = ?, claimed_by = NULL,
                    lease_expires_at = NULL, last_error = ?
                WHERE task_id = ?
                """,
                (timestamp, reason.strip()[:_MAX_ERROR_LENGTH], task_id),
            )
            self._event(
                connection, task_id, "TASK_CANCELLED", None, timestamp,
                {"reason": reason.strip()[:_MAX_ERROR_LENGTH]},
            )
            return self._task(
                connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            )  # type: ignore[return-value]

    def get(self, task_id: str) -> Task:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            task = self._task(row)
            if task is None:
                raise QueueError("task does not exist")
            return task
        finally:
            connection.close()

    def events(self, task_id: str) -> list[TaskEvent]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM task_events
                WHERE task_id = ?
                ORDER BY event_id ASC
                """,
                (task_id,),
            ).fetchall()
            return [
                TaskEvent(
                    event_id=row["event_id"],
                    task_id=row["task_id"],
                    event_type=row["event_type"],
                    actor=row["actor"],
                    occurred_at=row["occurred_at"],
                    details=json.loads(row["details_json"]),
                )
                for row in rows
            ]
        finally:
            connection.close()
