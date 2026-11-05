import hashlib
import hmac
import json
import tempfile
import unittest
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from receiver import CallbackStore, IdempotencyConflict, make_handler, validate_callback, verify_signature
from sender import send_callback


def sample(message_id="msg-001"):
    return {
        "protocol_version": "1.0",
        "message_id": message_id,
        "task_id": "task-001",
        "type": "task.completed",
        "from": {"agent_id": "copilot", "role": "github_copilot"},
        "to": {"agent_id": "rusa-gateway", "role": "a2a_gateway"},
        "created_at": "2026-11-06T00:00:00Z",
        "result": {"summary": "Implementation complete"},
        "evidence": [{"kind": "commit", "sha": "abc123"}],
    }


class CallbackTests(unittest.TestCase):
    def test_valid_callback(self):
        self.assertEqual(validate_callback(sample())["type"], "task.completed")

    def test_rejects_wrong_sender(self):
        payload = sample()
        payload["from"]["role"] = "unknown"
        with self.assertRaisesRegex(ValueError, "sender role"):
            validate_callback(payload)

    def test_rejects_wrong_recipient(self):
        payload = sample()
        payload["to"]["role"] = "chatgpt_app"
        with self.assertRaisesRegex(ValueError, "recipient role"):
            validate_callback(payload)

    def test_rejects_unknown_or_non_string_event(self):
        for event_type in ("task.delete", [], {}):
            with self.subTest(event_type=event_type):
                payload = sample()
                payload["type"] = event_type
                with self.assertRaisesRegex(ValueError, "unsupported callback type"):
                    validate_callback(payload)

    def test_rejects_invalid_identifiers_and_timestamp(self):
        for field, value in (("task_id", "../other"), ("message_id", "message id"),
                             ("created_at", "tomorrow"), ("created_at", "2026-11-06T00:00:00")):
            with self.subTest(field=field, value=value):
                payload = sample()
                payload[field] = value
                with self.assertRaises(ValueError):
                    validate_callback(payload)

    def test_signature_valid_and_tamper_proof(self):
        secret = "x" * 40
        timestamp = "1793923200"
        body = json.dumps(sample()).encode()
        signed = timestamp.encode() + b"." + body
        signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        self.assertTrue(verify_signature(timestamp, body, signature, secret, now=1793923200))
        self.assertFalse(verify_signature(timestamp, body + b" ", signature, secret, now=1793923200))
        self.assertFalse(verify_signature(timestamp, body, signature, secret, now=1793923601))
        self.assertFalse(verify_signature("not-a-time", body, signature, secret, now=1793923200))

    def test_store_idempotency_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CallbackStore(str(Path(directory) / "callbacks.sqlite3"))
            payload = sample()
            self.assertTrue(store.insert(payload))
            self.assertFalse(store.insert(payload))
            conflicting_payload = sample()
            conflicting_payload["result"] = {"summary": "different content"}
            with self.assertRaises(IdempotencyConflict):
                store.insert(conflicting_payload)
            records, next_cursor = store.page_for_task("task-001")
            self.assertEqual(len(records), 1)
            self.assertIsNone(next_cursor)
            self.assertEqual(records[0]["payload"]["message_id"], "msg-001")

    def test_store_pages_are_bounded_and_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CallbackStore(str(Path(directory) / "callbacks.sqlite3"))
            for index in range(3):
                store.insert(sample(f"msg-{index:03}"))
            first, cursor = store.page_for_task("task-001", limit=2)
            self.assertEqual(len(first), 2)
            self.assertIsNotNone(cursor)
            second, next_cursor = store.page_for_task("task-001", limit=2, cursor=cursor)
            self.assertEqual(len(second), 1)
            self.assertIsNone(next_cursor)
            self.assertEqual({item["payload"]["message_id"] for item in first + second},
                             {"msg-000", "msg-001", "msg-002"})


class CallbackHttpTests(unittest.TestCase):
    SECRET = "s" * 40
    READ_TOKEN = "r" * 32

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = CallbackStore(str(Path(self.tempdir.name) / "http.sqlite3"))
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(self.store, self.SECRET, self.READ_TOKEN),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def test_signed_sender_receiver_and_authenticated_poll(self):
        payload = sample()
        first = send_callback(self.endpoint, payload, self.SECRET)
        second = send_callback(self.endpoint, payload, self.SECRET)
        self.assertEqual(first["status"], "accepted")
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])

        request = urllib.request.Request(
            self.endpoint + "/v1/tasks/task-001/callbacks",
            headers={"Authorization": "Bearer " + self.READ_TOKEN},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.loads(response.read())
        self.assertEqual(result["task_id"], "task-001")
        self.assertEqual(len(result["callbacks"]), 1)
        self.assertIsNone(result["next_cursor"])

    def test_poll_requires_authentication_and_supports_query(self):
        request = urllib.request.Request(self.endpoint + "/v1/tasks/task-001/callbacks?limit=1")
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 401)

    def test_rejects_non_json_post(self):
        request = urllib.request.Request(
            self.endpoint + "/v1/callbacks", data=b"{}", headers={"Content-Type": "text/plain"}, method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 415)


if __name__ == "__main__":
    unittest.main()
