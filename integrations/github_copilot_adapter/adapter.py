#!/usr/bin/env python3
"""Convert a RUSA-AI A2A task.create envelope into a GitHub Issue handoff."""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
WORK_BRANCH_PATTERN = re.compile(r"^(feature|fix|chore|docs)/[A-Za-z0-9._/-]+$")


def require_object(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def validate(data):
    data = require_object(data, "Envelope")
    required = {"protocol_version", "task_id", "message_id", "type", "from", "to", "created_at", "task", "policy"}
    missing = required - data.keys()
    if missing:
        raise ValueError("Missing envelope fields: " + ", ".join(sorted(missing)))
    if data["protocol_version"] != "1.0" or data["type"] != "task.create":
        raise ValueError("Only protocol 1.0 task.create is supported")

    for field in ("from", "to"):
        agent = require_object(data[field], field)
        if not isinstance(agent.get("agent_id"), str) or not agent["agent_id"].strip():
            raise ValueError(f"{field}.agent_id must be a non-empty string")
        if not isinstance(agent.get("role"), str) or not agent["role"].strip():
            raise ValueError(f"{field}.role must be a non-empty string")
    if data["to"]["role"] != "github_copilot":
        raise ValueError("Recipient role must be github_copilot")

    task = require_object(data["task"], "task")
    for key in ("objective", "acceptance_criteria", "repository", "base_branch", "work_branch"):
        if key not in task:
            raise ValueError("Missing task field: " + key)
    if not isinstance(task["objective"], str) or not task["objective"].strip():
        raise ValueError("Objective must be a non-empty string")

    criteria = task["acceptance_criteria"]
    if not isinstance(criteria, list) or not criteria or any(
        not isinstance(item, str) or not item.strip() for item in criteria
    ):
        raise ValueError("Acceptance criteria must be a non-empty list of non-empty strings")

    repository = task["repository"]
    if not isinstance(repository, str) or not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError("repository must match owner/name")
    base_branch = task["base_branch"]
    if not isinstance(base_branch, str) or not base_branch.strip():
        raise ValueError("base_branch must be a non-empty string")

    work_branch = task["work_branch"]
    if not isinstance(work_branch, str) or not WORK_BRANCH_PATTERN.fullmatch(work_branch):
        raise ValueError("work_branch must use feature/, fix/, chore/, or docs/ prefix")
    if work_branch == "main" or work_branch == base_branch:
        raise ValueError("Work branch must be different from the base branch")
    if any(part in ("", ".", "..") for part in work_branch.split("/")[1:]):
        raise ValueError("work_branch contains an invalid path segment")

    policy = require_object(data["policy"], "policy")
    for field in ("allowed_actions", "prohibited_actions", "human_approval_required"):
        values = policy.get(field)
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not item.strip() for item in values
        ):
            raise ValueError(f"policy.{field} must be a list of non-empty strings")


def build_issue(data):
    task = data["task"]
    checks = "\n".join(f"- [ ] {item}" for item in task["acceptance_criteria"])
    title = f"[A2A {data['task_id'][:8]}] {task['objective'][:160]}"
    body = f"""## A2A task handoff
- Task ID: {data['task_id']}
- Message ID: {data['message_id']}
- Sender: {data['from'].get('agent_id', 'unknown')} ({data['from'].get('role', 'unknown')})
- Recipient: {data['to'].get('agent_id', 'copilot')} (GitHub Copilot)
- Repository: {task['repository']}
- Base branch: {task['base_branch']}
- Required work branch: {task['work_branch']}

## Objective
{task['objective']}

## Context
{task.get('context', 'No additional context supplied.')}

## Acceptance criteria
{checks}

## Policy
Allowed: {', '.join(data['policy'].get('allowed_actions', []))}
Prohibited: {', '.join(data['policy'].get('prohibited_actions', []))}
Human approval required: {', '.join(data['policy'].get('human_approval_required', ['merge', 'deploy', 'release']))}

## Completion evidence
Copilot must provide changed files, exact test commands/results, commit SHA, PR URL, limitations and risks. Never claim model training or benchmark success without artifacts and logs.

> This Issue is a handoff only. It does not prove Copilot accepted or started work. Assign/launch Copilot through GitHub where Coding Agent is enabled. No direct push to main, merge, or deployment.
"""
    return title, body


def submit(repo, title, body, token, dry_run=False):
    payload = {"title": title, "body": body}
    if dry_run:
        return {"dry_run": True, "payload": payload}
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=json.dumps(payload).encode(),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "rusa-ai-a2a-copilot-adapter",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"GitHub API {error.code}: {detail}") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="Envelope JSON file; default stdin")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
        data = json.loads(raw)
        validate(data)
        title, body = build_issue(data)
        token = os.getenv("GITHUB_TOKEN", "")
        if not args.dry_run and not token:
            raise ValueError("Set GITHUB_TOKEN in environment; never store it in the envelope/repo")
        result = submit(data["task"]["repository"], title, body, token, args.dry_run)
        print(json.dumps({
            "status": "prepared" if args.dry_run else "submitted",
            "task_id": data["task_id"],
            "issue_number": result.get("number"),
            "issue_url": result.get("html_url"),
            "dry_run": args.dry_run,
        }, indent=2))
        return 0
    except (ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"A2A adapter error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
