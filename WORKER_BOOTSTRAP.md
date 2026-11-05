# RusaAI Worker Bootstrap

## Current scope

This branch adds a safe GitHub Actions bootstrap for the RusaAI worker with a provider-neutral (`flexible`) model contract. It is a validation scaffold, not an always-on worker and not a production inference service.

## Runtime behavior

- `worker-bootstrap-ci` runs standard-library unit tests and a configuration dry-run on pushes to this feature branch, pull requests targeting `main`, and manual dispatch.
- `rusaai-worker-manual` can be started manually from the GitHub Actions tab. Its only permitted mode is `dry-run`.
- The dry-run validates configuration and reports `CONFIG_VALID`; it does not claim tasks, call a model, access external services, or require secrets.
- A normal worker invocation returns `BLOCKED` until a durable queue adapter and a concrete model-provider adapter have been implemented and reviewed.

## Provider contract

`RUSAAI_MODEL_PROVIDER` defaults to `flexible`. The contract is intentionally provider-neutral. No OpenAI, Anthropic, or other provider SDK is installed, selected, or called. Add a concrete adapter only after provider selection, secret handling, timeout/retry policy, data-processing review, and tests are approved.

## Missing production dependencies

1. Durable queue with atomic claims, leases, retries, idempotency, and dead-letter handling.
2. Concrete model-provider adapter and secret injection through GitHub Actions secrets or a dedicated secret manager.
3. Durable task/evidence storage and tenant-aware authorization boundaries.
4. Authenticated Founder approval provenance for protected actions.
5. Operational telemetry, alerting, rate limits, and cost controls.
6. A persistent runtime if continuous 24/7 processing is required. GitHub-hosted Actions runners are ephemeral and execute only on events or manual dispatch.

## Security posture

- Workflow token permission is read-only (`contents: read`).
- No repository secrets are referenced or emitted.
- No production database, RLS, IAM, deployment, merge, or branch protection settings are modified.
- The worker fails closed when execution adapters are missing.

## Local verification

```bash
python -m unittest discover -s tests -v
python -m rusa_worker --dry-run
python -m rusa_worker  # expected exit code 2 until adapters exist
```

## Status vocabulary

- Implemented: GitHub Actions workflows, configuration validation, provider/queue interfaces, fail-closed bootstrap, unit tests.
- Tested: local unit tests and workflow CI after GitHub reports a successful run.
- Verified: only after independently inspecting the workflow run and its logs.
- Production-proven: NOT VERIFIED; requires real queue/provider integration, security and tenant-isolation testing, and operational evidence.
