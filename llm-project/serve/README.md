# RUSA-AI Local Inference Runtime (P1 vertical slice)

This is a small standard-library client for a model server that is already
running on the same machine. It speaks the OpenAI-compatible \`/v1/models\`
and \`/v1/chat/completions\` endpoints (for example, Ollama's local API).

## Safety and scope

- Requests are restricted to \`localhost\`, \`127.0.0.0/8\`, or \`::1\`.
- HTTPS and non-loopback hosts are rejected by design.
- No external model API, credentials, model download, training, or telemetry is used.
- The runtime does not bundle model weights. Install a model locally and comply
  with its license before calling inference.
- A reachable endpoint is not the same as a model being installed or inference
  being ready. \`health\` reports process reachability and configured model
  availability separately.

## Prerequisites

- Python 3.10 or newer.
- A local OpenAI-compatible inference server listening on loopback.
- A model already installed by the operator.

For an Ollama-compatible local server, the default URL is
\`http://127.0.0.1:11434/v1\`.

## Configure

Set the model identifier to a model that is already installed locally:

\`\`\`bash
export RUSA_MODEL_NAME="your-installed-model-id"
# Optional overrides:
export RUSA_MODEL_BASE_URL="http://127.0.0.1:11434/v1"
export RUSA_MODEL_TIMEOUT_SECONDS="60"
export RUSA_MODEL_MAX_TOKENS="512"
\`\`\`

Do not put secrets or private data in shell history. The default runtime does
not require an API key and deliberately rejects remote endpoints.

## Check local endpoint and model availability

From the repository root:

\`\`\`bash
python llm-project/serve/local_runtime.py health
\`\`\`

Exit code is 0 when the endpoint is reachable and the configured model (if
specified) is listed. It is 1 for an unreachable/absent configured model and 2
for invalid configuration or request errors.

## Send one chat request

\`\`\`bash
python llm-project/serve/local_runtime.py chat --message "Introduce RUSA-AI."
\`\`\`

Or pass \`--model your-installed-model-id\` to override the environment setting.

## Run offline unit tests

\`\`\`bash
python -m unittest discover -s llm-project/tests -p "test_local_runtime.py" -v
\`\`\`

Tests use mocked HTTP responses. They validate request construction, loopback
policy, input validation, health-state distinctions, and error handling; they
do not prove a live model is installed or that generation quality is acceptable.

## Evidence status

- Runtime client source: IMPLEMENTED by this PR.
- Offline unit tests: committed; execution is VERIFIED only after CI reports success.
- Live local inference and model quality: NOT VERIFIED until run on the operator's
  machine with an identified model and recorded hardware/model revision.
