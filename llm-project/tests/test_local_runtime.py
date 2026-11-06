import json
import sys
import urllib.error
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "serve"))

from local_runtime import (
    LocalOpenAICompatibleRuntime,
    LocalRuntimeError,
    RuntimeConfig,
)


class FakeResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self.raw


class RuntimeConfigTests(unittest.TestCase):
    def test_default_config_is_loopback_only(self):
        config = RuntimeConfig()
        self.assertEqual(config.base_url, "http://127.0.0.1:11434/v1")

    def test_rejects_non_loopback_hosts(self):
        for url in (
            "https://127.0.0.1:11434/v1",
            "http://192.168.1.20:11434/v1",
            "http://model.example.com/v1",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    RuntimeConfig(base_url=url)

    def test_rejects_url_credentials_and_query(self):
        with self.assertRaisesRegex(ValueError, "credentials"):
            RuntimeConfig(base_url="http://user:pass@127.0.0.1:11434/v1")
        with self.assertRaisesRegex(ValueError, "credentials"):
            RuntimeConfig(base_url="http://127.0.0.1:11434/v1?token=x")

    def test_rejects_invalid_and_non_finite_limits(self):
        for timeout in (0, float("nan"), float("inf")):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(ValueError, "timeout_seconds"):
                    RuntimeConfig(timeout_seconds=timeout)
        with self.assertRaisesRegex(ValueError, "max_tokens"):
            RuntimeConfig(max_tokens=9000)


class LocalRuntimeTests(unittest.TestCase):
    def make_runtime(self, payload, model="rusa-test:latest"):
        opener = Mock(return_value=FakeResponse(payload))
        runtime = LocalOpenAICompatibleRuntime(
            RuntimeConfig(model=model, timeout_seconds=3.5),
            opener=opener,
        )
        return runtime, opener

    def test_health_distinguishes_process_and_model_availability(self):
        runtime, opener = self.make_runtime({"data": [{"id": "rusa-test:latest"}]})
        health = runtime.health()
        self.assertTrue(health.process_reachable)
        self.assertTrue(health.model_available)
        self.assertEqual(health.available_models, ("rusa-test:latest",))
        opener.assert_called_once()
        self.assertEqual(opener.call_args.kwargs["timeout"], 3.5)

    def test_health_reports_missing_model(self):
        runtime, _ = self.make_runtime({"data": [{"id": "other-model"}]})
        health = runtime.health()
        self.assertTrue(health.process_reachable)
        self.assertFalse(health.model_available)

    def test_health_without_target_model_is_not_false_readiness(self):
        runtime, _ = self.make_runtime({"data": []}, model=None)
        health = runtime.health()
        self.assertIsNone(health.model_available)

    def test_complete_posts_openai_compatible_payload(self):
        runtime, opener = self.make_runtime({
            "choices": [{"message": {"content": "RUSA response"}}]
        })
        answer = runtime.complete(
            [{"role": "user", "content": "Hello"}],
            max_tokens=64,
            temperature=0.1,
        )
        self.assertEqual(answer, "RUSA response")
        request = opener.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/chat/completions"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "rusa-test:latest")
        self.assertEqual(body["max_tokens"], 64)
        self.assertFalse(body["stream"])

    def test_complete_requires_model(self):
        runtime, _ = self.make_runtime({"choices": []}, model=None)
        with self.assertRaisesRegex(ValueError, "RUSA_MODEL_NAME"):
            runtime.complete([{"role": "user", "content": "Hello"}])

    def test_complete_validates_messages(self):
        runtime, _ = self.make_runtime({"choices": []})
        with self.assertRaisesRegex(ValueError, "role"):
            runtime.complete([{"role": "tool", "content": "bad"}])
        with self.assertRaisesRegex(ValueError, "content"):
            runtime.complete([{"role": "user", "content": " "}])

    def test_complete_validates_generation_limits(self):
        runtime, _ = self.make_runtime({"choices": []})
        with self.assertRaisesRegex(ValueError, "max_tokens"):
            runtime.complete([{"role": "user", "content": "Hello"}], max_tokens=0)
        for temperature in (3, float("nan"), float("inf")):
            with self.subTest(temperature=temperature):
                with self.assertRaisesRegex(ValueError, "temperature"):
                    runtime.complete(
                        [{"role": "user", "content": "Hello"}],
                        temperature=temperature,
                    )

    def test_bad_json_is_reported(self):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(read=Mock(return_value=b"{")))
        response.__exit__ = Mock(return_value=False)
        opener = Mock(return_value=response)
        runtime = LocalOpenAICompatibleRuntime(RuntimeConfig(), opener=opener)
        with self.assertRaisesRegex(LocalRuntimeError, "invalid JSON"):
            runtime.list_models()

    def test_transport_error_is_reported(self):
        opener = Mock(side_effect=urllib.error.URLError("connection refused"))
        runtime = LocalOpenAICompatibleRuntime(RuntimeConfig(), opener=opener)
        with self.assertRaisesRegex(LocalRuntimeError, "cannot reach"):
            runtime.list_models()

    def test_malformed_models_payload_is_reported(self):
        runtime, _ = self.make_runtime({"models": []})
        with self.assertRaisesRegex(LocalRuntimeError, "data array"):
            runtime.list_models()

    def test_malformed_completion_payload_is_reported(self):
        runtime, _ = self.make_runtime({"choices": []})
        with self.assertRaisesRegex(LocalRuntimeError, "missing choices"):
            runtime.complete([{"role": "user", "content": "Hello"}])


if __name__ == "__main__":
    unittest.main()
