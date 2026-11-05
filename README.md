# RUSA AI

RUSA AI is developed as a local-first reasoning, workflow orchestration, and evidence-driven engineering platform.

## Precision Engine v1.1

The RUSA AI Precision Engine separates model reasoning from deterministic workflow control, authorization, evidence validation, and persisted task state.

- [Implementation and local deployment guide](docs/RUSA_AI_PRECISION_ENGINE.md)
- [Copilot/MCP integration status and verification boundary](docs/integrations/rusa-ai-precision-engine-mcp.md)

The v1.1 runtime package is delivered separately as `RUSA_AI_Precision_Engine_v1_1.zip`. Extract it to the workspace folder `RUSA_AI_Precision_Engine_v1_1/` before using the local MCP configuration in `.vscode/mcp.json`. The ZIP SHA-256 is `897324ac03c736e2a8bda4fcccd71c8cc1cdd0dcc14f6ef5e535cf495734cab0`.

## Engineering policy

- Do not push directly to `main`; use reviewed branches and pull requests.
- Distinguish `IMPLEMENTED`, `VERIFIED`, and `DEPLOYED`.
- Do not claim live model, database, MCP, Copilot, or production readiness without execution evidence.
- Human approval is required for high-impact or externally visible actions.
