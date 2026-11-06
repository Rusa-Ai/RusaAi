import sqlite3
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "orchestrator"))

from local_queue import QueueConflict, QueueError, SQLiteTaskQueue


class SQLiteTaskQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "tasks.sqlite3"
        self.queue = SQLiteTaskQueue(self.db_path)

    def test_enqueue_persists_task_and_event(self):
        task = self.queue.enqueue("code.change", {"repo": "RusaAi"}, task_id="task-1", now=10)
        self.assertEqual(task.state, "QUEUED")
        self.assertEqual(task.attempts, 0)
        self.assertEqual(task.payload, {"repo": "RusaAi"})
        self.assertEqual([e.event_type for e in self.queue.events("task-1")], ["TASK_ENQUEUED"])

    def test_enqueue_is_idempotent_for_same_contract(self):
        first = self.queue.enqueue("test.run", {"suite": "unit"}, task_id="same", now=10)
        second = self.queue.enqueue(" test.run ", {"suite": "unit"}, task_id=" same ", now=11)
        self.assertEqual(first.task_id, second.task_id)
        self.assertEqual(len(self.queue.events("same")), 1)

    def test_enqueue_rejects_reused_id_with_different_contract(self):
        self.queue.enqueue("test.run", {"suite": "unit"}, task_id="same")
        with self.assertRaises(QueueConflict):
            self.queue.enqueue("test.run", {"suite": "integration"}, task_id="same")

    def test_claim_uses_priority_then_creation_order(self):
        self.queue.enqueue("low", {}, task_id="low", priority=1, now=10)
        self.queue.enqueue("high", {}, task_id="high", priority=10, now=11)
        task = self.queue.claim("worker-a", now=12)
        self.assertEqual(task.task_id, "high")
        self.assertEqual(task.state, "RUNNING")
        self.assertEqual(task.attempts, 1)
        self.assertEqual(task.claimed_by, "worker-a")

    def test_claim_returns_none_when_queue_is_empty(self):
        self.assertIsNone(self.queue.claim("worker-a", now=10))

    def test_claim_is_exclusive_across_threads(self):
        for index in range(8):
            self.queue.enqueue("task", {"index": index}, task_id=f"t-{index}", now=10)

        def claim(worker_number):
            return self.queue.claim(f"worker-{worker_number}", lease_seconds=30, now=11)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(claim, range(8)))
        claimed_ids = [task.task_id for task in results if task is not None]
        self.assertEqual(len(claimed_ids), 8)
        self.assertEqual(len(set(claimed_ids)), 8)

    def test_heartbeat_extends_lease(self):
        self.queue.enqueue("task", {}, task_id="heartbeat", now=10)
        self.queue.claim("worker-a", lease_seconds=5, now=11)
        renewed = self.queue.heartbeat("heartbeat", "worker-a", lease_seconds=20, now=14)
        self.assertEqual(renewed.lease_expires_at, 34)

    def test_wrong_worker_cannot_heartbeat_or_complete(self):
        self.queue.enqueue("task", {}, task_id="owner", now=10)
        self.queue.claim("worker-a", now=11)
        with self.assertRaises(QueueConflict):
            self.queue.heartbeat("owner", "worker-b", now=12)
        with self.assertRaises(QueueConflict):
            self.queue.complete("owner", "worker-b", now=12)

    def test_expired_lease_cannot_be_renewed_or_completed(self):
        self.queue.enqueue("task", {}, task_id="expired", now=10)
        self.queue.claim("worker-a", lease_seconds=5, now=11)
        with self.assertRaises(QueueConflict):
            self.queue.heartbeat("expired", "worker-a", now=16)
        with self.assertRaises(QueueConflict):
            self.queue.complete("expired", "worker-a", now=16)

    def test_complete_marks_terminal_and_releases_lease(self):
        self.queue.enqueue("task", {}, task_id="done", now=10)
        self.queue.claim("worker-a", now=11)
        task = self.queue.complete("done", "worker-a", now=12)
        self.assertEqual(task.state, "COMPLETED")
        self.assertIsNone(task.claimed_by)
        self.assertIsNone(task.lease_expires_at)

    def test_fail_requeues_then_fails_after_attempt_limit(self):
        self.queue.enqueue("task", {}, task_id="retry", max_attempts=2, now=10)
        self.queue.claim("worker-a", now=11)
        retry = self.queue.fail("retry", "worker-a", "temporary", now=12)
        self.assertEqual(retry.state, "QUEUED")
        self.assertEqual(retry.attempts, 1)
        self.queue.claim("worker-b", now=13)
        failed = self.queue.fail("retry", "worker-b", "permanent", now=14)
        self.assertEqual(failed.state, "FAILED")
        self.assertEqual(failed.attempts, 2)

    def test_retry_delay_defers_next_claim(self):
        self.queue.enqueue("task", {}, task_id="delayed", max_attempts=2, now=10)
        self.queue.claim("worker-a", now=11)
        self.queue.fail("delayed", "worker-a", "retry later", retry_delay_seconds=10, now=12)
        self.assertIsNone(self.queue.claim("worker-b", now=21))
        self.assertIsNotNone(self.queue.claim("worker-b", now=22))

    def test_claim_reclaims_expired_lease_before_selecting_work(self):
        self.queue.enqueue("task", {}, task_id="lease", max_attempts=2, now=10)
        self.queue.claim("worker-a", lease_seconds=5, now=11)
        reclaimed = self.queue.claim("worker-b", lease_seconds=10, now=16)
        self.assertEqual(reclaimed.task_id, "lease")
        self.assertEqual(reclaimed.attempts, 2)
        self.assertEqual(reclaimed.claimed_by, "worker-b")

    def test_expired_lease_uses_retry_budget(self):
        self.queue.enqueue("task", {}, task_id="lease", max_attempts=1, now=10)
        self.queue.claim("worker-a", lease_seconds=5, now=11)
        expired = self.queue.reclaim_expired(now=16)
        self.assertEqual(expired, ["lease"])
        self.assertEqual(self.queue.get("lease").state, "FAILED")

    def test_cancel_releases_running_lease_and_is_idempotent(self):
        self.queue.enqueue("task", {}, task_id="cancel", now=10)
        self.queue.claim("worker-a", now=11)
        cancelled = self.queue.cancel("cancel", reason="owner cancelled", now=12)
        self.assertEqual(cancelled.state, "CANCELLED")
        self.assertIsNone(cancelled.claimed_by)
        self.assertEqual(self.queue.cancel("cancel", now=13).state, "CANCELLED")
        with self.assertRaises(QueueConflict):
            self.queue.complete("cancel", "worker-a", now=14)

    def test_cannot_cancel_completed_task(self):
        self.queue.enqueue("task", {}, task_id="completed", now=10)
        self.queue.claim("worker-a", now=11)
        self.queue.complete("completed", "worker-a", now=12)
        with self.assertRaises(QueueConflict):
            self.queue.cancel("completed", now=13)

    def test_queue_rejects_invalid_contracts(self):
        with self.assertRaises(ValueError):
            self.queue.enqueue("", {})
        with self.assertRaises(ValueError):
            self.queue.enqueue("task", {"bad": float("nan")})
        with self.assertRaises(ValueError):
            self.queue.enqueue("task", {"large": "x" * (1024 * 1024)})
        with self.assertRaises(ValueError):
            self.queue.enqueue("task", {}, task_id="   ")
        with self.assertRaises(ValueError):
            self.queue.enqueue("task", {}, max_attempts=0)
        with self.assertRaises(ValueError):
            self.queue.claim("")
        with self.assertRaises(ValueError):
            self.queue.claim("worker", lease_seconds=float("inf"))
        with self.assertRaises(ValueError):
            self.queue.fail("not-found", "worker", "")

    def test_event_log_rejects_updates_and_deletes(self):
        self.queue.enqueue("task", {}, task_id="immutable-events", now=10)
        connection = self.queue._connect()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE task_events SET event_type = 'TAMPERED' WHERE task_id = ?",
                    ("immutable-events",),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM task_events WHERE task_id = ?",
                    ("immutable-events",),
                )
        finally:
            connection.close()
        self.assertEqual(
            [event.event_type for event in self.queue.events("immutable-events")],
            ["TASK_ENQUEUED"],
        )

    def test_complete_persists_json_result(self):
        self.queue.enqueue("task", {}, task_id="result", now=10)
        self.queue.claim("worker-a", now=11)
        completed = self.queue.complete("result", "worker-a", result={"answer": 42}, now=12)
        self.assertEqual(completed.result, {"answer": 42})
        self.assertEqual(self.queue.get("result").result, {"answer": 42})

    def test_queue_migrates_legacy_database_without_result_column(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        connection = sqlite3.connect(legacy_path)
        connection.execute(
            """
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                state TEXT NOT NULL,
                priority INTEGER NOT NULL,
                attempts INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                available_at REAL NOT NULL,
                claimed_by TEXT,
                lease_expires_at REAL,
                last_error TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO tasks VALUES
            ('legacy', 'task', '{}', 'QUEUED', 0, 0, 3, 10, 10, 10, NULL, NULL, NULL)
            """
        )
        connection.commit()
        connection.close()

        migrated = SQLiteTaskQueue(legacy_path)
        self.assertIsNone(migrated.get("legacy").result)
        columns = {
            row["name"] for row in migrated._connect().execute("PRAGMA table_info(tasks)")
        }
        self.assertIn("result_json", columns)

    def test_file_database_survives_queue_reconstruction(self):
        self.queue.enqueue("task", {"value": 42}, task_id="persisted", now=10)
        reopened = SQLiteTaskQueue(self.db_path)
        task = reopened.get("persisted")
        self.assertEqual(task.payload["value"], 42)
        self.assertEqual(task.state, "QUEUED")

    def test_event_log_records_worker_lifecycle(self):
        self.queue.enqueue("task", {}, task_id="events", now=10)
        self.queue.claim("worker-a", now=11)
        self.queue.heartbeat("events", "worker-a", now=12)
        self.queue.complete("events", "worker-a", now=13)
        event_types = [event.event_type for event in self.queue.events("events")]
        self.assertEqual(
            event_types,
            ["TASK_ENQUEUED", "TASK_CLAIMED", "WORKER_HEARTBEAT", "TASK_COMPLETED"],
        )


if __name__ == "__main__":
    unittest.main()
