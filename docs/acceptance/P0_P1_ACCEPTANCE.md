# RUSA-AI P0/P1 Acceptance Criteria

These criteria are gates, not claims of completion. Each item must be linked to a commit, test run, artifact, or deployment record.

## P0 — Architecture and repository contracts

- [ ] Local-only deployment target is explicit; external model APIs are optional and disabled by default.
- [ ] Runtime roles of ChatGPT, local orchestrator, workers, and Copilot are separated.
- [ ] Task lifecycle, terminal states, retries, cancellation, and idempotency are specified.
- [ ] Human approval boundaries are explicit for merge, deployment, destructive operations, model publication, and budget overruns.
- [ ] Evidence status vocabulary is consistent: PLANNED / IMPLEMENTED / VERIFIED / DEPLOYED.
- [ ] No credentials, tokens, or private datasets are committed.
- [ ] CI validates platform configuration and architecture contract.

## P1 — Local model runtime vertical slice

- [ ] A documented local runtime can start without ChatGPT, Copilot, or external model APIs.
- [ ] A real local model is selected with source, immutable revision/hash, license, quantization, and hardware requirements recorded.
- [ ] Configuration validation fails closed on missing/invalid model files, unsupported backend, and unsafe paths.
- [ ] Health/readiness endpoints distinguish process liveness from model readiness.
- [ ] A deterministic smoke test sends a prompt to the local model and validates a bounded response.
- [ ] Inference logs redact secrets and avoid storing raw user prompts by default.
- [ ] Model adapter has timeout, cancellation, resource limits, and explicit error states.
- [ ] Reproducible local startup, shutdown, and recovery instructions are tested on the target OS.
- [ ] Benchmark evidence records latency, throughput, RAM/VRAM, model revision, and test environment.

## P2 — Durable orchestration (dependent gate)

- [ ] Queue and task state are persisted in a local database.
- [ ] Worker leases, heartbeat, crash recovery, bounded retries, and idempotency are tested.
- [ ] Task execution occurs in an isolated workspace with least-privilege permissions.
- [ ] Independent verification is separate from implementation worker identity.
- [ ] Approval decisions and all external tool calls are auditable.

## Controlled autonomy rules

- Workers may autonomously create feature branches, implement scoped tasks, run tests, and open draft PRs.
- Workers must not merge to the default branch, deploy production, delete user data, rotate credentials, or exceed compute budgets without explicit approval.
- Failed acceptance criteria must return the task to a bounded repair loop or mark it BLOCKED; never report success optimistically.

## Required evidence record

For every acceptance item, record: requirement ID, status, commit SHA, workflow run URL, test/artifact reference, verifier, timestamp, and limitations. Missing evidence means the item remains PLANNED or IMPLEMENTED, not VERIFIED.
