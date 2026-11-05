#!/usr/bin/env python3
"""Send a signed RUSA-AI A2A callback to the local callback inbox."""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

from receiver import validate_callback


def send_callback(endpoint, payload, secret, now=None, timeout=10):
    if len(secret) < 32:
        raise ValueError("HMAC secret must contain at least 32 characters")
    validate_callback(payload)
    raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    timestamp = str(int(time.time() if now is None else now))
    signed = timestamp.encode("ascii") + b"." + raw_body
    signature = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/v1/callbacks",
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-RUSA-Timestamp": timestamp,
            "X-RUSA-Signature": signature,
            "User-Agent": "rusa-ai-a2a-callback-sender/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Callback endpoint returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Callback endpoint unavailable: {error.reason}") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="Base URL of the callback inbox")
    parser.add_argument("--input", default="-", help="Callback JSON file; default stdin")
    args = parser.parse_args()
    secret = os.environ.get("RUSA_CALLBACK_HMAC_SECRET", "")
    if len(secret) < 32:
        parser.error("Set RUSA_CALLBACK_HMAC_SECRET (32+ chars) in the environment")
    try:
        raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
        payload = json.loads(raw)
        result = send_callback(args.endpoint, payload, secret)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"A2A callback sender error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
