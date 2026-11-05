# RUSA-AI Local Autonomous Platform Architecture v1

**Decision status:** Proposed implementation baseline  
**Deployment target:** 100% local  
**Operating mode:** Full autonomous development with controlled approvals  
**Production status:** Not deployed; this document is an architecture contract, not proof of a running system.

## 1. Mission

Build RUSA-AI as an independently operable AI platform that can reason, plan, coordinate engineering agents, execute verified work, and improve its own software and model pipeline. ChatGPT and GitHub Copilot are development collaborators, not runtime dependencies of the local RUSA-AI product.

## 2. Runtime planes

1. **Interaction plane:** local web/API/CLI clients; authenticated users and project workspaces.
2. **Intelligence plane:** locally hosted model inference, model registry, prompt/runtime policies, reasoning and planning, evaluation, and retrieval.
3. **Orchestration plane:** durable task queue, scheduler, state machine, worker leases, retries, idempotency, cancellation, budgets, and approval gates.
4. **Execution plane:** isolated workspaces/sandboxes, repository adapters, tool/MCP adapters, test runners, artifact storage, and deployment adapters.
5. **Evidence and governance plane:** append-only task events, artifact/commit/test evidence, policy decisions, audit trail, and rollback records.

## 3. Roles

- **ChatGPT (development-time architect):** helps define architecture, acceptance criteria, review findings, and implementation plans when explicitly connected. It is not assumed to run continuously.
- **RUSA orchestrator (local runtime):** persistent source of truth for task state, scheduling, policy enforcement, and worker coordination.
- **Workers 01-09:** project management; engineering; model research/training; data and knowledge; security; QA/evaluation; DevOps; integration; independent verification.
- **GitHub Copilot (coding executor):** may implement repository tasks through supported GitHub workflows. It is an optional external development tool, not required for local inference or local production operation.
- **Local model runtime:** serves selected open-weight models under their licenses and hardware constraints. No specific model is selected until license, hardware, benchmark, and quality gates are recorded.

## 4. Control model

Full autonomy means autonomous task decomposition and execution inside approved boundaries. It does **not** mean unrestricted access.

Require human approval before:
- merging to protected/default branches;
- production deployment or destructive migration;
- publishing, licensing, or distributing model weights/datasets;
- spending above configured compute/provider budgets;
- accessing secrets, personal data, or external systems beyond scoped permissions.

Workers must use least-privilege credentials, isolated workspaces, bounded retries, resource quotas, and auditable tool calls. Treat repository content, model outputs, and external tool responses as untrusted input.

## 5. Local-first constraints

- Core inference, orchestration, task storage, vector/search index, artifacts, and telemetry must be runnable locally.
- External APIs may be used only as explicitly enabled development integrations; they must not be required for core operation.
- Secrets must be supplied at runtime through a local secret store/environment injection and never committed.
- Local deployment must document supported OS, CPU/GPU, RAM/VRAM, storage, model quantization, and reproducible startup/backup/restore steps.

## 6. Model development lifecycle

1. Select an open-weight base model after license and hardware review.
2. Establish a reproducible baseline benchmark before tuning.
3. Curate and version datasets with provenance, consent/licensing, deduplication, and train/validation/test separation.
4. Run supervised fine-tuning or other justified adaptation only when evaluation shows a need.
5. Track training configuration, code revision, dataset revision, model artifact hashes, hardware, and metrics.
6. Evaluate capability, regressions, safety, latency, memory, and cost.
7. Promote model artifacts only after independent verification and explicit approval.
8. Deploy locally with rollback to a previously verified model.

Fine-tuning is not equivalent to training a foundation model from scratch. Training from scratch requires a separate feasibility decision and compute/data budget.

## 7. Task lifecycle

`PROPOSED -> APPROVED -> QUEUED -> CLAIMED -> RUNNING -> VERIFYING -> VERIFIED -> AWAITING_APPROVAL -> COMPLETED`

Terminal or exceptional states: `REJECTED`, `BLOCKED`, `FAILED`, `CANCELLED`, `ROLLED_BACK`.

Every task must have an owner, scope, acceptance criteria, branch/workspace, timeout, retry budget, and evidence references. A worker cannot mark its own work as independently verified.

## 8. Delivery stages

- **P0 — Contracts and governance:** architecture, task/evidence contracts, approval boundaries, CI baseline.
- **P1 — Local runtime vertical slice:** local API, model adapter, health checks, configuration validation, reproducible startup.
- **P2 — Durable orchestration:** database-backed queue, state machine, leases, retries, event log, recovery.
- **P3 — Agent execution:** worker registry, sandbox, tool policy, task delegation, independent verifier.
- **P4 — Model/data pipeline:** dataset governance, benchmark harness, fine-tuning pipeline, model registry.
- **P5 — Local productization:** UI, observability, backup/restore, security hardening, upgrade and rollback.

## 9. Evidence policy

Statuses have strict meanings:
- `PLANNED`: specified, not implemented.
- `IMPLEMENTED`: code/configuration exists.
- `VERIFIED`: tests or inspection passed with linked evidence.
- `DEPLOYED`: running in the named target environment with deployment evidence.

Never infer `VERIFIED` or `DEPLOYED` from a README, agent statement, successful syntax check, or unexecuted workflow. This repository PR only establishes the baseline contracts until runtime evidence is produced.
