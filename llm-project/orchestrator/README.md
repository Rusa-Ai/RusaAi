# RUSA-AI Local Durable Task Queue (P2 foundation)

This module provides a file-backed SQLite task queue for local orchestration.
It persists task state and lifecycle events, and provides exclusive worker
claims through SQLite write transactions.

## Capabilities

- Idempotent task creation using a caller-supplied task ID.
- Priority-based claiming with incrementing attempt counts.
- Worker leases and explicit heartbeat renewal.
- Completion and failure transitions with bounded retry budgets.
- Automatic expired-lease reclamation on claim, plus explicit maintenance method.
- Cancellation with lease release.
- Append-only task lifecycle event records.
- SQLite WAL mode and a configurable busy timeout for concurrent local workers.

## Minimal use

```python
from local_queue import SQLiteTaskQueue

queue = SQLiteTaskQueue("./var/rusa-tasks.sqlite3")
task = queue.enqueue(
    "project.code_change",
    {"repository": "Rusa-Ai/RusaAi", "objective": "implement scoped change"},
    max_attempts=3,
)
claimed = queue.claim("engineering-worker-02", lease_seconds=60)
if claimed is not None:
    # Execute only a policy-approved task in a separate isolated executor.
    queue.heartbeat(claimed.task_id, "engineering-worker-02", lease_seconds=60)
    queue.complete(claimed.task_id, "engineering-worker-02")
```

Run from the repository root after adding the orchestrator directory to
`PYTHONPATH`, or import it from the local orchestrator package in a future
integration layer.

## Test

```bash
python -m unittest discover -s llm-project/tests -p "test_local_queue.py" -v
```

## Security boundary and limitations

- The queue stores task contracts and state only; it does not execute code.
- This module does not create worker processes, sandbox tasks, access GitHub,
  launch a model, or communicate over A2A.
- Do not place secrets, credentials, raw private datasets, or sensitive prompts
  in task payloads or error fields.
- Workers must still validate task scope, permissions, cancellation, and
  approval policy before invoking tools.
- SQLite supports a local single-machine deployment model. This is not a
  distributed multi-host queue.
- A task may be delivered again after a crash or lease expiry. Worker handlers
  must therefore be idempotent and must record external side effects.

Evidence status: queue implementation is included in this PR; unit-test
execution requires the attached GitHub Actions run. Live multi-process crash
recovery and filesystem backup/restore require a target-machine test.
