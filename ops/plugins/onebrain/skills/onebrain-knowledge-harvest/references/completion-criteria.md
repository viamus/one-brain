# Completion Criteria

This skill must distinguish complete documentation from inventory. A list of repositories, pull requests, work items, or wiki names is not a complete OneBrain harvest.

## Complete

A harvest is complete only when every selected active repository has:

- one individual Markdown document;
- one individual OneBrain memory created from that document;
- a stable repository source ref such as `onebrain-harvest://azure-devops/ORG/PROJECT/repositories/REPO`;
- repository coverage in `manifest.json` with `status: documented`;
- extracted clues and cross-repository reference checks;
- evidence from repository content or an explicit error if content could not be read.

## Partial

A harvest is partial when any selected repository lacks content reads, lacks an individual document, lacks an individual memory, or has unresolved errors. Partial output may still be useful as a map, but it must not be described as complete documentation.

## Inventory

Inventory is only repository, PR, wiki, and work item metadata. Inventory is not documentation. Do not upload inventory-only results as if they were complete repository knowledge.

## Minimum Repository Document

Each repository document must include:

- observed or inferred purpose;
- stack and language signals;
- structure and main folders;
- APIs and services;
- pipelines;
- dependencies;
- integrations;
- business flow;
- tests;
- evidence files used;
- known gaps.
- cross-repository clues and likely integration references.

Mark any conclusion as `inferred` when it comes from file names, PRs, work item titles, folder structure, or dependency names rather than explicit documentation.

## Minimum Evidence

For each repo, attempt to read:

- `README*`;
- docs folders and architecture/runbook/onboarding docs;
- `package.json`, `pyproject.toml`, `requirements.txt`, `.sln`, `.csproj`, `pom.xml`, or equivalent dependency manifests;
- `Dockerfile`, `docker-compose*`, deployment manifests, infra, and config files;
- `azure-pipelines*.yml`, GitHub Actions, or other pipeline YAML;
- source tree entrypoints and important service/API files;
- tests and test configuration.

For Azure DevOps MCP, use `get_repository_items` and `get_file_content` per selected repository. If file reads are too slow, split by repo through parallel agents. If file reads and clone are both unavailable, stop and ask before producing limited output.

## Manifest Requirements

`manifest.json` must include per repository:

- `status`: `documented`, `partial`, or `failed`;
- `files_read`;
- `docs_generated`;
- `memory_id` when available;
- `memory_created`;
- `source_ref`;
- `errors`;
- `inferred_fields`.

It must also include:

- `clues`: per-repository clues extracted from docs and source evidence;
- `cross_references`: shared clues and repository-to-repository references;
- enough evidence to explain why two repositories may communicate or belong to the same business flow.

The final summary must state coverage truthfully:

- `complete`: all selected active repositories documented and indexed;
- `partial`: one or more repositories missing content, document, or memory;
- `inventory`: only metadata collected.

Use separate booleans for documentation and ingestion when possible. A pack can be `documentation_complete: true` while still being `complete: false` until repository memories are created in OneBrain.

## Clues And Cross References

After individual repository documentation, run a cross-reference pass across all selected repositories. Extract and compare:

- repository name mentions;
- shared URLs and host names;
- package and library names;
- environment variables;
- API, client, worker, service, gateway, queue, topic, producer, consumer, and event terms;
- pipeline references;
- work item and PR references;
- database, cache, storage, and messaging terms.

Do not overstate the relationship. If the evidence is a shared variable name or a naming match, mark the relationship as inferred. If explicit docs or code show a call, queue, topic, client, or API route, mark the evidence more strongly and preserve the source file path.

## OneBrain Ingestion

Upload one memory per generated document. Do not upload only a general summary when repository docs exist.

Preferred path:

1. Generate `documents/`, `manifest.json`, and `onebrain-import.jsonl`.
2. Review coverage.
3. Ingest all generated repository documents.
4. Confirm generated document count equals inserted memory count, excluding explicit errors.

Fallback path:

1. If `onebrain_import_memory_files` fails due path mapping, read `onebrain-import.jsonl`.
2. Call `onebrain_add_memory` for each memory object.
3. Record inserted memory ids back into the delivery notes or manifest when possible.

## Stop Conditions

Stop and ask before continuing when:

- subagents are needed but require explicit authorization;
- 10 or more repos must be harvested without parallel agents;
- Azure DevOps repo content cannot be read through MCP and no clone/PAT path exists;
- the only available output would be an inventory summary.
