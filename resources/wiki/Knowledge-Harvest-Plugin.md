# OneBrain Codex Plugin

The OneBrain Codex plugin contains memory-first and harvest skills for agents. It exists to make
Codex consult durable OneBrain context before acting, then turn scattered enterprise systems into
reviewable documentation and OneBrain-ready memories.

## Consult First Skill

`onebrain-consult-first` tells Codex to query OneBrain memory, context packs, skills, and graph
correlations before broad local, web, Azure DevOps, GitHub, Jira, or shell investigation.

The skill prefers:

- `onebrain_get_context` for task-sized context packs;
- `onebrain_search_memory` for prior decisions, runbooks, facts, and pitfalls;
- `onebrain_search_skills` for reusable workflows and standards;
- `onebrain_correlate` or `onebrain_get_graph` for architecture and cross-repository clues.

OneBrain results are treated as remembered context, not unquestioned truth. Current code, current
service state, external facts, and time-sensitive information still need live verification.

## Knowledge Harvest Skill

`onebrain-knowledge-harvest` provides a runner-neutral Python pack writer. It turns scattered
enterprise systems into reviewable documentation and OneBrain-ready memories.

## Providers

| Provider | Collection path |
| --- | --- |
| Local repositories | Direct filesystem read. |
| GitHub | REST metadata, clone/readme/docs, issues, pull requests, wiki clone attempt. |
| Azure DevOps | Prefer Codex MCP export; REST fallback for cloud or non-Codex runners. |
| Jira Cloud | REST project and issue search. |
| OneBrain | HTTP ingest or MCP memory import/add-memory fallback. |

## Pack Contract

Each run writes:

```text
manifest.json
documents/
onebrain-import.jsonl
ingest-result.json  # only when --ingest is used
```

`manifest.json` records:

- sources and provider payload summaries;
- repositories, wikis, pull requests, work items, issues, and active people;
- repository coverage by repo;
- clues extracted per repo;
- cross-repository references;
- ingestion results and per-repo memory status when available;
- explicit errors and partial/inventory classifications.

## Azure DevOps MCP Flow

In Codex, the Python script does not call MCP tools directly. The agent should:

1. Use `mcp__mcp_azuredevops` to list projects and repositories.
2. Use `get_repository_items` and `get_file_content` per selected repository.
3. Collect PRs, work items, and wiki pages.
4. Write an export that follows `sample-azure-devops-mcp-export.json`.
5. Run the harvester with a `kind: "azure-devops-mcp-export"` target.

This keeps provider collection in Codex where MCP tools exist, while keeping the pack writer usable
from cloud, Gemini, CI, and local scripts.

## Running A Local Pack

```powershell
python ops/plugins/onebrain/skills/onebrain-knowledge-harvest/scripts/knowledge_harvest.py `
  --config ops/plugins/onebrain/skills/onebrain-knowledge-harvest/references/sample-source-config.json `
  --output resources/artifacts/onebrain-harvest `
  --skip-network `
  --skip-clone `
  --max-files 80 `
  --max-items 50
```

Add `--ingest` only after reviewing generated docs and coverage:

```powershell
$env:ONEBRAIN_API_URL = "http://127.0.0.1:8088/api/v1"
$env:ONEBRAIN_API_KEY = "<onebrain-key>"

python ops/plugins/onebrain/skills/onebrain-knowledge-harvest/scripts/knowledge_harvest.py `
  --config .\onebrain-source-config.json `
  --output resources/artifacts/onebrain-harvest `
  --ingest
```

## Subagent Rule

For broad harvests, especially 10 or more repositories, the skill must ask for explicit parallel
agent/subagent authorization when the environment requires it. It must not silently continue with a
limited inventory and present it as complete documentation.
