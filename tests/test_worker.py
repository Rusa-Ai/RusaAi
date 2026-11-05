import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from rusa_worker.config import WorkerConfig
from rusa_worker.providers import FlexibleProvider, GenerationRequest


class ConfigTests(unittest.TestCase):
    def test_defaults_to_flexible_provider(self):
        with patch.dict(os.environ, {}, clear=True):
            config = WorkerConfig.from_env()
        self.assertEqual(config.model_provider, "flexible")
        self.assertEqual(config.environment, "development")

    def test_rejects_unimplemented_provider(self):
        with patch.dict(os.environ, {"RUSAAI_MODEL_PROVIDER": "openai"}, clear=True):
            with self.assertRaises(ValueError):
                WorkerConfig.from_env()

    def test_rejects_invalid_environment(self):
        with patch.dict(os.environ, {"RUSAAI_ENVIRONMENT": "prod-ish"}, clear=True):
            with self.assertRaises(ValueError):
                WorkerConfig.from_env()


class ProviderTests(unittest.TestCase):
    def test_flexible_provider_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "No model provider adapter is configured"):
            FlexibleProvider().generate(GenerationRequest(task_id="t1", prompt="hello"))


class CliTests(unittest.TestCase):
    def test_dry_run_reports_config_valid(self):
        result = subprocess.run(
            [sys.executable, "-m", "rusa_worker", "--dry-run"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "CONFIG_VALID"', result.stdout)
        self.assertIn('"model_provider": "flexible"', result.stdout)

    def test_normal_run_is_blocked_without_adapter(self):
        result = subprocess.run(
            [sys.executable, "-m", "rusa_worker"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn('"status": "BLOCKED"', result.stdout)


if __name__ == "__main__":
    unittest.main()
