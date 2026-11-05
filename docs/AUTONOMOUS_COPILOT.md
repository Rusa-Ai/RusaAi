# RUSA-AI Autonomous Copilot Coding

## Purpose
This repository configuration gives GitHub Copilot reusable specialist roles, repository-wide instructions, and a baseline CI workflow. It does not itself create a continuously running agent, train an AI model, provision compute, or establish a live ChatGPT-to-Copilot A2A connection.

## Available custom agents
- `rusa-autonomous-engineer`: primary implementation and debugging worker.
- `rusa-project-manager`: task decomposition and acceptance criteria.
- `rusa-database-engineer`: schema and migration work.
- `rusa-security-reviewer`: security review.
- `rusa-qa-engineer`: test design and verification.
- `rusa-devops-engineer`: CI/build/deployment safety.
- `rusa-integration-engineer`: module and contract integration.

Profiles live in `.github/agents/`; repository-wide instructions live in `.github/copilot-instructions.md` and `AGENTS.md`.

## Suggested operating procedure
1. Create a GitHub issue with scope, acceptance criteria, constraints, and test expectations.
2. Assign the issue to Copilot or start a Copilot coding-agent session, if enabled for this repository.
3. Select `rusa-autonomous-engineer` or a specialist profile.
4. Require a task branch and a pull request targeting `main`.
5. Review the diff, CI result, security findings, and evidence before merging.
6. Keep merge and production deployment under human approval.

## CI scope
`.github/workflows/autonomous-ci.yml` runs repository-integrity checks on pull requests and selected branch pushes. Python source files receive a syntax compilation check. A Node project with `package-lock.json` receives `npm ci` and `npm test --if-present`.

This is a baseline, not a complete test strategy. It does not install arbitrary Python project dependencies or run an unknown test framework. Extend it after identifying the repository's actual stack.

## Enablement checklist
- Enable GitHub Copilot coding agent for the repository/account where eligible.
- Confirm repository Actions are enabled.
- Confirm Copilot can create branches and pull requests under the repository's configured permissions.
- Review Actions permissions and branch protection/rulesets in GitHub settings.
- Do not grant write permissions to CI unless a reviewed workflow specifically requires them.
- Verify each custom agent appears in the Copilot agent picker in the supported IDE or GitHub interface.
