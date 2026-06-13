# Operational Runbooks

This page collects the repeatable commands operators need most often.

## Build And Start

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

## Stop

```powershell
docker compose down
```

## Reset Local Knowledge

Preview:

```powershell
.\ops\scripts\onebrain-lab-reset.ps1
```

Apply:

```powershell
.\ops\scripts\onebrain-lab-reset.ps1 -Apply
```

The reset removes PostgreSQL and job status volumes. It preserves ML artifacts unless the script is
extended to remove them.

## Run Tests And Linters

```powershell
uv run ruff format .
uv run ruff check .
uv run pytest -q
npm run web:typecheck
```

## Run Services Without Docker

```powershell
docker compose up -d postgres
uv sync --dev
npm install
npm run web:build
uv run alembic -c backend/alembic.ini upgrade head
uv run onebrain-api
```

In separate terminals:

```powershell
uv run onebrain-web
uv run onebrain-mcp-http
uv run onebrain-jobs run_scheduled_jobs --job graph-aggregation
```

## Train Memory Classifier

```powershell
docker compose run --rm onebrain-jobs `
  onebrain-jobs train_memory_classifier `
  --model-out /var/lib/onebrain/ml/memory-classifier.json `
  --json
```

## Run Graph Aggregation

Preview grouping opportunities before writing aggregate memories:

```powershell
docker compose run --rm onebrain-jobs `
  onebrain-jobs aggregate_graph_memories `
  --scope-json '{"catalog":"private-engineering-catalog","source":"github-private-catalog"}' `
  --dry-run `
  --scoring-profile deterministic-v1 `
  --min-score 8 `
  --limit 500 `
  --correlation-limit 750 `
  --max-degree 12 `
  --grouping-limit 25 `
  --grouping-min-size 3
```

Materialize after reviewing the dry-run output:

```powershell
docker compose run --rm onebrain-jobs `
  onebrain-jobs aggregate_graph_memories `
  --scope-json '{"catalog":"private-engineering-catalog","source":"github-private-catalog"}' `
  --scoring-profile deterministic-v1 `
  --min-score 8
```

Useful flags:

- `--scope-json`: restricts graph inputs. Prefer scoped runs.
- `--aggregate-scope-json`: overrides scope on generated aggregate memories.
- `--memory-type`: filters graph inputs by memory type.
- `--scoring-profile`: selects the executable correlation scorer, usually `deterministic-v1` or
  `deterministic-v2`.
- `--limit`: caps memory scan size.
- `--correlation-limit`: caps generated correlation edges.
- `--max-degree`: caps correlation edges per memory.
- `--grouping-limit`: caps grouping opportunities.
- `--grouping-min-size`: minimum members for a grouping opportunity.
- `--min-score`: skips materialization below a score threshold.
- `--dry-run`: reports opportunities without creating memories or links.

Scheduler environment variables:

- `ONEBRAIN_GRAPH_AGGREGATION_QUERY`
- `ONEBRAIN_GRAPH_AGGREGATION_SCOPE_JSON`
- `ONEBRAIN_GRAPH_AGGREGATION_AGGREGATE_SCOPE_JSON`
- `ONEBRAIN_GRAPH_AGGREGATION_MEMORY_TYPE`
- `ONEBRAIN_GRAPH_AGGREGATION_SCORING_PROFILE`
- `ONEBRAIN_GRAPH_AGGREGATION_LIMIT`
- `ONEBRAIN_GRAPH_AGGREGATION_CORRELATION_LIMIT`
- `ONEBRAIN_GRAPH_AGGREGATION_MAX_DEGREE`
- `ONEBRAIN_GRAPH_AGGREGATION_GROUPING_LIMIT`
- `ONEBRAIN_GRAPH_AGGREGATION_GROUPING_MIN_SIZE`
- `ONEBRAIN_GRAPH_AGGREGATION_MIN_SCORE`
- `ONEBRAIN_GRAPH_AGGREGATION_SOURCE_TYPE`
- `ONEBRAIN_GRAPH_AGGREGATION_LINK_TYPE`
- `ONEBRAIN_GRAPH_AGGREGATION_DRY_RUN`

The job has no token cost and does not call GenAI, but it still costs database reads, facet pair
scoring, and pgvector searches. Use stable scopes, bounded limits, `--dry-run`, and `--min-score`
before scheduled writes.

The public job status endpoint and Web Settings tab expose the configured scoring profile plus the
registered strategy catalog. Planned ML profiles are visible for roadmap alignment, but the job
rejects them until their training and artifact loading path exists.

## Import Local Knowledge

```powershell
$env:ONEBRAIN_IMPORT_SCOPE_JSON = '{"organization":"abinbev","catalog":"private-engineering-catalog"}'

uv run onebrain-local-import `
  --docs C:\DoxieOS\github-private-catalog\libraries\ambevtech-developer-memory `
  --api-url http://localhost:8088/api/v1 `
  --api-key $env:ONEBRAIN_MCP_CLIENT_KEY `
  --source-type private-catalog-library `
  --source-ref-prefix catalog://private/libraries/ambevtech-developer-memory `
  --exclude-examples
```

## Publish Wiki Source Manually

If the GitHub Wiki repository exists or can be initialized:

```powershell
$wiki = Join-Path $env:TEMP "one-brain-wiki"
git clone https://github.com/viamus/one-brain.wiki.git $wiki
Copy-Item resources\wiki\*.md $wiki -Force
git -C $wiki add .
git -C $wiki commit -m "Refresh OneBrain wiki"
git -C $wiki push
```

If the remote wiki repository does not exist yet, create the first page from the GitHub UI or push
an initialized wiki repository if your token has permission.
