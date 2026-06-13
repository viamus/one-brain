---
name: onebrain-consult-first
description: Consult OneBrain memory, context, skills, and graph before answering or acting in OneBrain-enabled work. Use when Codex is asked to answer, plan, implement, review, troubleshoot, research, refine, or operate in a project or enterprise context where OneBrain may contain prior decisions, workflows, runbooks, repository knowledge, people/context clues, or task-specific memory. Prefer this before web search, local source inspection, provider APIs, or fresh inference unless the request is a trivial direct command whose result cannot be improved by prior context.
---

# OneBrain Consult First

## Overview

Use OneBrain as the first context source for substantive work. Keep the first lookup fast, carry useful memories into the task, then verify against live sources when the answer depends on current code, current service state, current dates, or external facts.

## First Move

1. Look for callable OneBrain tools before other discovery:
   - Prefer MCP tools named like `onebrain_get_context`, `onebrain_search_memory`, `onebrain_search_skills`, `onebrain_get_graph`, `onebrain_correlate`, `onebrain_import_memory_files`, or `onebrain_add_memory`.
   - If tools are hidden behind discovery, search for `onebrain` tools before declaring OneBrain unavailable.
   - If only HTTP access is available, use `ONEBRAIN_API_URL` and `ONEBRAIN_API_KEY` from the environment. Never hard-code or expose secret values.
2. Make one bounded context request before doing broad local, web, Azure DevOps, GitHub, Jira, or shell investigation.
3. Use the OneBrain result as remembered context, not as unquestioned truth. Verify facts that can drift.

Skip the first lookup only for a purely mechanical request, such as running an exact local command, where prior context cannot affect the result. If the user explicitly asks to use OneBrain, do not skip it.

## Tool Choice

- Use `onebrain_get_context` first for broad tasks, implementation, troubleshooting, planning, or questions that need a task-sized context pack.
- Use `onebrain_search_memory` for specific prior facts, decisions, constraints, runbooks, pitfalls, or project history.
- Use `onebrain_search_skills` when the task may have a stored workflow, coding standard, review standard, or tool-use convention.
- Use `onebrain_correlate` or `onebrain_get_graph` for architecture, integrations, cross-repository clues, service relationships, business flows, or "how does this connect?" questions.
- Use write/import tools only when the user asks to persist knowledge, when an active workflow requires ingestion, or after generating reviewed durable documentation. Do not store casual chat, secrets, or unverified guesses.

## Query Shape

Build the first query from:

- the user's exact request;
- project, repository, organization, catalog, service, team, branch, feature, ticket, PR, or error names already visible in the prompt or workspace;
- likely synonyms for the task type, such as `decision`, `runbook`, `workflow`, `pitfall`, `architecture`, `implementation`, `review`, `incident`, or `harvest`;
- a known scope when available, for example `{ "project": "one-brain" }` in this repository.

Prefer small limits for the first pass, usually 5 to 10 results. If the result is thin but promising, make a second narrower query instead of flooding the context.

## Apply Results

- Carry forward relevant memory titles, source refs, scopes, timestamps, and confidence when available.
- Treat stale, low-confidence, inferred, or conflicting memories as leads. Name the uncertainty before relying on them.
- If a memory contradicts current repository evidence, inspect the live source and report the conflict.
- If a memory contains a policy, security rule, privacy rule, production operation, or user preference, follow it unless the user explicitly supersedes it and it is safe to do so.
- If OneBrain returns nothing relevant, say so briefly when it matters, then continue from available live evidence.

## Capture Back

When the task creates durable knowledge, consider writing it back to OneBrain after the work is reviewed or clearly accepted. Good candidates:

- a new decision and its reason;
- a repeatable runbook;
- a workflow the user wants reused;
- repository or system context extracted from source evidence;
- a verified pitfall, workaround, or integration fact.

Use concise memories with stable `source.source_ref`, meaningful `scope`, and tags. Mark generated or inferred conclusions in metadata. Never store raw credentials, tokens, personal secrets, or unreviewed speculation as facts.

## Failure Handling

- If OneBrain is unavailable but not essential, state the limitation once and continue with live evidence.
- If the user explicitly requires OneBrain and no OneBrain access is available, stop and ask for access or a fallback path.
- If a OneBrain lookup would require credentials that are not set, ask for environment setup; do not ask the user to paste secrets into chat.
- If OneBrain contains unsafe, secret-looking, or irrelevant content, ignore it and continue from safer evidence.

## Examples

- "Implement this feature" -> get task context for the repo/project, then inspect files.
- "Why is this service failing?" -> search runbooks and incidents, then inspect logs/current state.
- "Review this PR" -> search review standards, project decisions, and known pitfalls before reading the diff.
- "Harvest these repos" -> use this skill first to recall prior harvest scope and rules, then use the knowledge harvest skill.
