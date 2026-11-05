#!/usr/bin/env python3
"""Authenticated local callback inbox for RUSA-AI A2A task events.

The service binds to loopback by default. Expose it only behind a separately
configured TLS/authenticated gateway after a security review.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

MAX_BODY_BYTES = 1_048_576
MAX_PAGE_SIZE = 100
ALLOWED_EVENTS = {"task.accepted", "task.progress", "task.completed", "task.failed"}
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MESSAGE_ID_PATTERN = TASK_ID_PATTERN


class IdempotencyConflict(Exception):
    """A previously used message ID was reused for different callback content."""


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


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


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
    if not MESSAGE_ID_PATTERN.fullmatch(payload["message_id"]):
        raise ValueError("message_id contains invalid characters")
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
    created_at = payload["created_at"]
    if not isinstance(created_at, str) or not created_at.strip():
        raise ValueError("created_at must be a non-empty timestamp")
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("created_at must be an ISO-8601 timestamp") from error
    if parsed_created_at.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    for key in ("result", "evidence"):
        if key in payload and not isinstance(payload[key], (dict, list)):
            raise ValueError(f"{key} must be an object or array")
    return payload


def _encode_cursor(received_at, message_id):
    raw = json.dumps([received_at, message_id], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor):
    if not cursor or len(cursor) > 1024:
        raise ValueError("invalid cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
    except (ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid cursor") from error
    if (not isinstance(decoded, list) or len(decoded) != 2 or
            not all(isinstance(part, str) for part in decoded) or
            not MESSAGE_ID_PATTERN.fullmatch(decoded[1])):
        raise ValueError("invalid cursor")
    return decoded[0], decoded[1]


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
                "ON callbacks(task_id, received_at, message_id)"
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
            if cursor.rowcount == 1:
                return True
            existing = connection.execute(
                "SELECT task_id, payload_json FROM callbacks WHERE message_id = ?",
                (payload["message_id"],),
            ).fetchone()
            if existing is None or existing["task_id"] != payload["task_id"] or existing["payload_json"] != serialized:
                raise IdempotencyConflict("message_id already exists with different callback content")
            return False

    def page_for_task(self, task_id, limit=MAX_PAGE_SIZE, cursor=None):
        params = [task_id]
        cursor_clause = ""
        if cursor is not None:
            received_at, message_id = _decode_cursor(cursor)
            cursor_clause = " AND (received_at > ? OR (received_at = ? AND message_id > ?))"
            params.extend((received_at, received_at, message_id))
        params.append(limit + 1)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json, received_at, message_id FROM callbacks "
                "WHERE task_id = ?" + cursor_clause +
                " ORDER BY received_at, message_id LIMIT ?",
                params,
            ).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        records = [
            {"payload": json.loads(row["payload_json"]), "received_at": row["received_at"]}
            for row in rows
        ]
        next_cursor = _encode_cursor(rows[-1]["received_at"], rows[-1]["message_id"]) if has_more and rows else None
        return records, next_cursor


def make_handler(store, hmac_secret, read_token):
    class CallbackHandler(BaseHTTPRequestHandler):
        server_version = "RUSA-AI-Callback"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def _json(self, status, value):
            encoded = json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def handle_expect_100(self):
            return self._json(417, {"error": "expectation_not_supported"})

        def do_POST(self):
            if urlsplit(self.path).path != "/v1/callbacks":
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
            if not verify_signature(timestamp, raw_body, signature, hmac_secret):
                return self._json(401, {"error": "invalid_signature_or_timestamp"})
            try:
                payload = validate_callback(json.loads(raw_body, object_pairs_hook=_reject_duplicate_json_keys))
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
                return self._json(400, {"error": str(error)})
            try:
                inserted = store.insert(payload)
            except IdempotencyConflict:
                return self._json(409, {"error": "message_id_conflict"})
            except sqlite3.Error:
                return self._json(503, {"error": "storage_unavailable"})
            return self._json(202, {
                "status": "accepted",
                "duplicate": not inserted,
                "message_id": payload["message_id"],
                "task_id": payload["task_id"],
            })

        def do_GET(self):
            parsed_path = urlsplit(self.path)
            prefix, suffix = "/v1/tasks/", "/callbacks"
            if not parsed_path.path.startswith(prefix) or not parsed_path.path.endswith(suffix):
                return self._json(404, {"error": "not_found"})
            expected = "Bearer " + read_token if read_token else ""
            if not expected or not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
                return self._json(401, {"error": "unauthorized"})
            task_id = unquote(parsed_path.path[len(prefix):-len(suffix)])
            if not TASK_ID_PATTERN.fullmatch(task_id):
                return self._json(400, {"error": "invalid_task_id"})
            try:
                query = parse_qs(parsed_path.query, strict_parsing=True, max_num_fields=2)
            except ValueError:
                return self._json(400, {"error": "invalid_query"})
            if set(query) - {"limit", "cursor"} or any(len(values) != 1 for values in query.values()):
                return self._json(400, {"error": "invalid_query"})
            try:
                limit = int(query.get("limit", [str(MAX_PAGE_SIZE)])[0])
            except ValueError:
                return self._json(400, {"error": "invalid_limit"})
            if limit < 1 or limit > MAX_PAGE_SIZE:
                return self._json(400, {"error": "invalid_limit"})
            cursor = query.get("cursor", [None])[0]
            try:
                callbacks, next_cursor = store.page_for_task(task_id, limit, cursor)
            except ValueError:
                return self._json(400, {"error": "invalid_cursor"})
            except sqlite3.Error:
                return self._json(503, {"error": "storage_unavailable"})
            return self._json(200, {"task_id": task_id, "callbacks": callbacks, "next_cursor": next_cursor})

        def log_message(self, format_string, *args):
            # Avoid logging paths, request headers, or potentially sensitive task IDs.
            return

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
