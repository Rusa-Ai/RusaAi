import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PlatformContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            (ROOT / "config" / "rusa-platform.json").read_text(encoding="utf-8")
        )

    def test_deployment_is_local_first(self):
        deployment = self.contract["deployment"]
        self.assertEqual(deployment["mode"], "local")
        self.assertFalse(deployment["external_model_apis_enabled_by_default"])
        self.assertFalse(deployment["core_runtime_requires_internet"])

    def test_controlled_autonomy_has_approval_boundaries(self):
        autonomy = self.contract["autonomy"]
        self.assertEqual(autonomy["mode"], "full")
        self.assertEqual(autonomy["approval_policy"], "controlled")
        self.assertTrue(autonomy["may_create_feature_branches"])
        self.assertTrue(autonomy["may_open_draft_pull_requests"])
        self.assertFalse(autonomy["may_merge_default_branch_without_approval"])
        self.assertFalse(autonomy["may_deploy_without_approval"])
        self.assertFalse(autonomy["may_perform_destructive_operations_without_approval"])

    def test_evidence_vocabulary_is_complete(self):
        self.assertEqual(
            self.contract["evidence_statuses"],
            ["PLANNED", "IMPLEMENTED", "VERIFIED", "DEPLOYED"],
        )

    def test_runtime_is_not_claimed_as_running(self):
        for status in self.contract["runtime_components"].values():
            self.assertEqual(status, "PLANNED")


if __name__ == "__main__":
    unittest.main()
