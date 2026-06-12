# OneBrain Next Phase Architecture

Date: 2026-06-12

## Decisions

### Web

OneBrain Web is now a React + TypeScript workspace under `frontend/web`.

- Runtime UI: React.
- Build tool: Vite.
- Design system: Material UI, aligned with Material Design.
- Graph surface: React Flow for draggable nodes, typed edges, minimap, pan, zoom, and live
  inspection.
- Backend host: Django still serves `/`, `/graph`, `/graph/data`, and `/web/assets/*`.

This keeps API/Web/MCP/Jobs deployment stable while moving human-facing UI out of Python string
templates.

### Vector Store

Qdrant is removed from the base stack. Vector recall now lives in PostgreSQL through pgvector.

Reasoning:

- OneBrain already uses PostgreSQL as canonical storage.
- pgvector stores embeddings in the same transactional boundary as memories.
- pgvector supports cosine distance and approximate indexes such as HNSW.
- Redis remains a future cache/queue candidate, but it is not the right replacement for semantic
  vector recall in this phase.

References:

- [pgvector project](https://github.com/pgvector/pgvector)
- [pgvector Docker image tags](https://hub.docker.com/r/pgvector/pgvector/tags)

### Jobs

OneBrain Jobs now follows an Onion Ring shape.

- Edge: Django management commands parse CLI options and print output.
- Ring: `onebrain_jobs.ring` owns execution lifecycle, status persistence, and scheduler callbacks.
- Job: concrete job modules own config, formatting, and `run_once`.
- Core: domain behavior remains in `onebrain_core`.

This removes duplicated start/result/error flows from command files and makes future jobs easier to
add without copying scheduler wiring.

## Monorepo Layout

```text
.
+-- backend/
|   +-- src/                  # Python packages
|   +-- migrations/           # Alembic migrations
|   +-- tests/                # Python tests
+-- frontend/web/             # React + TypeScript + Material UI + React Flow
+-- ops/                      # Dockerfile and lab scripts
+-- resources/docs/           # Runbooks and architecture notes
+-- resources/artifacts/      # Local/generated ML artifacts
+-- package.json               # npm workspace root
+-- pyproject.toml             # Python project root
```
