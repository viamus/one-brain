# OneBrain

OneBrain is a production-oriented memory service for LLM tools, coding agents, and personal agent
workflows. It stores durable memories and semantic recall vectors in PostgreSQL with pgvector, then
exposes API, Web, MCP, and Jobs service surfaces.

OneBrain does not use an LLM in its online request path. It remembers, retrieves, ranks, and
explains. The calling LLM, such as Codex, does the deeper reasoning over the context returned by
OneBrain.

## Documentation

Use the public GitHub Wiki as the main operating guide:

- [OneBrain Wiki](https://github.com/viamus/one-brain/wiki)
- [Architecture](https://github.com/viamus/one-brain/wiki/Architecture)
- [Services And Ports](https://github.com/viamus/one-brain/wiki/Services-And-Ports)
- [Graph And Correlation](https://github.com/viamus/one-brain/wiki/Graph-And-Correlation)
- [OneBrain Codex Plugin](https://github.com/viamus/one-brain/wiki/Knowledge-Harvest-Plugin)
- [Operational Runbooks](https://github.com/viamus/one-brain/wiki/Operational-Runbooks)

The reviewable wiki source lives in [resources/wiki](resources/wiki). Sync those Markdown files to
the GitHub Wiki repository when wiki content changes.

For repeatable corpus and graph-scoring experiments, see [resources/docs/corpus-lab.md](resources/docs/corpus-lab.md).

## Quick Start

Requirements:

- Docker 27+ with Docker Compose.
- Optional for local development outside Docker: Python 3.11+, Node.js 22+, and `uv`.

Start the full stack:

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

Open:

- Web console: `http://localhost:8089/`
- Web graph: `http://localhost:8089/graph`
- API health: `http://localhost:8088/healthz`
- API: `http://localhost:8088/api/v1`
- MCP HTTP: `http://localhost:8090/mcp`

Stop the stack:

```powershell
docker compose down
```

## Local Development

Run tests and checks:

```powershell
uv run ruff format .
uv run ruff check .
uv run pytest -q
npm run web:typecheck
```

Run services without the full Docker stack:

```powershell
docker compose up -d postgres
uv sync --dev
npm install
npm run web:build
uv run alembic -c backend/alembic.ini upgrade head
uv run onebrain-api
```

See the [Operational Runbooks](https://github.com/viamus/one-brain/wiki/Operational-Runbooks) for
MCP setup, imports, graph aggregation, classifier training, troubleshooting, and wiki publishing.

## License

OneBrain is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
