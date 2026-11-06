"""Send a signed A2A task to the loopback-only RUSA-AI local ingress."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from a2a_ingress import _canonical_payload, validate_loopback_host, validate_task_envelope


class A2ASenderError(RuntimeError):
    """Raised when the local A2A task cannot be sent or accepted."""


def send_task(
    endpoint: str,
    envelope: dict[str, Any],
    secret: str,
    *,
    now: float | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    if len(secret) < 32:
        raise ValueError("HMAC secret must contain at least 32 characters")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    parsed = urllib.parse.urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("endpoint must be a plain HTTP loopback base URL without credentials or path")
    validate_loopback_host(parsed.hostname)
    validated = validate_task_envelope(envelope)
    raw_body = _canonical_payload(validated).encode("utf-8")
    timestamp = str(int(time.time() if now is None else now))
    signature = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("ascii") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/v1/tasks",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-RUSA-Timestamp": timestamp,
            "X-RUSA-Signature": signature,
            "User-Agent": "rusa-ai-local-a2a-sender/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_response = response.read(65_537)
            if len(raw_response) > 65_536:
                raise A2ASenderError("A2A ingress response exceeded the 64 KiB limit")
    except urllib.error.HTTPError as exc:
        raise A2ASenderError(f"A2A ingress rejected the task with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise A2ASenderError("A2A local ingress is unavailable") from exc
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise A2ASenderError("A2A ingress returned an invalid JSON response") from exc
    if not isinstance(payload, dict):
        raise A2ASenderError("A2A ingress returned an unexpected response")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8766")
    parser.add_argument("--input", default="-", help="A2A task envelope JSON file; default stdin")
    args = parser.parse_args(argv)
    secret = os.getenv("RUSA_A2A_INGRESS_HMAC_SECRET", "")
    if len(secret) < 32:
        parser.error("Set RUSA_A2A_INGRESS_HMAC_SECRET to at least 32 characters")
    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        envelope = json.loads(raw)
        result = send_task(args.endpoint, envelope, secret)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, A2ASenderError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"error": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
