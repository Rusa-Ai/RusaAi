# RUSA-AI Local A2A Task Bridge (P3 integration)

This service accepts signed A2A task envelopes on a loopback HTTP endpoint and
places them into the local SQLite task queue.

## Supported first-stage flow

1. A sender prepares the RUSA-AI A2A task envelope from
   schemas/a2a/task-envelope.schema.json.
2. It sends the exact JSON body to POST /v1/tasks with:
   - Content-Type: application/json
   - X-RUSA-Timestamp: Unix timestamp in seconds
   - X-RUSA-Signature: HMAC-SHA256(secret, timestamp + "." + raw_body)
3. The bridge validates the envelope, sender/recipient, task scope, and human
   approval policy; then it idempotently enqueues task.create as a2a.plan.
4. The local worker consumes the task and returns a planning result from the
   configured local model.
5. The result is persisted in SQLite for local retrieval.

The first-stage bridge is planning-only. It does not apply code patches, run
shell commands, write to GitHub, launch Copilot, merge, or deploy.

## Start the ingress server

\`\`\`bash
export RUSA_QUEUE_DB="./var/rusa-tasks.sqlite3"
export RUSA_A2A_INGRESS_HMAC_SECRET="replace-with-a-random-secret-of-at-least-32-characters"
python llm-project/orchestrator/a2a_ingress.py --host 127.0.0.1 --port 8766
\`\`\`

The server rejects non-loopback bind addresses. Do not expose it publicly or on
a LAN. A future remote gateway requires TLS, authentication, rate limiting,
replay protection, authorization, and security review.

## Start the local worker

After a compatible model has been installed in a local OpenAI-compatible
runtime, start the local worker with the same queue database:

\`\`\`bash
export RUSA_MODEL_BASE_URL="http://127.0.0.1:11434/v1"
export RUSA_MODEL_NAME="your-installed-local-model-id"
python llm-project/orchestrator/worker.py serve
\`\`\`

The worker currently registers model.chat and a2a.plan only. A2A tasks are
converted into a scoped planning request; the returned plan is not permission
to execute code or external actions.

## Signature construction

The signature is lowercase hexadecimal HMAC-SHA256 over:

\`\`\`text
<unix_timestamp>.<exact raw request body bytes>
\`\`\`

Use the same UTF-8 bytes that are sent over HTTP. Do not parse and reserialize
the JSON between signing and transmission. Requests with timestamps older/newer
than five minutes are rejected.

## Mandatory policy

Every accepted envelope must include all six human approval gates:
merge, deploy, release, secret_change, permission_change, and destructive_action.
An incoming task cannot weaken these local requirements.

## Evidence boundary

- HMAC validation, envelope validation, queue handoff, and idempotent task IDs
  are covered by offline local HTTP tests.
- This is a local A2A-to-planning bridge; no live ChatGPT/Copilot network
  handshake has been tested.
- A2A callback delivery back to Copilot/ChatGPT is a separate follow-up.
- Local model inference still requires an installed model and a successful
  target-machine smoke test.
