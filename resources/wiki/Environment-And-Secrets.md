# Environment And Secrets

OneBrain and the knowledge harvest plugin use environment variables for runtime configuration and
secrets. Source configs and documentation must store variable names, not secret values.

## OneBrain Runtime

| Variable | Purpose |
| --- | --- |
| `ONEBRAIN_ENVIRONMENT` | Runtime mode, such as `local` or `production`. |
| `ONEBRAIN_API_KEYS` | Comma-separated accepted API keys for HTTP surfaces. |
| `ONEBRAIN_DATABASE_URL` | Async SQLAlchemy PostgreSQL URL. |
| `ONEBRAIN_EMBEDDING_PROVIDER` | `hash`, `openai`, or `fastembed`. |
| `ONEBRAIN_EMBEDDING_MODEL` | Embedding model name. |
| `ONEBRAIN_VECTOR_SIZE` | Embedding dimensions expected by pgvector. |
| `ONEBRAIN_OPENAI_API_KEY` | OpenAI key when provider is `openai`. |
| `ONEBRAIN_MCP_REQUIRE_API_KEY` | Whether MCP HTTP requires auth. |
| `ONEBRAIN_MCP_CLIENT_KEY` | Client-side variable used by Codex MCP config. |

## Knowledge Harvest

| Variable | Purpose |
| --- | --- |
| `ONEBRAIN_API_URL` | Base URL for OneBrain API ingest, default `http://127.0.0.1:8088/api/v1`. |
| `ONEBRAIN_API_KEY` | Bearer token for `POST /memories`. |
| `GITHUB_TOKEN` or `GH_TOKEN` | GitHub REST and clone access. |
| `AZURE_DEVOPS_PAT` | Azure DevOps REST fallback or clone access. |
| `JIRA_EMAIL` | Jira Cloud account email. |
| `JIRA_API_TOKEN` | Jira Cloud API token. |

## Codex MCP Configuration

HTTP MCP example:

```toml
[mcp_servers.onebrain]
type = "http"
url = "http://localhost:8090/mcp"
bearer_token_env_var = "ONEBRAIN_MCP_CLIENT_KEY"
```

Stdio MCP example:

```toml
[mcp_servers.onebrain]
command = "uv"
args = ["run", "onebrain-mcp"]
cwd = "C:\\Repositories\\one-brain"
startup_timeout_sec = 20
tool_timeout_sec = 60
```

## Rules

- Keep `.env` out of Git.
- Keep provider tokens in runner/user/CI secret stores.
- Use placeholders in docs.
- Prefer separate keys for humans, automation, and agents.
- Never store raw secrets as OneBrain memories.
- Redact secret-looking values before publishing generated harvest packs.
