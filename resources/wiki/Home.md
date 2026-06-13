# OneBrain Wiki

OneBrain is a memory and knowledge platform for agents, coding assistants, and enterprise
automation. It stores durable memories in PostgreSQL with pgvector, exposes API/Web/MCP/Jobs
surfaces, and gives LLM callers deterministic context packs instead of putting an LLM in the
online request path.

This wiki is the operating map for the repository. The source of truth lives in this folder so it
can be reviewed in pull requests and synced to the GitHub Wiki when needed.

## Start Here

- [Architecture](Architecture.md): runtime shape, package boundaries, and data flow.
- [Services And Ports](Services-And-Ports.md): Docker services, ports, health checks, and local
  URLs.
- [Graph And Correlation](Graph-And-Correlation.md): how vector, explicit, and entity links become
  a living graph.
- [Knowledge Harvest Plugin](Knowledge-Harvest-Plugin.md): Codex plugin, supported providers, and
  pack outputs.
- [Repository Harvest Acceptance](Repository-Harvest-Acceptance.md): the criteria that separate
  complete docs from inventory.
- [Environment And Secrets](Environment-And-Secrets.md): where keys live and how runners should
  inject them.
- [Operational Runbooks](Operational-Runbooks.md): common local and CI workflows.

## Current North Star

OneBrain should become the structured memory layer for enterprise agents:

- harvest source systems and repository evidence;
- generate repository-level documentation with provenance;
- detect cross-repository communication clues;
- ingest one durable memory per generated document;
- expose graph and context APIs that agents can query safely;
- keep local, cloud, and Codex execution paths aligned.

## Repository Map

```text
.
+-- backend/
|   +-- src/onebrain/
|   |   +-- core/             # Domain services, contracts, ingestion, graph logic
|   |   +-- infrastructure/   # SQLAlchemy, pgvector, embeddings
|   |   +-- interfaces/       # API, Web host, MCP adapter
|   |   +-- ml/               # Memory classification and training
|   |   +-- platform/         # Django/ASGI/runtime composition
|   |   +-- tools/            # Local importer and operator tooling
|   |   +-- workers/          # Jobs, scheduler, status snapshots
|   +-- tests/
|   +-- migrations/
+-- frontend/web/             # React, TypeScript, Material UI, React Flow
+-- ops/
|   +-- plugins/onebrain/     # Codex plugin and knowledge harvest skill
|   +-- scripts/
|   +-- Dockerfile
+-- resources/
|   +-- docs/                 # Runbooks and architecture notes
|   +-- wiki/                 # Versioned GitHub Wiki source
|   +-- artifacts/            # Local/generated ML artifacts
```

## Documentation Rules

- Keep user-facing operations in wiki pages, not only in PR descriptions.
- Keep implementation detail close to the code when it changes quickly.
- Mark inferred behavior as inferred when documentation comes from filenames, PRs, or structure.
- Add runbook steps when a workflow requires more than one command.
- Do not commit secrets. Use environment variable names and placeholders only.
