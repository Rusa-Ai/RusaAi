"""Authenticated local A2A task intake bridge for the RUSA-AI SQLite queue.

Accepts only task.create envelopes addressed to the local RUSA orchestrator.
The first registered consumer is an analysis/planning worker; this HTTP service
does not authorize repository writes, shell execution, merges, or deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import sqlite3
import signal
import sys
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from local_queue import QueueConflict, QueueError, SQLiteTaskQueue

MAX_BODY_BYTES = 1_048_576
SIGNATURE_TOLERANCE_SECONDS = 300
_REQUIRED_APPROVALS = {
    "merge",
    "deploy",
    "release",
    "secret_change",
    "permission_change",
    "destructive_action",
}
_ALLOWED_ROLES = {"human", "chatgpt_app", "github_copilot"}
_TOP_LEVEL_KEYS = {
    "protocol_version", "task_id", "message_id", "type", "from", "to",
    "created_at", "task", "policy", "status", "evidence",
}
_TASK_KEYS = {
    "objective", "context", "acceptance_criteria", "repository",
    "base_branch", "work_branch",
}
_TASK_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_WORK_BRANCH_PATTERN = re.compile(r"^(feature|fix|chore|docs)/[A-Za-z0-9._/-]+$")


class A2AValidationError(ValueError):
    """Raised for invalid or unsupported A2A task envelopes."""


class A2AIngressError(RuntimeError):
    """Raised when a task cannot be safely accepted."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise A2AValidationError("duplicate JSON object key")
        result[key] = value
    return result


def _parse_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise A2AValidationError(f"{field_name} must be a UUID string")
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise A2AValidationError(f"{field_name} must be a UUID string") from exc


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise A2AValidationError("created_at must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise A2AValidationError("created_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise A2AValidationError("created_at must include a timezone")


def validate_task_envelope(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise A2AValidationError("task envelope must be a JSON object")
    if set(payload) - _TOP_LEVEL_KEYS:
        raise A2AValidationError("task envelope contains unsupported top-level fields")
    required = {
        "protocol_version", "task_id", "message_id", "type", "from", "to",
        "created_at", "task", "policy",
    }
    missing = required - set(payload)
    if missing:
        raise A2AValidationError("missing required fields: " + ", ".join(sorted(missing)))
    if payload["protocol_version"] != "1.0":
        raise A2AValidationError("unsupported protocol_version")
    task_id = _parse_uuid(payload["task_id"], "task_id")
    message_id = _parse_uuid(payload["message_id"], "message_id")
    if payload["type"] != "task.create":
        raise A2AValidationError("only task.create envelopes are accepted")
    _validate_timestamp(payload["created_at"])

    for field, expected_role in (("from", None), ("to", "rusa_orchestrator")):
        agent = payload[field]
        if not isinstance(agent, dict) or set(agent) != {"agent_id", "role"}:
            raise A2AValidationError(f"{field} must contain only agent_id and role")
        if not isinstance(agent["agent_id"], str) or not agent["agent_id"].strip():
            raise A2AValidationError(f"{field}.agent_id must be non-empty")
        if not isinstance(agent["role"], str) or not agent["role"].strip():
            raise A2AValidationError(f"{field}.role must be non-empty")
        if field == "from" and agent["role"] not in _ALLOWED_ROLES:
            raise A2AValidationError("unsupported sender role")
        if expected_role and agent["role"] != expected_role:
            raise A2AValidationError("recipient role must be rusa_orchestrator")

    task = payload["task"]
    if not isinstance(task, dict) or set(task) - _TASK_KEYS:
        raise A2AValidationError("task must be an object with only supported task fields")
    task_required = {"objective", "acceptance_criteria", "repository", "base_branch", "work_branch"}
    if task_required - set(task):
        raise A2AValidationError("task is missing required fields")
    objective = task["objective"]
    if not isinstance(objective, str) or not objective.strip() or len(objective) > 8000:
        raise A2AValidationError("task.objective must contain 1-8000 characters")
    if "context" in task and (
        not isinstance(task["context"], str) or len(task["context"]) > 20000
    ):
        raise A2AValidationError("task.context must be a string no longer than 20000 characters")
    criteria = task["acceptance_criteria"]
    if (
        not isinstance(criteria, list)
        or not criteria
        or any(not isinstance(item, str) or not item.strip() for item in criteria)
    ):
        raise A2AValidationError("acceptance_criteria must be a non-empty string array")
    repository = task["repository"]
    if not isinstance(repository, str) or not _REPOSITORY_PATTERN.fullmatch(repository):
        raise A2AValidationError("task.repository must use owner/repository form")
    owner, repository_name = repository.split("/", 1)
    if owner in {".", ".."} or repository_name in {".", ".."}:
        raise A2AValidationError("task.repository contains an unsafe path segment")
    if not isinstance(task["base_branch"], str) or not task["base_branch"].strip():
        raise A2AValidationError("task.base_branch must be non-empty")
    work_branch = task["work_branch"]
    if not isinstance(work_branch, str) or not _WORK_BRANCH_PATTERN.fullmatch(work_branch):
        raise A2AValidationError("task.work_branch must use feature/, fix/, chore/, or docs/ prefix")
    if any(part in {".", ".."} for part in work_branch.split("/")):
        raise A2AValidationError("task.work_branch contains an unsafe path segment")

    policy = payload["policy"]
    if not isinstance(policy, dict) or set(policy) != {
        "allowed_actions", "prohibited_actions", "human_approval_required"
    }:
        raise A2AValidationError("policy must contain allowed_actions, prohibited_actions, and human_approval_required")
    for key in ("allowed_actions", "prohibited_actions", "human_approval_required"):
        if not isinstance(policy[key], list) or any(
            not isinstance(item, str) or not item.strip() for item in policy[key]
        ):
            raise A2AValidationError(f"policy.{key} must be a string array")
    if not _REQUIRED_APPROVALS.issubset(set(policy["human_approval_required"])):
        raise A2AValidationError("policy must require human approval for merge, deploy, release, secret, permission, and destructive actions")

    if "status" in payload and payload["status"] not in {
        "proposed", "accepted", "in_progress", "submitted", "reviewing",
        "approved", "changes_requested", "blocked", "cancelled",
    }:
        raise A2AValidationError("unsupported task status")
    if "evidence" in payload:
        if not isinstance(payload["evidence"], list):
            raise A2AValidationError("evidence must be an array")
        for item in payload["evidence"]:
            if not isinstance(item, dict) or set(item) - {"kind", "uri", "sha", "description"}:
                raise A2AValidationError("evidence entries contain unsupported fields")
            if not isinstance(item.get("kind"), str) or not isinstance(item.get("uri"), str):
                raise A2AValidationError("evidence entries require kind and uri strings")

    normalized = dict(payload)
    normalized["task_id"] = task_id
    normalized["message_id"] = message_id
    return normalized


def verify_request_signature(
    timestamp: str,
    raw_body: bytes,
    supplied_signature: str,
    secret: str,
    *,
    now: float | None = None,
    tolerance_seconds: int = SIGNATURE_TOLERANCE_SECONDS,
) -> bool:
    if not timestamp or not supplied_signature or len(secret) < 32:
        return False
    if not re.fullmatch(r"[0-9]{1,12}", timestamp):
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", supplied_signature):
        return False
    stamp = int(timestamp)
    current = int(time.time() if now is None else now)
    if abs(current - stamp) > tolerance_seconds:
        return False
    signed = timestamp.encode("ascii") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied_signature)


def _canonical_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def enqueue_a2a_task(queue: SQLiteTaskQueue, envelope: dict[str, Any]):
    task_payload = {
        "a2a_message_id": envelope["message_id"],
        "envelope": envelope,
        "requested_execution": "planning_only",
    }
    return queue.enqueue(
        "a2a.plan",
        task_payload,
        task_id=envelope["task_id"],
        priority=10,
        max_attempts=3,
    )


def make_handler(
    queue: SQLiteTaskQueue,
    hmac_secret: str,
    *,
    now_provider: Callable[[], float] = time.time,
):
    if len(hmac_secret) < 32:
        raise ValueError("HMAC secret must contain at least 32 characters")

    class A2AIngressHandler(BaseHTTPRequestHandler):
        server_version = "RUSA-AI-A2A-Ingress"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def _json(self, status: int, value: dict[str, Any]):
            encoded = json.dumps(value, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def handle_expect_100(self):
            self._json(417, {"error": "expectation_not_supported"})
            return False

        def do_POST(self):
            if urlsplit(self.path).path != "/v1/tasks":
                return self._json(404, {"error": "not_found"})
            if self.headers.get("Transfer-Encoding"):
                return self._json(400, {"error": "transfer_encoding_not_supported"})
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                return self._json(415, {"error": "unsupported_media_type"})
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return self._json(411, {"error": "content_length_required"})
            try:
                length = int(raw_length)
            except ValueError:
                return self._json(400, {"error": "invalid_content_length"})
            if length <= 0:
                return self._json(400, {"error": "invalid_body_size"})
            if length > MAX_BODY_BYTES:
                return self._json(413, {"error": "body_too_large"})
            try:
                raw_body = self.rfile.read(length)
            except OSError:
                return self._json(408, {"error": "request_body_timeout"})
            if len(raw_body) != length:
                return self._json(400, {"error": "incomplete_request_body"})

            timestamp = self.headers.get("X-RUSA-Timestamp", "")
            signature = self.headers.get("X-RUSA-Signature", "")
            if not verify_request_signature(
                timestamp,
                raw_body,
                signature,
                hmac_secret,
                now=now_provider(),
            ):
                return self._json(401, {"error": "invalid_signature_or_timestamp"})
            try:
                payload = json.loads(
                    raw_body.decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
                envelope = validate_task_envelope(payload)
                existing = None
                try:
                    existing = queue.get(envelope["task_id"])
                except QueueError:
                    pass
                task = enqueue_a2a_task(queue, envelope)
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc)})
            except QueueConflict:
                return self._json(409, {"error": "task_id_conflict"})
            except (OSError, sqlite3.Error):
                return self._json(503, {"error": "queue_storage_unavailable"})

            return self._json(
                202,
                {
                    "status": "accepted",
                    "duplicate": existing is not None,
                    "task_id": task.task_id,
                    "message_id": envelope["message_id"],
                    "queue_state": task.state,
                    "execution_mode": "planning_only",
                },
            )

        def log_message(self, format_string, *args):
            return

    return A2AIngressHandler


def validate_loopback_host(host: str) -> None:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise ValueError("A2A ingress may bind only to localhost or a loopback IP") from exc
    if not address.is_loopback:
        raise ValueError("A2A ingress may bind only to localhost or a loopback IP")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RUSA-AI authenticated local A2A task ingress")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--database", default=os.getenv("RUSA_QUEUE_DB", "./var/rusa-tasks.sqlite3"))
    args = parser.parse_args(argv)

    secret = os.getenv("RUSA_A2A_INGRESS_HMAC_SECRET", "")
    if len(secret) < 32:
        parser.error("Set RUSA_A2A_INGRESS_HMAC_SECRET to a secret of at least 32 characters")
    try:
        validate_loopback_host(args.host)
        queue = SQLiteTaskQueue(Path(args.database))
        server = ThreadingHTTPServer((args.host, args.port), make_handler(queue, secret))
        server.daemon_threads = True
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": type(exc).__name__}), file=sys.stderr)
        return 2

    def stop(_signum: int, _frame: Any):
        server.shutdown()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
