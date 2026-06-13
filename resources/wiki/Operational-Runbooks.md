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
