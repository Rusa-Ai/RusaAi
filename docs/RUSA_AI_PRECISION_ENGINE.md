# RUSA AI Precision Engine v1.1

## Purpose

This release establishes a local-first precision and workflow runtime. The model is treated as a probabilistic proposer; Python owns task state, action policy, retries, approvals, evidence validation, and execution boundaries. PostgreSQL is the durable source of truth for task state and event history.

## Included runtime components

The delivered package `RUSA_AI_Precision_Engine_v1_1.zip` contains:

- finite-state workflow with task leases, heartbeat, bounded retries, optimistic versioning, and human approval/rejection;
- PostgreSQL adapter and initial SQL schema;
- allowlisted worker runtime with separate verification and recovery of persisted artifacts;
- loopback-only OpenAI-compatible local model adapter;
- evidence registry, response-contract validator, and SHA-256 content-addressed artifact store;
- local stdio MCP server and CLI;
- 80 seed evaluation cases: 40 answerable, 25 unanswerable, 15 false-premise;
- local Compose file, environment template, deployment guide, and unit tests.

**Package integrity:** 70,830 bytes. SHA-256: `897324ac03c736e2a8bda4fcccd71c8cc1cdd0dcc14f6ef5e535cf495734cab0`.

The runtime package is a separate delivery artifact and is not embedded as source files in this documentation/configuration PR. Extract the ZIP so its top-level directory is `RUSA_AI_Precision_Engine_v1_1/`.

## Local setup

Requirements: Python 3.11+, Docker Engine with Compose plugin, and a local model runtime if inference is required.

From the extracted directory:

```bash
cp .env.example .env
# Set a unique local database password and keep .env untracked.
docker compose --env-file .env up -d postgres
docker compose --env-file .env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
  < sql/001_initial_schema.sql
python -m pip install -e '.[postgres]'
```

Set `RUSA_DATABASE_URL` in the untracked `.env`. Configure `RUSA_LOCAL_MODEL_URL` and `RUSA_LOCAL_MODEL_NAME` only for a model server bound to `localhost`, `127.0.0.1`, or `::1`. Load environment variables in a shell before CLI use:

```bash
set -a && . ./.env && set +a
rusa-precision --help
rusa-precision model-check
```

`model-check` performs a real inference request. A passing unit test for the adapter is not a substitute for this runtime check.

## VS Code / Copilot MCP

This branch's `.vscode/mcp.json` starts the MCP server locally through stdio. After extracting and installing the package, use **MCP: List Servers** in VS Code and start `rusaAiPrecision`. The server exposes:

- `rusa_submit_task`
- `rusa_get_task_status`
- `rusa_submit_evidence`

MCP-created tasks require operator approval. Approve through the local CLI; approval is intentionally not exposed as an MCP tool. RUSA AI → Copilot coding-agent delegation remains a manual GitHub handoff in this release.

## Local build verification

The delivered source package was checked in its build environment:

- 67/67 standard-library unit tests passed.
- Evaluation corpus shape validation passed for all 80 cases; category counts and document-line references resolved.
- Python source compiled; response JSON Schema, VS Code MCP JSON, and TOML metadata parsed.
- Editable installation and `rusa-precision --help` succeeded.

These checks do not constitute a semantic model benchmark. No model outputs were collected or independently adjudicated, so fabrication/citation/honesty scores are not reported.

## Not yet verified

- Live PostgreSQL connection, applying the SQL migration, transaction/concurrency behavior, backup/restore, and crash recovery.
- Live local model inference and model-quality metrics.
- Live MCP handshake from the user's VS Code/Copilot process.
- A complete bidirectional RUSA AI ↔ GitHub Copilot execution round trip.
- Security penetration testing, monitoring/alerting, signed identity, restore drills, and production deployment.

Docker, `psql`, and the PostgreSQL driver were unavailable in the package build environment; the database adapter was unit-tested with fakes. Do not mark this release `DEPLOYED` or production-ready based on local unit tests alone.

## Required acceptance gates before production

1. Start local PostgreSQL and apply the schema; retain migration output and connection checks.
2. Run concurrent worker/lease/reclaim and restart/recovery integration tests against real PostgreSQL.
3. Connect the chosen local model and collect the complete 80-case outputs; independently adjudicate claims and citations before reporting metrics.
4. Complete a live VS Code/Copilot MCP handshake and execute a real task through submit → approval → worker → verifier → status.
5. Demonstrate the reverse RUSA AI → Copilot handoff with traceable task ID, commit/PR evidence, and human approval boundary.
6. Run security, backup/restore, and operational recovery reviews. Only then assess deployment readiness.

## Scope of this PR

This PR updates repository entry documentation and the VS Code local MCP configuration. The complete runtime implementation is supplied as the separately downloadable ZIP artifact; it is not copied into repository source paths by this PR. No secrets, deployment, merge, or direct `main` modification are involved.
