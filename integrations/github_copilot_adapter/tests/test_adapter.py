import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapter import validate, build_issue


def sample():
    return {
        "protocol_version": "1.0",
        "task_id": "12345678-1234-4234-8234-123456789abc",
        "message_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "type": "task.create",
        "from": {"agent_id": "chatgpt", "role": "chatgpt_app"},
        "to": {"agent_id": "copilot", "role": "github_copilot"},
        "created_at": "2026-11-06T00:00:00Z",
        "task": {
            "objective": "Implement a safe parser",
            "acceptance_criteria": ["Tests pass", "No main changes"],
            "repository": "Rusa-Ai/RusaAi",
            "base_branch": "main",
            "work_branch": "feature/a2a-demo",
        },
        "policy": {
            "allowed_actions": ["code", "tests"],
            "prohibited_actions": ["merge", "deploy"],
            "human_approval_required": ["merge", "deploy"],
        },
    }


class AdapterTests(unittest.TestCase):
    def test_valid_envelope(self):
        validate(sample())

    def test_wrong_recipient_rejected(self):
        data = sample()
        data["to"]["role"] = "human"
        with self.assertRaisesRegex(ValueError, "Recipient role"):
            validate(data)

    def test_missing_criteria_rejected(self):
        data = sample()
        del data["task"]["acceptance_criteria"]
        with self.assertRaisesRegex(ValueError, "Missing task field"):
            validate(data)

    def test_non_object_envelope_rejected(self):
        with self.assertRaisesRegex(ValueError, "Envelope must be an object"):
            validate([])

    def test_malformed_recipient_rejected(self):
        data = sample()
        data["to"] = []
        with self.assertRaisesRegex(ValueError, "to must be an object"):
            validate(data)

    def test_empty_or_invalid_acceptance_criteria_rejected(self):
        for criteria in ([], "not-a-list", ["valid", "  "]):
            with self.subTest(criteria=criteria):
                data = sample()
                data["task"]["acceptance_criteria"] = criteria
                with self.assertRaisesRegex(ValueError, "Acceptance criteria"):
                    validate(data)

    def test_invalid_repository_rejected(self):
        data = sample()
        data["task"]["repository"] = "../other/repo"
        with self.assertRaisesRegex(ValueError, "owner/name"):
            validate(data)

    def test_invalid_work_branch_rejected(self):
        data = sample()
        data["task"]["work_branch"] = "main"
        with self.assertRaisesRegex(ValueError, "work_branch"):
            validate(data)

    def test_issue_has_task_and_branch(self):
        title, body = build_issue(sample())
        self.assertIn("A2A", title)
        self.assertIn("feature/a2a-demo", body)
        self.assertIn("Acceptance criteria", body)


if __name__ == "__main__":
    unittest.main()
