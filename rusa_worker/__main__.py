"""Safe bootstrap entry point; real processing stays disabled without adapters."""

import argparse
import json

from .config import WorkerConfig
from .providers import FlexibleProvider, GenerationRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="RusaAI worker bootstrap")
    parser.add_argument("--dry-run", action="store_true", help="validate configuration without claiming tasks")
    args = parser.parse_args()

    try:
        config = WorkerConfig.from_env()
    except ValueError as exc:
        parser.error(str(exc))

    if args.dry_run:
        print(json.dumps({
            "status": "CONFIG_VALID",
            "runtime": "github-actions-compatible",
            "model_provider": config.model_provider,
            "model_name": config.model_name,
            "environment": config.environment,
            "task_execution": "disabled",
            "reason": "durable queue and concrete model adapter are not configured",
        }, sort_keys=True))
        return 0

    # Fail closed: never pretend that a task was processed without real adapters.
    try:
        FlexibleProvider().generate(GenerationRequest(task_id="bootstrap", prompt=""))
    except RuntimeError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
