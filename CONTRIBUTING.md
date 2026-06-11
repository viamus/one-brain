# Contributing to OneBrain

Thanks for improving OneBrain. This project is intended to be a production-oriented memory service, so changes should keep reliability, auditability, and operational clarity in view.

## Development Setup

```powershell
Copy-Item .env.example .env
docker compose up -d postgres qdrant
uv sync --dev
uv run alembic upgrade head
```

Run the Django web/API locally:

```powershell
uv run onebrain-django
```

Run the full Docker stack:

```powershell
docker compose up -d --build
```

## Quality Checks

Before opening a pull request:

```powershell
uv run ruff format .
uv run ruff check .
uv run pytest -q
```

## Change Guidelines

- Keep OneBrain's online path deterministic. Do not add LLM calls to context composition or retrieval.
- Keep PostgreSQL as the canonical source of truth.
- Keep Qdrant as an index, not the only source of memory data.
- Keep MCP servers thin and deterministic.
- Add migrations for schema changes.
- Keep authentication and secret handling explicit.
- Do not commit `.env`, credentials, generated caches, or local database files.
- Update `README.md` when setup, configuration, Docker behavior, or APIs change.

## Migrations

Create a migration:

```powershell
uv run alembic revision --autogenerate -m "describe change"
```

Review the generated file. Alembic autogeneration is a helper, not a contract.

Apply migrations:

```powershell
uv run alembic upgrade head
```

## Commit Style

Prefer small, descriptive commits. Examples:

```text
Add API key auth documentation
Add deterministic relation schema
Fix Qdrant collection healthcheck
```

## Security

Report security issues privately. Do not open a public issue with secrets, exploit details, or live infrastructure identifiers.
