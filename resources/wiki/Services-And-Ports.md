# Services And Ports

Docker Compose starts the complete OneBrain stack: PostgreSQL, migrations, API, Web, MCP, and Jobs.

## Services

| Service | Purpose | Host URL |
| --- | --- | --- |
| `postgres` | PostgreSQL plus pgvector storage. | `localhost:5432` |
| `migrate` | One-shot Alembic migration runner. | none |
| `onebrain-api` | Protected HTTP API for memories, skills, ingestion, search, context, graph. | `http://localhost:8088` |
| `onebrain-web` | React web console and graph explorer. | `http://localhost:8089` |
| `onebrain-mcp` | MCP streamable HTTP endpoint for Codex and MCP clients. | `http://localhost:8090/mcp` |
| `onebrain-jobs` | Scheduled graph aggregation worker. | none |

## Common Commands

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
docker compose logs -f onebrain-api
docker compose logs -f onebrain-web
docker compose logs -f onebrain-mcp
docker compose logs -f onebrain-jobs
docker compose down
```

## Health Checks

| Surface | Health path |
| --- | --- |
| API | `http://localhost:8088/healthz` and `http://localhost:8088/readyz` |
| Web | `http://localhost:8089/healthz` and `http://localhost:8089/readyz` |
| MCP | `http://localhost:8090/healthz` |

## Persistent Volumes

| Volume | Stores |
| --- | --- |
| `onebrain_postgres_data` | PostgreSQL data, memories, graph tables, vectors. |
| `onebrain_job_status` | Durable worker status snapshots. |
| `onebrain.ml_artifacts` | Runtime memory-classifier model artifacts. |

The volumes are external by default, so `docker compose down` does not remove knowledge state.
