# RUSA-AI Build Roadmap

## Objective
Build RUSA-AI into an independently testable AI system. A repository configuration or agent prompt is not a trained model. Every stage must produce inspectable artifacts and reproducible evidence.

## Current baseline (verified from the default branch)
- The default-branch README currently contains only the project heading `# RusaAi`.
- Common project manifests checked at the repository root (`pyproject.toml`, `requirements.txt`, `package.json`, `Cargo.toml`, `go.mod`) were not found.
- Therefore the implementation language, runtime, model family, data pipeline, tests, and compute environment are not yet established.
- Copilot agent activation and CI execution are not yet verified.

## Delivery phases

### P0 — Repository discovery and architecture decision
Deliver:
- inventory of tracked files and current repository conventions;
- explicit product definition: model, inference runtime, training/fine-tuning scope, and intended interfaces;
- architecture decision record comparing viable local-first model paths against actual hardware and license constraints;
- dependency, data, compute, security, and evaluation risks;
- acceptance criteria and a staged implementation plan.
Do not select a model or framework before inspecting available constraints.

### P1 — Reproducible engineering foundation
Deliver:
- minimal project structure and pinned dependencies;
- configuration and secret-handling rules;
- deterministic smoke tests and CI that match the chosen stack;
- documented local developer setup;
- a minimal runnable baseline with no unsupported performance claims.

### P2 — Data and evaluation pipeline
Deliver:
- dataset manifest with source, license, provenance, and permitted use;
- validation, deduplication, preprocessing, train/validation/test separation, and leakage checks;
- baseline evaluation suite with fixed test cases and metrics;
- data lineage and artifact hashes.
Do not ingest private or unlicensed data without explicit authorization.

### P3 — Model baseline and inference
Deliver:
- a justified baseline model choice and model card;
- reproducible inference API/CLI and local runtime;
- resource measurements (CPU/GPU/RAM/storage) and latency;
- functional, safety, and regression evaluations.
Use pretrained/open-weight models only when license and provenance are verified. Do not claim RUSA-AI has its own trained weights unless training produced verifiable artifacts.

### P4 — Training or fine-tuning
Proceed only after P0-P3 evidence and compute/data approval.
Deliver:
- versioned training configuration and reproducible scripts;
- checkpoint/artifact hashes, logs, hardware details, and dataset versions;
- held-out evaluation against the baseline;
- rollback and model-release procedure.
Training may be deferred if available compute or data does not justify it.

### P5 — Autonomous engineering loop
Deliver:
- issue-to-branch-to-PR workflow for bounded tasks;
- worker ownership and handoff contracts;
- test, security, and review gates;
- evidence ledger and failure/retry limits;
- human approval for merge, secrets, external spend, and production deployment.

## Non-negotiable controls
- Never commit directly to `main`; use a task branch and PR.
- Never merge or deploy without explicit owner approval.
- Do not alter secrets, billing, repository permissions, or external infrastructure.
- Do not invent tests, benchmarks, model weights, training runs, or deployment status.
- Mark each requirement IMPLEMENTED, VERIFIED, or DEPLOYED only when matching evidence exists.
