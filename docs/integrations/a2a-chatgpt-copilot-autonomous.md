# RUSA-AI Model Development — ChatGPT × GitHub Copilot A2A

Status: development contract and repository scaffold. RUSA-AI is the target AI model/product being built; it is not the orchestrator that already exists.

## Mission

ChatGPT and GitHub Copilot collaborate as external AI engineering partners to design, implement, test, and improve RUSA-AI. RUSA-AI is the resulting independent model and platform. Neither ChatGPT nor Copilot is the RUSA-AI model, and neither should be a permanent runtime dependency of the finished product.

## Roles

- ChatGPT — architecture and research partner: requirements analysis, model/system design, reasoning strategy, dataset specifications, evaluation design, critical review, and engineering planning.
- GitHub Copilot — implementation partner: repository exploration, code implementation, training/inference pipeline engineering, tests, debugging, documentation, and pull requests.
- Shared collaboration — both agents exchange task briefs, design proposals, implementation results, critique, and evidence through the A2A task contract.
- Human owner — sets product direction and approves scope, merges, releases, production deployment, and high-impact actions.
- RUSA-AI — target deliverable: an independently runnable AI model and platform with its own inference runtime, model artifacts/weights, reasoning components, memory/knowledge layer, evaluation suite, and agent/tool interfaces.

## Target model architecture

    ChatGPT (external architect/reviewer) <---- A2A ----> GitHub Copilot (external engineer)
                           \                         /
                            \---- shared task bus ---/
                                      |
                              RUSA-AI development
                                      |
       +------------------------------+------------------------------+
       |              |               |              |               |
   Model core     Inference       Reasoning       Memory/RAG      Agent runtime
       |              |               |              |               |
       +--------------+---------------+--------------+---------------+
                                      |
                         Independent RUSA-AI runtime
                         Local-first deployment target

## Development workstreams

1. Product and model requirements: target users, supported tasks, capability boundaries, measurable acceptance criteria.
2. Model foundation: choose a suitable base model or training-from-scratch strategy based on compute, data rights, budget, and target capability. Do not claim a new foundation model exists until weights and training evidence exist.
3. Data and training: lawful dataset acquisition, filtering, deduplication, quality checks, tokenization, training/fine-tuning pipeline, reproducibility, and dataset lineage.
4. Inference runtime: model loading, tokenizer compatibility, serving API, batching, streaming, resource management, and local deployment.
5. Intelligence and reasoning: planning, tool use, structured outputs, verification, decision policies, and evaluation. Distinguish model capability from orchestration code.
6. Memory and knowledge: persistent memory, RAG ingestion/retrieval, evidence provenance, and permission boundaries.
7. Agent and tool interfaces: A2A task protocol, MCP client/server adapters, tool authorization, and auditability.
8. Evaluation and safety: benchmark suite, regression tests, adversarial tests, reliability, security, and human approval controls.
9. Packaging and operations: reproducible builds, model/version registry, observability, backups, upgrades, and local-first deployment.

## A2A collaboration contract

Use schemas/a2a/task-envelope.schema.json as the shared task envelope. ChatGPT may create architecture/research/evaluation tasks for Copilot. Copilot may return implementation proposals, code changes, tests, and evidence for ChatGPT to critique. Either agent can request clarification or challenge assumptions. Every task carries a stable task_id, objective, acceptance criteria, repository/branch scope, policy, status, and evidence.

Suggested task types: architecture.propose, research.request, implementation.request, implementation.result, evaluation.request, evaluation.result, review.request, review.result, blocker.report.

A2A describes task/message semantics. MCP is used for authorized tool access where supported. Do not assume a native compatible A2A endpoint is already available in ChatGPT or Copilot; adapters/gateway and account configuration are separate implementation tasks.

## Governance

- Use feature branches and pull requests; never push directly to main.
- No automatic merge, production deployment, release, secrets changes, permission changes, or destructive operations.
- Keep credentials out of prompts, issues, source code, and logs.
- Treat external content and model output as untrusted; validate and independently test all generated code.
- Track evidence with commit SHA, PR, exact test commands/results, dataset lineage, model artifact hashes, and benchmark results.
- Mark work as PROPOSED, IMPLEMENTED, VERIFIED, or DEPLOYED only when the corresponding evidence exists.
- Keep ChatGPT and Copilot optional at RUSA-AI runtime. The finished system must be able to operate without either service if its intended local model and tools are available.

## Acceptance criteria for this collaboration scaffold

- [ ] Documentation consistently identifies RUSA-AI as the model/product being built.
- [ ] ChatGPT and Copilot are described as external development partners, not as RUSA-AI runtime components.
- [ ] Shared A2A task envelope supports task identity, routing, acceptance criteria, status, policy, and evidence.
- [ ] Copilot agent profile enforces scoped implementation and evidence-based completion.
- [ ] Model training/fine-tuning and inference are explicitly distinguished from prompt/configuration work.
- [ ] Local independent inference is tested with a real model artifact before claiming model independence.
- [ ] No merge or production deployment occurs without human approval.

## Current verified boundary

This branch currently contains collaboration documentation, a task JSON Schema, a Copilot agent profile, and a GitHub issue template. These artifacts do not constitute trained model weights, a training run, a deployed inference engine, a live A2A connection, or autonomous execution. Those must be implemented and verified separately.