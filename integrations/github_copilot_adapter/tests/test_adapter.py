import unittest
from adapter import validate, build_issue

def sample():
    return {"protocol_version":"1.0","task_id":"12345678-1234-4234-8234-123456789abc","message_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","type":"task.create","from":{"agent_id":"chatgpt","role":"chatgpt_app"},"to":{"agent_id":"copilot","role":"github_copilot"},"created_at":"2026-11-06T00:00:00Z","task":{"objective":"Implement a safe parser","acceptance_criteria":["Tests pass","No main changes"],"repository":"Rusa-Ai/RusaAi","base_branch":"main","work_branch":"feature/a2a-demo"},"policy":{"allowed_actions":["code","tests"],"prohibited_actions":["merge","deploy"],"human_approval_required":["merge","deploy"]}}

class AdapterTests(unittest.TestCase):
    def test_valid_envelope(self): validate(sample())
    def test_wrong_recipient_rejected(self):
        d=sample(); d["to"]["role"]="human"
        with self.assertRaises(ValueError): validate(d)
    def test_missing_criteria_rejected(self):
        d=sample(); del d["task"]["acceptance_criteria"]
        with self.assertRaises(ValueError): validate(d)
    def test_issue_has_task_and_branch(self):
        title,body=build_issue(sample())
        self.assertIn("A2A",title); self.assertIn("feature/a2a-demo",body); self.assertIn("Acceptance criteria",body)

if __name__=="__main__": unittest.main()
