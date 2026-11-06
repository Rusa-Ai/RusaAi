# RUSA-AI Local Worker Runtime (P3 first executor)

This module is a local worker process that polls the SQLite task queue and runs
only explicitly registered task types. The first and only built-in handler is
`model.chat`, which calls the loopback-only model adapter.

## Start

Set the same environment variables documented by the local inference runtime:

```bash
export RUSA_QUEUE_DB="./var/rusa-tasks.sqlite3"
export RUSA_WORKER_ID="rusa-local-worker-01"
export RUSA_MODEL_NAME="your-installed-model-id"
export RUSA_MODEL_BASE_URL="http://127.0.0.1:11434/v1"
```

Run one task or keep a local process polling:

```bash
python llm-project/orchestrator/worker.py run-once
python llm-project/orchestrator/worker.py serve
```

For a long-running process, stop it with SIGINT or SIGTERM. The worker renews
its lease while a registered handler is running. If the process exits, the
queue reclaims expired leases according to the task's bounded retry budget.

## Enqueue a model chat task

From Python at the repository root:

```python
import sys
sys.path.insert(0, "llm-project/orchestrator")
from local_queue import SQLiteTaskQueue

queue = SQLiteTaskQueue("./var/rusa-tasks.sqlite3")
queue.enqueue(
    "model.chat",
    {
        "messages": [{"role": "user", "content": "Introduce RUSA-AI."}],
        "max_tokens": 256,
        "temperature": 0.2
    },
    task_id="demo-model-chat-001",
    max_attempts=2
)
```

After a worker claims and completes the task, read its result:

```python
task = queue.get("demo-model-chat-001")
print(task.state, task.result)
```

## Safety boundary

- Only registered handler names execute. There is no generic shell, Python,
  repository write, or arbitrary command handler.
- The initial built-in handler is model inference only.
- Model inference remains on loopback; a model must be installed separately.
- Task results are bounded JSON data stored in the local SQLite DB.
- Handler exceptions are persisted as exception class names only, not tracebacks.
- Leases provide at-least-once execution, not exactly-once side effects. Handler
  implementations must be idempotent.
- This is a local single-machine worker; it does not provide public A2A ingress,
  GitHub Copilot dispatch, sandboxed code editing, or production monitoring.
- Human approval is still required before adding dangerous handlers, writing
  to external systems, merging code, or deploying.

## Tests

```bash
python -m unittest discover -s llm-project/tests -p "test_local_worker.py" -v
```
