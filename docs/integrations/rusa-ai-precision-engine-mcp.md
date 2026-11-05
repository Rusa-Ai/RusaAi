# RUSA AI Precision Engine — MCP/Copilot status

## Intended local connection

VS Code launches `rusa_ai_precision.mcp_server` as a local stdio process from the extracted runtime directory via `.vscode/mcp.json`. This is not a remotely reachable MCP service and it uses the local operating-system process identity.

## MCP tools

- `rusa_submit_task`
- `rusa_get_task_status`
- `rusa_submit_evidence`

Task submission is approval-gated. Approval is intentionally performed by an operator through the local CLI, not delegated to a model/tool client.

## What has been tested

The MCP JSON-RPC protocol and tool handlers have unit tests in the runtime package. The package build checks report 67/67 unit tests passing. This is test-harness evidence only.

## What remains unverified

- No live initialize/tool-list handshake has been observed from the user's VS Code/Copilot session.
- No live Copilot tool invocation or executed task round-trip is proven.
- No automatic RUSA AI → Copilot coding-agent dispatch is included; the reverse direction remains a manual GitHub handoff.
- No live PostgreSQL or local model service was connected in the package build environment.

A live integration claim requires captured client handshake, tool invocation, task ID, approval event, worker result, verifier result, and final status evidence.
