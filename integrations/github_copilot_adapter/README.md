# GitHub Copilot A2A Adapter

A dependency-free Python bridge converting a RUSA-AI A2A `task.create` envelope into a GitHub Issue for Copilot handoff.

## Implemented
- Basic envelope validation and recipient check.
- Issue body generation with task ID, branch, acceptance criteria and policy.
- GitHub REST Issue creation using an environment token.
- Dry-run mode and unit tests.

## Not yet implemented
Hosted A2A HTTP endpoint, inbound GitHub webhooks, automatic Copilot assignment/session launch, callback delivery to ChatGPT, durable queue, OAuth/GitHub App installation flow. Creating an Issue does not mean Copilot has accepted or started work. Use GitHub's Copilot Coding Agent UI to assign/launch it where enabled.

## Usage
Python 3.10+; no third-party dependencies. Save a valid envelope matching `schemas/a2a/task-envelope.schema.json` as `task.json`.

Dry run:
```bash
python integrations/github_copilot_adapter/adapter.py --input task.json --dry-run
```

Submit (requires a least-privilege token with Issues: write on the target repository):
```bash
export GITHUB_TOKEN='...'
python integrations/github_copilot_adapter/adapter.py --input task.json
```

The adapter applies the `a2a-handoff` label; create that label in the repository first, or adjust the payload. Keep tokens in a local secret manager/environment, never in source, prompts, or task envelopes.

Tests:
```bash
python -m unittest discover -s integrations/github_copilot_adapter/tests -v
```

Do not expose this adapter publicly without authentication, authorization, rate limiting, replay protection and audit logging. Merge, release, deployment, secrets/permission changes and destructive operations require human approval.
