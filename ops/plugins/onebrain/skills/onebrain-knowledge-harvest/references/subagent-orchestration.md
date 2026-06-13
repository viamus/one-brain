# Subagent Query Orchestration

Use parallel agents/subagents to reduce harvest time whenever the request spans more than one source, project, repository, wiki, or work-tracking query. The main agent stays as the orchestrator and final pack owner.

## Authorization Rule

Some Codex surfaces only permit spawning subagents when the active user request explicitly asks for `parallel agents` or `subagents`. Skill instructions alone may not count as that explicit authorization.

If subagents are needed and the environment reports that explicit authorization is required:

1. Do not continue with a local-only harvest by default.
2. Ask: `Posso usar parallel agents/subagents para dividir esse harvest?`
3. Continue with subagent fan-out after approval.
4. Continue local-only only when the user denies, subagent tools are absent, or the user explicitly requests local-only execution.

## Default Strategy

1. Build a source inventory from the config or user request.
2. Partition the inventory into independent slices:
   - Azure DevOps: organization/project/repository/wiki/work-item query slices.
   - GitHub: owner/repository/wiki slices.
   - Jira: project or JQL window slices.
   - Local repositories: repository or directory-family slices.
3. Launch subagents for independent read-only collection slices when available and authorized.
4. Require every subagent to write a bounded artifact to the run output folder.
5. Merge artifacts in the main agent and run the bundled script or equivalent pack writer once.
6. Run a cross-reference pass across all slices before declaring coverage complete.

## Subagent Prompt Contract

Give each subagent only its slice and the output path it owns. Do not ask subagents to ingest into OneBrain or mutate live systems.

Use this shape:

```text
Use the OneBrain knowledge harvest contract to collect evidence for this slice only.
Provider: <provider>
Scope: <org/project/repo/wiki/query>
Output: <absolute-output-folder>/<slice-id>.json

Collect repositories, repository file contents, wikis, pull requests, issues/work items, active people, source URLs, clues, and concise business-flow evidence. For every repository in scope, read content files or record an explicit per-repository block. Extract cross-reference clues such as URLs, package names, env vars, queue/topic names, service/client/API terms, and mentions of other repos. Do not ingest into OneBrain. Do not modify source systems. Return the artifact path and any errors.
```

For Azure DevOps in Codex, subagents should prefer `mcp__mcp_azuredevops` tools and write data using the `sample-azure-devops-mcp-export.json` shape. Use `get_repository_items` to discover README/docs/manifests/pipelines/source/test files and `get_file_content` to export their contents. Inventory-only slices are not complete.

## Concurrency Guardrails

- Start with 3 to 5 subagents for normal harvests.
- Use 6 to 8 only for very large catalogs when the tools and services are healthy.
- Keep one subagent per independent source slice; avoid multiple subagents querying the exact same repository or work item range.
- Bound each slice with `max_items`, date windows, repository lists, or project lists.
- If rate limits, auth failures, or service errors appear, reduce concurrency and continue with the completed artifacts.

## Merge Rules

The main agent merges by stable keys:

- Repository: `provider + organization/owner + project + repository`.
- Pull request: `provider + repository + pullRequestId/number`.
- Work item or issue: `provider + project/repository + id/key`.
- Wiki: `provider + project/repository + wiki id/name`.
- Person: normalized display name, unique name, email, or login.
- Clue: `clue_type + normalized value`.

Preserve provenance. Keep each subagent artifact path in final metadata when possible.

## Output Layout

Recommended run layout:

```text
resources/artifacts/onebrain-harvest/
  slices/
    ado-project-a.json
    github-repo-x.json
    jira-project-y.json
  manifest.json
  documents/
  onebrain-import.jsonl
```

Use `azure-devops-mcp-export` targets for Azure DevOps slice files. For other providers, either create smaller source configs per slice and run the bundled script per slice, or normalize slice artifacts into the same final pack contract before merge.

## Main-Agent Responsibilities

- Decide partitioning and concurrency.
- Launch and monitor subagents.
- Inspect failed slices and retry only the failed scope.
- Merge and deduplicate artifacts.
- Build cross-references from clues and explicit repository mentions.
- Reject inventory-only slices as complete output.
- Run validation and smoke checks.
- Review generated docs before ingestion.
- Perform OneBrain ingestion only after the pack is reviewed or explicitly approved.
