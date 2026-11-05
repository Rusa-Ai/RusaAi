# P0 Repository Discovery and Architecture Decision Record

- Date: 2026-11-06
- Repository: `Rusa-Ai/RusaAi`
- Base: `main` at `dccb8140950e97286c0382860e6ac33c3e4cd7b5`
- Work branch: `docs/p0-repository-discovery-adr`
- Status: PARTIALLY COMPLETE; model selection BLOCKED pending hardware, data, and product requirements.
- Production deployment: NOT PERFORMED.

## 1. Executive summary

The current default branch is not an empty repository. The recursive Git tree API returned `truncated=false` and nine tracked file paths:

- `.github/ISSUE_TEMPLATE/rusa-agent-task.yml`
- `.github/agents/rusa-implementation.agent.md`
- `.github/copilot-instructions.md`
- `.vscode/mcp.json` (configuration file; values intentionally not reproduced)
- `README.md` (only `# RusaAi`)
- `docs/CATARAN_WORKER_VALIDATION.md`
- `docs/integrations/a2a-chatgpt-copilot-autonomous.md`
- `docs/integrations/copilot-a2a.md`
- `schemas/a2a/task-envelope.schema.json`

Directories observed: `.github`, `.vscode`, `docs`, and `schemas`.

The earlier Issue #8 statement that README was the only repository content is incomplete. The tracked tree contains collaboration and protocol scaffolding, but no identified runnable model implementation.

## 2. Findings from inspected files

- Copilot instructions define branch/PR discipline, evidence requirements, phase gates, model independence, and tenant/security requirements.
- The Copilot agent profile defines implementation workflow and forbids unsupported claims about training, tests, weights, or A2A handshakes.
- The A2A JSON Schema defines protocol version, task/message UUIDs, message types, sender/recipient, objective, acceptance criteria, repository/branch scope, policy, status, and evidence.
- Integration documents describe ChatGPT as architecture/research/review partner, Copilot as external implementation partner, and RUSA-AI as the target independent model/product.
- The docs explicitly say an MCP configuration template does not create an MCP server or prove a live connection.
- The worker-validation report says its PASS covers GitHub connector READ/WRITE, branch creation, documentation write, and PR creation; it does not prove separate autonomous worker runtimes or application tests.

## 3. Implementation inventory

Earlier root checks did not find `pyproject.toml`, `requirements.txt`, `package.json`, `Cargo.toml`, or `go.mod`.

Not found in the inspected tracked tree:
- Model weights/checkpoints.
- Training/fine-tuning scripts.
- Inference runtime/API/CLI.
- Dataset manifest or labeled evaluation benchmark.
- Application test suite.

Not verified:
- Live A2A handshake.
- Active Copilot coding-agent execution.
- CI success for this baseline.
- Any local/untracked assets or external model artifacts.

This is a tracked-tree and selected-file inspection, not a hardware audit.

## 4. Architecture decision record — local-first

The existing A2A document names local-first deployment as the target. The inspected repository does not establish CPU/GPU/VRAM/RAM/storage, target model size, workload, latency/throughput targets, lawful dataset sources, or training budget. Therefore, selecting a specific model/framework now would be speculative.

| Option | Benefit | Main constraint | Decision |
|---|---|---|---|
| Licensed open-weight model, locally hosted | Fastest path to real inference and measurable resource use | License, provenance, model size, hardware fit | Preferred candidate for P1 evaluation; not yet selected |
| Local fine-tuning of open-weight base | Domain adaptation and own adapter/checkpoint | Lawful data, GPU/VRAM, reproducible training/evaluation | Defer until P0 gates pass |
| Train foundation model from scratch | Maximum control | Very high compute/data/engineering cost | Not justified by current evidence |
| External API as primary runtime | Fast prototype, low local compute | Vendor/network dependency; conflicts with local-only target | Not accepted as production architecture |

**Provisional direction:** evaluate one appropriately licensed open-weight model as a local inference baseline. Keep model artifact, tokenizer, inference runtime, evaluation harness, and orchestration independently identifiable. Fine-tuning is a later gated option. This is not a model selection and does not mean RUSA-AI already has trained weights.

## 5. Required hardware and data evidence

Before selecting a model, collect:
- CPU model and instruction-set support.
- GPU model, VRAM, drivers/runtime, and GPU availability.
- RAM, free disk, and storage type.
- Target context length, concurrency, latency, throughput, and supported tasks.
- Model source, immutable revision/hash, license, and permitted use.
- Dataset provenance, license/consent, privacy classification, and retention rules.
- Local training compute availability and limits.

Model/framework selection and performance estimates remain BLOCKED until these inputs are verified.

## 6. Proposed P1 runnable baseline and acceptance tests

After hardware/license review:
1. Pin one model identifier, revision/hash, tokenizer, and license.
2. Provide a documented local runtime with pinned dependencies and no mandatory vendor API.
3. Add a CLI smoke-test entry point; add HTTP only if required by product scope.
4. Capture fixed test prompts, outputs, latency, CPU/GPU/RAM use, and errors.
5. Test clean setup, model/config loading, inference, invalid config, missing/corrupt artifacts, and restart.
6. Keep model execution tests separate when CI hardware cannot run the model.
7. Ensure logs contain no secrets or private data.

These are proposed tests; none are claimed as executed.

## 7. Risk register

| Risk | Severity | Control | Status |
|---|---|---|---|
| Unclear model license/provenance | High | Verify source, revision, license, permitted use | BLOCKED |
| Unlicensed/private training data | High | Provenance manifest and explicit authorization | BLOCKED |
| Hardware cannot run target model | High | Hardware inventory and candidate benchmark | BLOCKED |
| Dependency/supply-chain drift | High | Pin versions, review provenance, scan packages | OPEN |
| Prompt/config mistaken for trained model | High | Require checkpoint hashes and training logs | CONTROL DOCUMENTED |
| MCP/A2A scaffold mistaken for live connection | High | Authenticated end-to-end handshake evidence | NOT VERIFIED |
| Copilot profile mistaken for active agent | High | Assigned run, branch, PR, and test evidence | NOT VERIFIED |
| Secrets in workspace config/logs | High | Local inspection, environment/secret manager | OPEN |
| Evaluation leakage/misleading metrics | High | Versioned held-out set and fixed metrics | BLOCKED |

## 8. Evidence ledger

| ID | Check | Result |
|---|---|---|
| P0-001 | Repository default branch and base SHA | VERIFIED: `main`, `dccb8140950e97286c0382860e6ac33c3e4cd7b5` |
| P0-002 | Recursive Git tree | VERIFIED: 9 tracked paths; API `truncated=false` |
| P0-003 | Copilot instructions and agent profile | VERIFIED as repository artifacts; activation NOT VERIFIED |
| P0-004 | A2A schema | VERIFIED as file; runtime validation NOT RUN |
| P0-005 | A2A/Copilot docs | VERIFIED as documentation; live handshake NOT VERIFIED |
| P0-006 | Worker validation report | VERIFIED; its stated scope excludes autonomous worker runtimes |
| P0-007 | Common root manifests | NOT FOUND for Python/Node/Rust/Go manifests listed above |
| P0-008 | Model/training/inference/data/eval assets | NOT FOUND in inspected tracked tree |
| P0-009 | Hardware and dataset rights | BLOCKED; evidence unavailable |
| P0-010 | CI and Copilot agent execution | NOT VERIFIED |

## 9. P0 exit assessment and next steps

- Tracked-file inventory: VERIFIED for the returned complete Git tree.
- Collaboration/protocol scaffolding: VERIFIED as documentation/schema artifacts.
- Model/inference implementation: NOT FOUND in inspected tracked tree.
- Concrete model/framework choice: BLOCKED pending hardware, workload, and license evidence.
- P1 plan and acceptance tests: PROPOSED.
- Training, weights, live A2A, autonomous workers, and deployment: NOT VERIFIED.

P0 is PARTIALLY COMPLETE, not fully complete. Next: obtain target hardware/workload; confirm lawful data sources; evaluate a licensed local model; then open a bounded P1 implementation task. Verify Copilot entitlement and a real agent run separately.

## Safety boundary

Documentation only. No main-branch changes, merge, release, deployment, secret/permission changes, compute purchase, or private-data ingestion.
