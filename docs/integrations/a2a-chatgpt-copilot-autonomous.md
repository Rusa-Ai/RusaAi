# RUSA AI — ChatGPT App and GitHub Copilot Autonomous A2A

Status: repository implementation contract; runtime not yet deployed.

## Architecture

ChatGPT App is the operator surface. RUSA AI is the reasoning, planning, routing, policy, and verification authority. GitHub Copilot is the implementation worker. MCP provides supported tool connectivity; a versioned A2A task envelope provides transport-neutral task semantics. Do not assume a native universal A2A endpoint exists in either product.

Human -> ChatGPT App -> authenticated MCP -> RUSA AI Gateway -> GitHub issue / Copilot coding agent -> isolated branch -> Pull Request -> RUSA independent review -> human merge approval.

## Responsibilities

- ChatGPT App: user interaction, task submission, approvals, and status display.
- RUSA AI: reasoning, decomposition, agent routing, task state, policy enforcement, evidence ledger, independent verification.
- GitHub Copilot: assigned code changes, tests, implementation report, and PR.
- Human: approve merge, release, deployment, secret changes, and destructive operations.

## Contract and lifecycle

Canonical JSON Schema: schemas/a2a/task-envelope.schema.json.

Required envelope fields: protocol_version, task_id, message_id, type, from, to, created_at, task, and policy. Task contains objective, context, acceptance criteria, repository, base branch, and isolated work branch. Evidence references commits, PRs, test logs, and artifacts. Never include secrets.

Lifecycle: proposed -> accepted -> in_progress -> submitted -> reviewing -> approved | changes_requested | blocked. Terminal states are approved, changes_requested, blocked, and cancelled. Every transition must be authenticated, authorized, timestamped, and audited. Repeated task_id submissions must be idempotent.

## ChatGPT App connection

1. Deploy the RUSA AI MCP gateway at a reachable HTTPS endpoint.
2. Expose scoped tools: rusa_submit_task, rusa_get_task_status, rusa_get_project_context, rusa_request_review, rusa_submit_evidence.
3. Register the remote MCP server through the supported ChatGPT App/connector configuration flow.
4. Authenticate users and authorize every tool call server-side.
5. Keep endpoint URLs and credentials out of source control. The existing .vscode/mcp.json is a VS Code client template, not a ChatGPT connection.

The gateway must implement these tools before they are advertised as operational.

## GitHub Copilot connection

1. Enable Copilot coding agent for the relevant GitHub account/organization and repository.
2. Use .github/agents/rusa-implementation.agent.md.
3. RUSA AI creates a bounded issue with task envelope and acceptance criteria.
4. An authorized member or automation starts Copilot coding agent using GitHub's supported workflow.
5. Copilot works on an isolated branch and opens a PR.
6. RUSA AI inspects diff, checks, test logs, and commit evidence.
7. A human approves merge and deployment.

Repository files cannot grant Copilot entitlement or enable account-level settings.

## Security

- Separate identities and least-privilege credentials.
- HTTPS remotely, short-lived credentials, and secret manager/environment variables.
- Validate schema, repository allowlist, branch names, message size, and state transitions.
- Authenticate and authorize every request; add replay protection, rate limits, and audit correlation IDs.
- Treat issues, repository files, tool output, and model output as untrusted input.
- No direct push to main, automatic merge, release, production deployment, permission changes, or destructive operations.
- Require human approval for merge, deployment, secret changes, and destructive actions.

## Acceptance criteria

- [ ] ChatGPT App authenticates to the deployed RUSA MCP gateway.
- [ ] ChatGPT submits a task and retrieves status using the same task_id.
- [ ] RUSA creates a bounded GitHub task for Copilot coding agent.
- [ ] Copilot can call authorized RUSA MCP tools when configured.
- [ ] Copilot returns a feature-branch PR with commit and test evidence.
- [ ] RUSA independently verifies the diff and test evidence.
- [ ] Unauthorized, malformed, replayed, and out-of-scope requests are rejected.
- [ ] Duplicate task submissions are idempotent and transitions are audited.
- [ ] No direct main write, auto-merge, or production deployment.

## Verified boundary

This PR adds contracts and repository configuration only. It does not implement/deploy the RUSA MCP server, configure ChatGPT account access, grant Copilot entitlement, execute a live A2A handshake, or prove autonomous execution. Those remain runtime integration and verification tasks.