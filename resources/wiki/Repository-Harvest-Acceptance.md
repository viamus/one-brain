# Repository Harvest Acceptance

A harvest is not complete just because repositories, PRs, work items, or wikis were listed. It is
complete only when repository documentation and OneBrain ingestion are complete for every selected
active repository.

## Classifications

| Classification | Meaning |
| --- | --- |
| `complete` | Every selected repo has content evidence, an individual Markdown doc, and an individual OneBrain memory. |
| `partial` | At least one repo is missing content, doc generation, or OneBrain memory creation. |
| `inventory` | Only metadata was collected. This must not be presented as documentation. |

## Per-Repository Requirements

Each selected active repository needs:

- individual Markdown document;
- stable `source_ref`;
- `manifest.json.repository_coverage[]` entry;
- attempted content reads or explicit block/error;
- extracted clues;
- cross-reference checks;
- individual OneBrain memory when ingestion is requested or required.

## Minimum Evidence To Read

- `README*`
- `docs/`, architecture, onboarding, runbook files
- dependency manifests such as `package.json`, `pyproject.toml`, `.sln`, `.csproj`, `pom.xml`
- `Dockerfile`, `docker-compose*`, deployment, infra, config files
- `azure-pipelines*.yml`, GitHub Actions, and other CI files
- source tree entrypoints and service/API files
- tests and test configuration

## Required Document Sections

Each repository document should explain:

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
- gaps and inferred fields.

## Clues And Cross References

The cross-reference pass compares:

- repository name mentions;
- shared URLs and hostnames;
- package/library names;
- environment variables;
- queue, topic, producer, consumer, event, gateway, API, client, service, worker terms;
- pipeline references;
- PR/work item references;
- database, cache, storage, and messaging terms.

Relationship strength should stay honest:

- explicit docs or code calls are stronger evidence;
- shared names and variables are inferred hints;
- vector or text similarity is a discovery signal, not proof by itself.
