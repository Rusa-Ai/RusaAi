# RUSA AI ↔ GitHub Copilot integration

**Status:** integration scaffold / configuration contract  
**Repository:** `Rusa-Ai/RusaAi`  
**Default branch protection:** all integration work targets feature branches; never write to `main`.

## 1. Roles

- **RUSA AI → Copilot:** RUSA AI prepares a bounded engineering task and hands it to GitHub Copilot coding agent through the repository's supported GitHub issue/agent workflow. Copilot implements on an isolated branch and returns a pull request.
- **Copilot → RUSA AI:** Copilot Chat/agent mode calls tools exposed by the RUSA AI MCP server (for example, submit a reasoning request, retrieve project context, request an architecture review, or report implementation evidence).
- **RUSA AI remains the coordinator:** it validates task scope, evaluates evidence, and decides whether a PR is acceptable. Human approval remains required for merge and production deployment.

This is a bidirectional agent workflow using GitHub's Copilot coding-agent and MCP capabilities. It is **not** a claim that Copilot exposes a universal native A2A endpoint. A protocol-native A2A transport can be added behind the same task contract when both runtimes expose compatible A2A endpoints.

## 2. Message envelope

Every handoff should carry:
- `task_id`: globally unique ID
- `from`, `to`: agent identities
- `type`: `task.create | task.accepted | task.status | task.result | task.blocked | task.review`
- `created_at`: RFC 3339 UTC timestamp
- `repository`, `base_branch`, `work_branch`
- `objective`, `context`, `acceptance_criteria`
- `constraints`: permissions, security boundaries, and prohibited actions
- `evidence`: commit SHA, PR URL, test logs, artifact references

Do not include secrets, access tokens, private keys, or personal data in task payloads.

## 3. RUSA AI → Copilot

1. RUSA AI creates a GitHub issue containing the task envelope and acceptance criteria.
2. A repository member invokes/assigns the GitHub Copilot coding agent using the Copilot coding-agent workflow available to this repository.
3. Copilot works on its own branch and opens a PR.
4. RUSA AI reads the PR, checks diff and CI evidence, and returns `task.review`.
5. A human reviews and merges. No automatic merge or production deployment is configured here.

**Prerequisites:** Copilot coding agent must be enabled for the GitHub account/organization and repository, and the repository must allow the required agent workflow. This scaffold does not enable account-level Copilot settings.

## 4. Copilot → RUSA AI

Configure a RUSA AI MCP server in the local VS Code workspace using `.vscode/mcp.json` (template below). The endpoint must be implemented and running by the RUSA AI runtime before the tools become usable.

The MCP server should expose narrowly scoped tools such as:
- `rusa_submit_task`
- `rusa_get_task_status`
- `rusa_get_project_context`
- `rusa_request_architecture_review`
- `rusa_submit_evidence`

Use authenticated HTTPS outside local development. Keep credentials in environment variables or a secret manager; never commit them. Restrict tool scopes and validate every incoming argument.

## 5. Task state machine

`proposed → accepted → in_progress → submitted → reviewing → approved | changes_requested | blocked`

Terminal states: `approved`, `changes_requested`, `blocked`, `cancelled`. Every transition must be timestamped and attributable to an agent or human. Retries must be idempotent using `task_id`.

## 6. Security and governance

- Least-privilege GitHub App/token permissions.
- Branch protection and required checks on `main`.
- Explicit human approval for merge, release, deployment, secrets, and destructive operations.
- Signed/authenticated service-to-service requests; TLS in non-local environments.
- Input validation, replay protection, rate limits, audit log, and correlation IDs.
- Treat model output as untrusted; RUSA AI independently verifies code and test evidence.
- No secrets in prompts, issues, PR bodies, logs, or artifacts.

## 7. Acceptance criteria

- [ ] Copilot can discover and call the configured RUSA AI MCP tools in VS Code.
- [ ] RUSA AI can create a bounded GitHub task and invoke the enabled Copilot coding-agent workflow.
- [ ] Both directions preserve `task_id`, status, repository, branch, and evidence.
- [ ] Unauthorized requests are rejected; secrets are not logged.
- [ ] Duplicate task submissions are idempotent.
- [ ] Changes remain on feature branches and are returned as PRs.
- [ ] Tests cover authentication, authorization, validation, state transitions, and failure handling.
- [ ] No direct push to `main`, auto-merge, or production deployment.

## 8. Current implementation boundary

This PR adds repository-side collaboration instructions and an MCP client configuration template. It does not create or deploy the RUSA AI MCP server, does not grant Copilot entitlements, and does not prove live agent-to-agent communication. Those require the RUSA runtime endpoint, credentials, and Copilot coding-agent availability to be configured and tested.
