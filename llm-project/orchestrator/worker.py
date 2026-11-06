"""Local RUSA-AI worker process for registered, policy-approved task handlers.

Only explicitly registered task types are executable. The initial handler is
model.chat, which delegates to the loopback-only local inference adapter.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sys
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_SERVE = _HERE.parent / "serve"
for _path in (_HERE, _SERVE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from local_queue import QueueConflict, SQLiteTaskQueue, Task
from local_runtime import LocalOpenAICompatibleRuntime, RuntimeConfig


TaskHandler = Callable[[dict[str, Any]], Any]


class LocalModelChatHandler:
    """Runs a chat task using the configured loopback-only model runtime."""

    def __init__(self, runtime: LocalOpenAICompatibleRuntime):
        self.runtime = runtime

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise ValueError("model.chat payload requires a messages array")
        model = payload.get("model")
        max_tokens = payload.get("max_tokens")
        temperature = payload.get("temperature", 0.2)
        response = self.runtime.complete(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return {
            "response": response,
            "model": model or self.runtime.config.model,
        }


class LocalWorker:
    """Claims tasks, runs registered handlers, renews leases, and stores results."""

    def __init__(
        self,
        queue: SQLiteTaskQueue,
        worker_id: str,
        handlers: Mapping[str, TaskHandler],
        *,
        lease_seconds: float = 180.0,
        heartbeat_interval_seconds: float | None = None,
    ):
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a non-empty string")
        if len(worker_id) > 128:
            raise ValueError("worker_id must be at most 128 characters")
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be finite and positive")
        heartbeat_interval = (
            heartbeat_interval_seconds
            if heartbeat_interval_seconds is not None
            else lease_seconds / 3
        )
        if (
            not math.isfinite(heartbeat_interval)
            or heartbeat_interval <= 0
            or heartbeat_interval >= lease_seconds
        ):
            raise ValueError("heartbeat interval must be finite, positive, and shorter than the lease")

        self.queue = queue
        self.worker_id = worker_id.strip()
        self.handlers = dict(handlers)
        self.lease_seconds = float(lease_seconds)
        self.heartbeat_interval_seconds = float(heartbeat_interval)

    def _start_heartbeat(self, task: Task) -> tuple[threading.Event, threading.Thread, list[Exception]]:
        stop_event = threading.Event()
        failures: list[Exception] = []

        def renew() -> None:
            while not stop_event.wait(self.heartbeat_interval_seconds):
                try:
                    self.queue.heartbeat(
                        task.task_id,
                        self.worker_id,
                        lease_seconds=self.lease_seconds,
                    )
                except Exception as exc:
                    failures.append(exc)
                    stop_event.set()
                    return

        thread = threading.Thread(
            target=renew,
            name="rusa-heartbeat-" + self.worker_id,
            daemon=True,
        )
        thread.start()
        return stop_event, thread, failures

    def run_once(self) -> Task | None:
        task = self.queue.claim(
            self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if task is None:
            return None

        handler = self.handlers.get(task.task_type)
        if handler is None:
            return self.queue.fail(
                task.task_id,
                self.worker_id,
                f"NoHandlerRegistered:{task.task_type[:120]}",
            )

        stop_event, heartbeat_thread, heartbeat_failures = self._start_heartbeat(task)
        try:
            result = handler(task.payload)
        except Exception as exc:
            stop_event.set()
            heartbeat_thread.join()
            if heartbeat_failures:
                raise QueueConflict("worker lost its lease while handling a task") from heartbeat_failures[0]
            return self.queue.fail(
                task.task_id,
                self.worker_id,
                f"HandlerError:{type(exc).__name__}",
            )

        stop_event.set()
        heartbeat_thread.join()
        if heartbeat_failures:
            raise QueueConflict("worker lost its lease before persisting the task result") from heartbeat_failures[0]
        try:
            return self.queue.complete(
                task.task_id,
                self.worker_id,
                result=result,
            )
        except ValueError as exc:
            return self.queue.fail(
                task.task_id,
                self.worker_id,
                f"InvalidHandlerResult:{type(exc).__name__}",
            )

    def serve(self, stop_event: threading.Event, *, poll_interval_seconds: float = 1.0) -> None:
        if not math.isfinite(poll_interval_seconds) or poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be finite and positive")
        while not stop_event.is_set():
            task = self.run_once()
            if task is None:
                stop_event.wait(poll_interval_seconds)


def build_worker_from_env() -> LocalWorker:
    queue_path = os.getenv("RUSA_QUEUE_DB", "./var/rusa-tasks.sqlite3")
    worker_id = os.getenv("RUSA_WORKER_ID", "rusa-local-worker-01")
    lease_seconds = float(os.getenv("RUSA_WORKER_LEASE_SECONDS", "180"))
    queue = SQLiteTaskQueue(queue_path)
    runtime = LocalOpenAICompatibleRuntime(RuntimeConfig.from_env())
    return LocalWorker(
        queue,
        worker_id,
        {"model.chat": LocalModelChatHandler(runtime)},
        lease_seconds=lease_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RUSA-AI local registered-task worker")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run-once", help="claim and process at most one task")
    serve_parser = commands.add_parser("serve", help="poll the local queue until interrupted")
    serve_parser.add_argument("--poll-interval", type=float, default=1.0)
    try:
        args = parser.parse_args(argv)
        worker = build_worker_from_env()
        if args.command == "run-once":
            task = worker.run_once()
            if task is None:
                print(json.dumps({"status": "IDLE"}))
            else:
                print(json.dumps({"task_id": task.task_id, "state": task.state}))
            return 0

        stop_event = threading.Event()

        def request_stop(_signum: int, _frame: Any) -> None:
            stop_event.set()

        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)
        worker.serve(stop_event, poll_interval_seconds=args.poll_interval)
        return 0
    except (ValueError, QueueConflict, OSError) as exc:
        print(json.dumps({"error": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
