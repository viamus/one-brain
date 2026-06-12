---
name: onebrain-knowledge-harvest
description: Harvest enterprise knowledge from GitHub repositories, GitHub wikis, Azure DevOps repos/wikis/work items/pull requests, Jira projects/issues, and local repositories into OneBrain-ready documentation, metadata manifests, and ingestion payloads. Use when asked to scan repos, clone repos, build a super repository of documentation, extract business flows, map active people, generate missing docs from source evidence, or ingest generated knowledge into OneBrain.
---

# OneBrain Knowledge Harvest

## Operating Model

Use this skill to create a durable knowledge pack before ingesting anything into OneBrain. The pack is a file-system artifact with:

- `manifest.json`: source inventory, discovered projects, repositories, wikis, issues, pull requests, people, and errors.
- `documents/`: generated Markdown documentation for repositories, wikis, work tracking, active people, and business-flow hypotheses.
- `onebrain-import.jsonl`: one MemoryCreate-compatible JSON object per line.

Prefer the bundled script:

```powershell
python ops/plugins/onebrain/skills/onebrain-knowledge-harvest/scripts/knowledge_harvest.py `
  --config ops/plugins/onebrain/skills/onebrain-knowledge-harvest/references/sample-source-config.json `
  --output resources/artifacts/onebrain-harvest
```

Add `--ingest` only after reviewing the generated pack:

```powershell
python ops/plugins/onebrain/skills/onebrain-knowledge-harvest/scripts/knowledge_harvest.py `
  --config .\onebrain-source-config.json `
  --output resources/artifacts/onebrain-harvest `
  --ingest
```

The script reads `ONEBRAIN_API_URL` and `ONEBRAIN_API_KEY` by default. It posts to `/memories` using bearer auth and writes the ingest result back to `ingest-result.json`.

For Azure DevOps inside Codex, prefer the existing MCP before using REST fallback. The reference MCP is `viamus/mcp-azure-devops` at https://github.com/viamus/mcp-azure-devops. If tools under `mcp__mcp_azuredevops` are available, use them for repositories, files, pull requests, work items, builds, and wikis, then write their outputs into the same knowledge pack contract. Use the bundled script's Azure DevOps REST mode only for cloud/Gemini runners or environments where the MCP is not configured.

## Source Configuration

Read `references/source-config.schema.json` before authoring a config. Keep secrets in environment variables, not in the config. The expected provider env vars are:

- GitHub: `GITHUB_TOKEN` or `GH_TOKEN`
- Azure DevOps: `AZURE_DEVOPS_PAT`
- Jira Cloud: `JIRA_EMAIL` and `JIRA_API_TOKEN`
- OneBrain: `ONEBRAIN_API_URL` and `ONEBRAIN_API_KEY`

Use `references/provider-endpoints.md` when changing provider coverage. It records the official APIs this skill is based on.

## Harvest Policy

Extract broadly and preserve provenance. Do not discard a source just because it looks incomplete. If the source lacks explicit docs, generate documentation from available evidence:

- repository description, README, topics, detected languages, paths, dependency files, and recent commits;
- pull request titles, states, reviewers, linked work items, and merge cadence;
- Jira issues, Azure DevOps work items, labels, states, assignees, reporters, and comments when available;
- wiki pages and local documentation files;
- repeated nouns and path names that indicate business domains or integration flows.

Mark generated conclusions as `inferred` in metadata. Use factual language in generated docs: say what was observed and what is inferred from observed artifacts.

## OneBrain Ingestion Shape

The generated memories should use:

- `memory_type`: `context`, `runbook`, `workflow`, `fact`, or `decision`.
- `source.source_type`: `onebrain-knowledge-harvest`.
- `source.source_ref`: stable `onebrain-harvest://...` URI.
- `scope`: copied from the source config plus provider/project/repository details.
- `tags`: provider, repo/project, artifact kind, and business domain hints.
- `metadata`: raw source URL, clone status, active people, generated/inferred flags, and extraction coverage.

When using MCP instead of HTTP, call `onebrain_import_memory_files` against the generated `documents/` folder and pass the same scope plus `source_type=onebrain-knowledge-harvest`.

## Provider Coverage

For GitHub, collect repository metadata, clone URLs, contributors, issues, pull requests, README, local docs from clone, and wiki clone attempts.

For Azure DevOps, collect projects, Git repositories, pull requests, wikis, wiki root pages, WIQL work items, and work item details in batches. In Codex, use `mcp__mcp_azuredevops` first and preserve the MCP result payloads in `manifest.json`.

For Jira Cloud, collect projects and JQL search results. Use active people from assignee, reporter, creator, and status transitions present in the issue payload.

For local repositories, collect remotes, recent commits, top documentation files, source tree signals, and active authors.

## Cloud, Codex, And Gemini

This plugin is Codex-native because it contains `SKILL.md`, but the harvester script and JSON config are runner-neutral. Cloud or Gemini runners should invoke the same script, persist the same pack contract, and ingest through OneBrain HTTP or MCP. Do not rely on Codex-only state inside generated metadata. Azure DevOps MCP usage is a Codex optimization, not a required pack dependency.
