# RUSA-AI A2A Callback Inbox

This is a local, authenticated callback receiver for task lifecycle events sent by a GitHub Copilot-side integration.

## Implemented in this branch

- HTTP `POST /v1/callbacks` receiver.
- HMAC-SHA256 request authentication over `timestamp + "." + raw_body`.
- Five-minute timestamp tolerance to reduce replay exposure.
- Strict callback envelope validation and a 1 MiB body limit.
- SQLite persistence with `message_id` as a unique key (idempotent duplicate handling).
- Authenticated `GET /v1/tasks/{task_id}/callbacks` polling endpoint.
- Loopback-only bind address by default.
- Unit tests for envelope validation, signature verification, tamper detection, timestamp expiry, and persistence/idempotency.

## Not implemented / important boundary

- This inbox does not itself receive GitHub webhooks or launch Copilot.
- No production TLS termination, public hosting, OAuth, rate limiting, key rotation, multi-tenant authorization, or operational monitoring is included.
- No ChatGPT app connector or live ChatGPT callback/polling integration is configured by this repository change.
- A Copilot-side sender must be implemented and configured to POST callbacks.
- A live two-way A2A handshake is **not** claimed until a sender, reachable endpoint, authenticated POST, and authenticated retrieval are exercised end-to-end.

## Run locally

Python 3.10+; standard library only.

Generate independent secrets and store them in a local secret manager or environment (never commit them):

```bash
export RUSA_CALLBACK_HMAC_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export RUSA_CALLBACK_READ_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python integrations/a2a_callback/receiver.py --host 127.0.0.1 --port 8765
```

The service creates a SQLite database at `rusa_callbacks.sqlite3` by default. Use `--database` to select another local path.

## Callback signing contract

The sender must:
1. Serialize the callback envelope to UTF-8 JSON bytes.
2. Set `X-RUSA-Timestamp` to the current Unix timestamp in seconds.
3. Compute HMAC-SHA256 using `RUSA_CALLBACK_HMAC_SECRET` over the exact bytes `timestamp + "." + raw_body`.
4. Set `X-RUSA-Signature` to the lowercase hexadecimal digest.
5. POST the raw JSON body to `/v1/callbacks`.

Allowed event types: `task.accepted`, `task.progress`, `task.completed`, `task.failed`.

The reader polls `/v1/tasks/{task_id}/callbacks` with `Authorization: Bearer <RUSA_CALLBACK_READ_TOKEN>`.

Required envelope fields: `protocol_version` (`1.0`), `message_id`, `task_id`, `type`, `from`, `to`, and `created_at`. Sender role must be `github_copilot`; recipient role must be `a2a_gateway`.

## Tests

```bash
python -m unittest discover -s integrations/a2a_callback/tests -v
python -m compileall -q integrations/a2a_callback
```

Do not expose this service to the public internet without a separate security design and deployment review. Merge, deployment, secret/permission changes, and destructive operations remain human-approved.
