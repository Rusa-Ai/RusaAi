import hashlib
import hmac
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrator"))

from local_queue import SQLiteTaskQueue
from worker import A2APlanningHandler, LocalWorker
from a2a_ingress import (
    A2AValidationError,
    make_handler,
    validate_loopback_host,
    validate_task_envelope,
    verify_request_signature,
)


def sample_envelope(task_id=None, message_id=None):
    return {
        "protocol_version": "1.0",
        "task_id": task_id or str(uuid.uuid4()),
        "message_id": message_id or str(uuid.uuid4()),
        "type": "task.create",
        "from": {"agent_id": "chatgpt-session", "role": "chatgpt_app"},
        "to": {"agent_id": "rusa-local", "role": "rusa_orchestrator"},
        "created_at": "2026-11-06T02:00:00Z",
        "task": {
            "objective": "Analyze the local RUSA-AI model runtime and propose the next implementation step.",
            "context": "Development task issued through the local A2A bridge.",
            "acceptance_criteria": [
                "Return a scoped implementation plan.",
                "Identify risks and required evidence."
            ],
            "repository": "Rusa-Ai/RusaAi",
            "base_branch": "main",
            "work_branch": "feature/a2a-local-plan"
        },
        "policy": {
            "allowed_actions": ["analyze", "plan", "review"],
            "prohibited_actions": ["merge", "deploy", "delete", "secret_change"],
            "human_approval_required": [
                "merge", "deploy", "release", "secret_change",
                "permission_change", "destructive_action"
            ]
        },
        "status": "proposed",
        "evidence": []
    }


class A2AEnvelopeTests(unittest.TestCase):
    def test_validates_task_envelope_and_normalizes_uuid(self):
        payload = sample_envelope()
        payload["task_id"] = payload["task_id"].upper()
        normalized = validate_task_envelope(payload)
        self.assertEqual(normalized["task_id"], str(uuid.UUID(payload["task_id"])))

    def test_rejects_wrong_type_sender_and_recipient(self):
        for mutate, pattern in (
            (lambda p: p.update(type="task.cancel"), "only task.create"),
            (lambda p: p["from"].update(role="unknown"), "sender role"),
            (lambda p: p["to"].update(role="github_copilot"), "recipient role"),
        ):
            payload = sample_envelope()
            mutate(payload)
            with self.subTest(pattern=pattern), self.assertRaisesRegex(A2AValidationError, pattern):
                validate_task_envelope(payload)

    def test_rejects_unsafe_or_invalid_task_contract(self):
        for mutate in (
            lambda p: p["task"].update(repository="../outside"),
            lambda p: p["task"].update(repository="owner/.."),
            lambda p: p["task"].update(work_branch="feature/../main"),
            lambda p: p["task"].update(acceptance_criteria=[]),
            lambda p: p["task"].update(objective=""),
            lambda p: p["task"].update(base_branch=" "),
        ):
            payload = sample_envelope()
            mutate(payload)
            with self.subTest(payload=payload), self.assertRaises(A2AValidationError):
                validate_task_envelope(payload)

    def test_requires_high_impact_human_approvals(self):
        payload = sample_envelope()
        payload["policy"]["human_approval_required"].remove("merge")
        with self.assertRaisesRegex(A2AValidationError, "human approval"):
            validate_task_envelope(payload)

    def test_rejects_unknown_fields_and_duplicate_json_keys(self):
        payload = sample_envelope()
        payload["unexpected"] = True
        with self.assertRaises(A2AValidationError):
            validate_task_envelope(payload)
        from a2a_ingress import _reject_duplicate_json_keys
        with self.assertRaisesRegex(A2AValidationError, "duplicate"):
            json.loads('{"task_id":"a","task_id":"b"}', object_pairs_hook=_reject_duplicate_json_keys)

    def test_hmac_signature_is_timestamp_bound_and_tamper_proof(self):
        secret = "s" * 40
        timestamp = str(int(time.time()))
        raw = json.dumps(sample_envelope(), separators=(",", ":")).encode()
        digest = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        self.assertTrue(verify_request_signature(timestamp, raw, digest, secret))
        self.assertFalse(verify_request_signature(timestamp, raw + b" ", digest, secret))
        self.assertFalse(verify_request_signature(str(int(timestamp) - 1000), raw, digest, secret))
        self.assertFalse(verify_request_signature(timestamp, raw, digest, "short"))

    def test_loopback_bind_policy(self):
        for host in ("127.0.0.1", "::1", "localhost"):
            validate_loopback_host(host)
        for host in ("0.0.0.0", "192.168.1.10", "example.com"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_loopback_host(host)


class A2AHttpIngressTests(unittest.TestCase):
    SECRET = "rusa-a2a-secret-" + ("x" * 40)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.queue = SQLiteTaskQueue(Path(self.temp_dir.name) / "a2a.sqlite3")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(self.queue, self.SECRET),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self.endpoint = f"http://127.0.0.1:{self.server.server_address[1]}"

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, payload, *, secret=None, raw_body=None, timestamp=None):
        body = raw_body if raw_body is not None else json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        stamp = timestamp or str(int(time.time()))
        key = self.SECRET if secret is None else secret
        signature = hmac.new(key.encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        request = urllib.request.Request(
            self.endpoint + "/v1/tasks",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-RUSA-Timestamp": stamp,
                "X-RUSA-Signature": signature,
            },
            method="POST",
        )
        return urllib.request.urlopen(request, timeout=5)

    def test_signed_task_is_enqueued_for_planning_only(self):
        envelope = sample_envelope()
        with self.post(envelope) as response:
            result = json.loads(response.read())
            self.assertEqual(response.status, 202)
        self.assertEqual(result["execution_mode"], "planning_only")
        task = self.queue.get(envelope["task_id"])
        self.assertEqual(task.state, "QUEUED")
        self.assertEqual(task.task_type, "a2a.plan")
        self.assertEqual(task.payload["a2a_message_id"], envelope["message_id"])

    def test_duplicate_task_id_with_same_envelope_is_idempotent(self):
        envelope = sample_envelope()
        with self.post(envelope) as first:
            self.assertFalse(json.loads(first.read())["duplicate"])
        with self.post(envelope) as second:
            self.assertTrue(json.loads(second.read())["duplicate"])
        self.assertEqual(len(self.queue.events(envelope["task_id"])), 1)

    def test_duplicate_task_id_with_different_content_returns_conflict(self):
        envelope = sample_envelope()
        with self.post(envelope):
            pass
        changed = json.loads(json.dumps(envelope))
        changed["task"]["objective"] = "different request"
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post(changed)
        self.assertEqual(error.exception.code, 409)

    def test_rejects_invalid_signature_and_expired_timestamp(self):
        envelope = sample_envelope()
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post(envelope, secret="wrong-secret-" + ("z" * 32))
        self.assertEqual(error.exception.code, 401)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post(envelope, timestamp=str(int(time.time()) - 1000))
        self.assertEqual(error.exception.code, 401)


    def test_end_to_end_signed_a2a_task_to_worker_plan(self):
        envelope = sample_envelope()
        with self.post(envelope) as response:
            accepted = json.loads(response.read())
        self.assertEqual(accepted["status"], "accepted")

        class FakeRuntime:
            config = type("RuntimeConfigStub", (), {"model": "rusa-local-test"})()

            def complete(self, messages, *, model=None, max_tokens=None, temperature=0.2):
                self.messages = messages
                return "1. Inspect repository. 2. Implement scoped change. 3. Run tests."

        runtime = FakeRuntime()
        worker = LocalWorker(
            self.queue,
            "a2a-planning-worker",
            {"a2a.plan": A2APlanningHandler(runtime)},
            lease_seconds=2,
            heartbeat_interval_seconds=0.5,
        )
        completed = worker.run_once()
        self.assertEqual(completed.state, "COMPLETED")
        self.assertEqual(completed.result["status"], "planning_result")
        self.assertFalse(completed.result["execution_performed"])
        self.assertEqual(completed.result["task_id"], envelope["task_id"])
        self.assertIn("acceptance_criteria", runtime.messages[1]["content"])

    def test_rejects_oversized_content_length_before_reading_body(self):
        request = urllib.request.Request(
            self.endpoint + "/v1/tasks",
            data=b"x",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(1_048_577),
                "X-RUSA-Timestamp": str(int(time.time())),
                "X-RUSA-Signature": "0" * 64,
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 413)

    def test_rejects_non_json_media_type(self):
        request = urllib.request.Request(
            self.endpoint + "/v1/tasks",
            data=b"{}",
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 415)


if __name__ == "__main__":
    unittest.main()
