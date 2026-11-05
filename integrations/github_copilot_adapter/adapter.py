#!/usr/bin/env python3
"""Convert a RUSA-AI A2A task.create envelope into a GitHub Issue handoff."""
import argparse, json, os, sys, urllib.error, urllib.request

def validate(data):
    required={"protocol_version","task_id","message_id","type","from","to","created_at","task","policy"}
    missing=required-data.keys()
    if missing: raise ValueError("Missing envelope fields: "+", ".join(sorted(missing)))
    if data["protocol_version"]!="1.0" or data["type"]!="task.create": raise ValueError("Only protocol 1.0 task.create is supported")
    if data["to"].get("role")!="github_copilot": raise ValueError("Recipient role must be github_copilot")
    task=data["task"]
    for key in ("objective","acceptance_criteria","repository","base_branch","work_branch"):
        if key not in task: raise ValueError("Missing task field: "+key)
    if not str(task["objective"]).strip() or not task["acceptance_criteria"]: raise ValueError("Objective and acceptance criteria cannot be empty")
    if task["repository"].count("/")!=1: raise ValueError("repository must be owner/name")
    if task["work_branch"]=="main": raise ValueError("Work branch cannot be main")

def build_issue(data):
    t=data["task"]
    title=f"[A2A {data['task_id'][:8]}] {t['objective'][:160]}"
    checks="\n".join(f"- [ ] {x}" for x in t["acceptance_criteria"])
    body=f"""## A2A task handoff
- Task ID: `{data['task_id']}`
- Message ID: `{data['message_id']}`
- Sender: `{data['from'].get('agent_id','unknown')}` ({data['from'].get('role','unknown')})
- Recipient: `{data['to'].get('agent_id','copilot')}` (GitHub Copilot)
- Repository: `{t['repository']}`
- Base branch: `{t['base_branch']}`
- Required work branch: `{t['work_branch']}`

## Objective
{t['objective']}

## Context
{t.get('context','No additional context supplied.')}

## Acceptance criteria
{checks}

## Policy
Allowed: {', '.join(data['policy'].get('allowed_actions',[]))}
Prohibited: {', '.join(data['policy'].get('prohibited_actions',[]))}
Human approval required: {', '.join(data['policy'].get('human_approval_required',['merge','deploy','release']))}

## Completion evidence
Copilot must provide changed files, exact test commands/results, commit SHA, PR URL, limitations and risks. Never claim model training or benchmark success without artifacts and logs.

> This Issue is a handoff only. It does not prove Copilot accepted or started the task. Assign/launch Copilot through GitHub where Coding Agent is enabled. No direct push to main, merge, or deployment.
"""
    return title,body

def submit(repo,title,body,token,dry_run=False):
    payload={"title":title,"body":body,"labels":["a2a-handoff"]}
    if dry_run: return {"dry_run":True,"payload":payload}
    req=urllib.request.Request(f"https://api.github.com/repos/{repo}/issues",data=json.dumps(payload).encode(),headers={
        "Accept":"application/vnd.github+json","Authorization":f"Bearer {token}",
        "X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json",
        "User-Agent":"rusa-ai-a2a-copilot-adapter"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=30) as res: return json.loads(res.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub API {e.code}: {e.read().decode(errors='replace')}") from e

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",default="-",help="Envelope JSON file; default stdin")
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    try:
        raw=sys.stdin.read() if a.input=="-" else open(a.input,encoding="utf-8").read()
        data=json.loads(raw); validate(data); title,body=build_issue(data)
        token=os.getenv("GITHUB_TOKEN","")
        if not a.dry_run and not token: raise ValueError("Set GITHUB_TOKEN in environment; never store it in the envelope/repo")
        result=submit(data["task"]["repository"],title,body,token,a.dry_run)
        print(json.dumps({"status":"prepared" if a.dry_run else "submitted","task_id":data["task_id"],"issue_number":result.get("number"),"issue_url":result.get("html_url"),"dry_run":a.dry_run},indent=2))
        return 0
    except (ValueError,RuntimeError,json.JSONDecodeError) as e:
        print(f"A2A adapter error: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
