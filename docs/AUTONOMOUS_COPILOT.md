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


## Important activation boundary
Repository custom agent profiles can be tested from this branch in a supported IDE when the branch is checked out. For Copilot cloud agent on GitHub.com, GitHub's documented setup requires the profile files to be merged into the repository's default branch before they appear in the cloud agent picker. This PR intentionally remains unmerged to preserve the owner's no-main-change boundary.

The CI workflow is committed on this feature branch. A workflow run has not yet been verified through the available GitHub connection. GitHub Actions may need to be enabled in repository settings, and a manual `workflow_dispatch` run can be started from the Actions tab after GitHub recognizes the workflow. Do not mark CI as VERIFIED until the run and job logs show success.

## Safe manual smoke test
After the PR is reviewed and merged by the owner (or while using the feature branch in a supported IDE):
1. Open the repository and select the `rusa-autonomous-engineer` custom agent.
2. Ask it to inspect the repository and propose a small documentation-only change.
3. Require a dedicated branch and PR; do not permit direct commits to `main`.
4. Confirm it reads repository instructions, runs available checks, and reports exact evidence.
5. Confirm no merge or deployment occurs without human approval.
