import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from receiver import CallbackStore, validate_callback, verify_signature


def sample():
    return {
        "protocol_version": "1.0",
        "message_id": "msg-001",
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

    def test_rejects_unknown_event(self):
        payload = sample()
        payload["type"] = "task.delete"
        with self.assertRaisesRegex(ValueError, "unsupported callback type"):
            validate_callback(payload)

    def test_rejects_invalid_task_id(self):
        payload = sample()
        payload["task_id"] = "../other"
        with self.assertRaisesRegex(ValueError, "invalid characters"):
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

    def test_store_is_idempotent_and_queryable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CallbackStore(str(Path(directory) / "callbacks.sqlite3"))
            payload = sample()
            self.assertTrue(store.insert(payload))
            self.assertFalse(store.insert(payload))
            records = store.list_for_task("task-001")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["payload"]["message_id"], "msg-001")


if __name__ == "__main__":
    unittest.main()
