import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrator"))
sys.path.insert(0, str(ROOT / "serve"))

from local_queue import SQLiteTaskQueue
from worker import A2APlanningHandler, LocalModelChatHandler, LocalWorker


class FakeRuntime:
    def __init__(self, response="local answer"):
        self.config = type("RuntimeConfigStub", (), {"model": "rusa-test:latest"})()
        self.response = response
        self.calls = []

    def complete(self, messages, *, model=None, max_tokens=None, temperature=0.2):
        self.calls.append({
            "messages": messages,
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        return self.response


class LocalWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.queue = SQLiteTaskQueue(Path(self.temp_dir.name) / "worker.sqlite3")

    def test_worker_executes_registered_handler_and_persists_result(self):
        runtime = FakeRuntime("hello from RUSA")
        handler = LocalModelChatHandler(runtime)
        worker = LocalWorker(
            self.queue,
            "worker-model-01",
            {"model.chat": handler},
            lease_seconds=2,
            heartbeat_interval_seconds=0.5,
        )
        self.queue.enqueue(
            "model.chat",
            {"messages": [{"role": "user", "content": "hello"}]},
            task_id="chat-1",
        )
        completed = worker.run_once()
        self.assertEqual(completed.state, "COMPLETED")
        self.assertEqual(completed.result, {
            "response": "hello from RUSA",
            "model": "rusa-test:latest",
        })
        self.assertEqual(runtime.calls[0]["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(self.queue.get("chat-1").result["response"], "hello from RUSA")

    def test_worker_returns_none_when_queue_is_empty(self):
        worker = LocalWorker(self.queue, "worker-idle", {}, lease_seconds=2)
        self.assertIsNone(worker.run_once())

    def test_unregistered_task_type_fails_without_execution(self):
        self.queue.enqueue("shell.exec", {"command": "not allowed"}, task_id="unhandled")
        worker = LocalWorker(self.queue, "worker-no-handler", {}, lease_seconds=2)
        failed = worker.run_once()
        self.assertEqual(failed.state, "FAILED")
        self.assertEqual(failed.last_error, "NoHandlerRegistered:shell.exec")

    def test_handler_exception_uses_bounded_retry_state(self):
        def broken(_payload):
            raise RuntimeError("sensitive traceback should not be persisted")

        self.queue.enqueue("model.chat", {}, task_id="failure", max_attempts=1)
        worker = LocalWorker(
            self.queue,
            "worker-failure",
            {"model.chat": broken},
            lease_seconds=2,
            heartbeat_interval_seconds=0.5,
        )
        failed = worker.run_once()
        self.assertEqual(failed.state, "FAILED")
        self.assertEqual(failed.last_error, "HandlerError:RuntimeError")
        self.assertNotIn("sensitive", failed.last_error)

    def test_worker_renews_lease_during_long_handler(self):
        started = threading.Event()
        release = threading.Event()

        def slow(_payload):
            started.set()
            release.wait(timeout=2)
            return {"ok": True}

        self.queue.enqueue("slow.task", {}, task_id="slow", max_attempts=1)
        worker = LocalWorker(
            self.queue,
            "worker-slow",
            {"slow.task": slow},
            lease_seconds=0.3,
            heartbeat_interval_seconds=0.05,
        )
        result_holder = []
        error_holder = []

        def run():
            try:
                result_holder.append(worker.run_once())
            except Exception as exc:
                error_holder.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(started.wait(timeout=1))
        time.sleep(0.45)
        release.set()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(error_holder, [])
        self.assertEqual(result_holder[0].state, "COMPLETED")
        event_types = [event.event_type for event in self.queue.events("slow")]
        self.assertIn("WORKER_HEARTBEAT", event_types)

    def test_invalid_handler_result_is_failed_not_completed(self):
        self.queue.enqueue("bad.result", {}, task_id="bad-result", max_attempts=1)
        worker = LocalWorker(
            self.queue,
            "worker-bad-result",
            {"bad.result": lambda _payload: {"big": "x" * (1024 * 1024)}},
            lease_seconds=2,
            heartbeat_interval_seconds=0.5,
        )
        failed = worker.run_once()
        self.assertEqual(failed.state, "FAILED")
        self.assertEqual(failed.last_error, "InvalidHandlerResult:ValueError")


    def test_a2a_planning_handler_returns_plan_without_execution(self):
        runtime = FakeRuntime("Step 1: inspect. Step 2: implement. Step 3: test.")
        handler = A2APlanningHandler(runtime)
        task_payload = {
            "envelope": {
                "task_id": "task-uuid",
                "message_id": "message-uuid",
                "task": {
                    "objective": "Add feature safely",
                    "context": "Local-only system",
                    "acceptance_criteria": ["Tests pass", "No main write"],
                    "repository": "Rusa-Ai/RusaAi",
                    "base_branch": "main",
                    "work_branch": "feature/safe-plan",
                },
                "policy": {
                    "allowed_actions": ["analyze", "plan"],
                    "prohibited_actions": ["merge", "deploy"],
                    "human_approval_required": ["merge", "deploy"],
                },
            }
        }
        result = handler(task_payload)
        self.assertEqual(result["status"], "planning_result")
        self.assertEqual(result["plan"], "Step 1: inspect. Step 2: implement. Step 3: test.")
        self.assertFalse(result["execution_performed"])
        self.assertEqual(runtime.calls[0]["temperature"], 0.2)
        self.assertIn("acceptance_criteria", runtime.calls[0]["messages"][1]["content"])

    def test_a2a_planning_handler_rejects_unstructured_payload(self):
        handler = A2APlanningHandler(FakeRuntime())
        with self.assertRaisesRegex(ValueError, "validated task envelope"):
            handler({"objective": "not an envelope"})

    def test_worker_rejects_invalid_lease_configuration(self):
        with self.assertRaises(ValueError):
            LocalWorker(self.queue, "", {}, lease_seconds=2)
        with self.assertRaises(ValueError):
            LocalWorker(self.queue, "worker", {}, lease_seconds=2, heartbeat_interval_seconds=2)
        with self.assertRaises(ValueError):
            LocalWorker(self.queue, "worker", {}, lease_seconds=float("nan"))


if __name__ == "__main__":
    unittest.main()
