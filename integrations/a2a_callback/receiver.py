#!/usr/bin/env python3
"""Authenticated local callback inbox for RUSA-AI A2A task events.

The service binds to loopback by default. Expose it only behind a separately
configured TLS/authenticated gateway after a security review.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

MAX_BODY_BYTES = 1_048_576
ALLOWED_EVENTS = {"task.accepted", "task.progress", "task.completed", "task.failed"}
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def verify_signature(timestamp, raw_body, supplied_signature, secret, now=None, tolerance=300):
    if not timestamp or not supplied_signature or not secret:
        return False
    if not isinstance(timestamp, str) or not re.fullmatch(r"[0-9]{1,12}", timestamp):
        return False
    if not isinstance(supplied_signature, str) or not re.fullmatch(r"[0-9a-f]{64}", supplied_signature):
        return False
    try:
        stamp = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int(time.time() if now is None else now)
    if abs(current - stamp) > tolerance:
        return False
    signed = timestamp.encode("ascii") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied_signature)


def validate_callback(payload):
    if not isinstance(payload, dict):
        raise ValueError("callback must be a JSON object")
    required = ("protocol_version", "message_id", "task_id", "type", "from", "to", "created_at")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError("missing fields: " + ", ".join(missing))
    if payload["protocol_version"] != "1.0":
        raise ValueError("unsupported protocol_version")
    for key in ("message_id", "task_id"):
        value = payload[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
    if not TASK_ID_PATTERN.fullmatch(payload["task_id"]):
        raise ValueError("task_id contains invalid characters")
    if not isinstance(payload["type"], str) or payload["type"] not in ALLOWED_EVENTS:
        raise ValueError("unsupported callback type")
    for key in ("from", "to"):
        agent = payload[key]
        if not isinstance(agent, dict) or not isinstance(agent.get("agent_id"), str) or not agent["agent_id"].strip():
            raise ValueError(f"{key}.agent_id is required")
        if not isinstance(agent.get("role"), str) or not agent["role"].strip():
            raise ValueError(f"{key}.role is required")
    if payload["from"]["role"] != "github_copilot":
        raise ValueError("callback sender role must be github_copilot")
    if payload["to"]["role"] != "a2a_gateway":
        raise ValueError("callback recipient role must be a2a_gateway")
    if not isinstance(payload["created_at"], str) or not payload["created_at"].strip():
        raise ValueError("created_at must be a non-empty string")
    for key in ("result", "evidence"):
        if key in payload and not isinstance(payload[key], (dict, list)):
            raise ValueError(f"{key} must be an object or array")
    return payload


class CallbackStore:
    def __init__(self, database_path):
        self.database_path = database_path
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS callbacks (
                    message_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    received_at TEXT NOT NULL
                )
            """)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_callbacks_task_received "
                "ON callbacks(task_id, received_at)"
            )

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def insert(self, payload):
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        received_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO callbacks "
                "(message_id, task_id, event_type, payload_json, received_at) VALUES (?, ?, ?, ?, ?)",
                (payload["message_id"], payload["task_id"], payload["type"], serialized, received_at),
            )
            return cursor.rowcount == 1

    def list_for_task(self, task_id):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json, received_at FROM callbacks "
                "WHERE task_id = ? ORDER BY received_at, message_id",
                (task_id,),
            ).fetchall()
        return [
            {"payload": json.loads(row["payload_json"]), "received_at": row["received_at"]}
            for row in rows
        ]


def make_handler(store, hmac_secret, read_token):
    class CallbackHandler(BaseHTTPRequestHandler):
        server_version = "RUSA-AI-Callback/0.1"

        def _json(self, status, value):
            encoded = json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self):
            if self.path != "/v1/callbacks":
                return self._json(404, {"error": "not_found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._json(400, {"error": "invalid_content_length"})
            if length <= 0 or length > MAX_BODY_BYTES:
                return self._json(413, {"error": "invalid_body_size"})
            raw_body = self.rfile.read(length)
            timestamp = self.headers.get("X-RUSA-Timestamp", "")
            signature = self.headers.get("X-RUSA-Signature", "")
            if not verify_signature(timestamp, raw_body, signature, hmac_secret):
                return self._json(401, {"error": "invalid_signature_or_timestamp"})
            try:
                payload = validate_callback(json.loads(raw_body))
            except (ValueError, json.JSONDecodeError) as error:
                return self._json(400, {"error": str(error)})
            inserted = store.insert(payload)
            return self._json(202, {
                "status": "accepted",
                "duplicate": not inserted,
                "message_id": payload["message_id"],
                "task_id": payload["task_id"],
            })

        def do_GET(self):
            prefix, suffix = "/v1/tasks/", "/callbacks"
            if not self.path.startswith(prefix) or not self.path.endswith(suffix):
                return self._json(404, {"error": "not_found"})
            expected = "Bearer " + read_token if read_token else ""
            if not expected or not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
                return self._json(401, {"error": "unauthorized"})
            task_id = unquote(self.path[len(prefix):-len(suffix)])
            if not TASK_ID_PATTERN.fullmatch(task_id):
                return self._json(400, {"error": "invalid_task_id"})
            return self._json(200, {"task_id": task_id, "callbacks": store.list_for_task(task_id)})

        def log_message(self, format_string, *args):
            # Avoid logging request headers or payloads; retain minimal access logs.
            super().log_message(format_string, *args)

    return CallbackHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind address; loopback is the safe default")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", default="rusa_callbacks.sqlite3")
    args = parser.parse_args()
    hmac_secret = os.environ.get("RUSA_CALLBACK_HMAC_SECRET", "")
    read_token = os.environ.get("RUSA_CALLBACK_READ_TOKEN", "")
    if len(hmac_secret) < 32 or len(read_token) < 24:
        parser.error("Set RUSA_CALLBACK_HMAC_SECRET (32+ chars) and RUSA_CALLBACK_READ_TOKEN (24+ chars)")
    store = CallbackStore(args.database)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store, hmac_secret, read_token))
    print(f"RUSA-AI callback inbox listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
