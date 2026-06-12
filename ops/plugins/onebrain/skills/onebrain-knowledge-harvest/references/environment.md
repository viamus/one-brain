# Environment And Secret Configuration

The OneBrain knowledge harvest plugin does not store credentials in the plugin, skill, source config, generated documentation, or Git history. Secrets must come from the runtime environment.

## Secret Contract

| Variable | Required When | Used For | Notes |
| --- | --- | --- | --- |
| `ONEBRAIN_API_URL` | Ingesting into OneBrain | OneBrain HTTP API base URL | Defaults to `http://127.0.0.1:8088/api/v1` when omitted. |
| `ONEBRAIN_API_KEY` | OneBrain requires auth | Bearer token for `POST /memories` | Optional only for unauthenticated local dev. |
| `GITHUB_TOKEN` | Reading private GitHub data or avoiding low anonymous limits | GitHub REST calls | `GH_TOKEN` is also accepted as a fallback. |
| `AZURE_DEVOPS_PAT` | Azure DevOps REST fallback | Azure DevOps REST calls and clone metadata | In Codex, prefer `mcp__mcp_azuredevops`; its auth is configured outside this plugin. |
| `JIRA_EMAIL` | Jira Cloud harvest | Basic auth username | Usually the Atlassian account email. |
| `JIRA_API_TOKEN` | Jira Cloud harvest | Basic auth API token | Use an Atlassian API token, not the account password. |

## Local PowerShell

Set variables in the shell that will run the harvest:

```powershell
$env:ONEBRAIN_API_URL = "http://127.0.0.1:8088/api/v1"
$env:ONEBRAIN_API_KEY = "<onebrain-key>"
$env:GITHUB_TOKEN = "<github-token>"
$env:AZURE_DEVOPS_PAT = "<azure-devops-pat>"
$env:JIRA_EMAIL = "person@example.com"
$env:JIRA_API_TOKEN = "<jira-api-token>"
```

Those values live only for the current terminal session. To persist a value for future terminals on Windows:

```powershell
[Environment]::SetEnvironmentVariable("ONEBRAIN_API_KEY", "<onebrain-key>", "User")
```

Open a new terminal after setting persistent variables.

## Source Config Overrides

Provider targets may override the variable names through `token_env` or `email_env`. The config stores only the environment variable name:

```json
{
  "targets": [
    {
      "kind": "github",
      "owner": "viamus",
      "token_env": "ONEBRAIN_GITHUB_READ_TOKEN"
    },
    {
      "kind": "jira",
      "base_url": "https://example.atlassian.net",
      "email_env": "ONEBRAIN_JIRA_EMAIL",
      "token_env": "ONEBRAIN_JIRA_TOKEN"
    }
  ]
}
```

## Codex And MCP

Codex skills inherit environment variables from the process that runs the command. For Azure DevOps inside Codex, prefer the configured `mcp__mcp_azuredevops` tools. The MCP server owns its own credential configuration, so this plugin should not duplicate that secret unless the REST fallback is required.

## CI Or Cloud Runners

Store secrets in the runner secret manager, then map them into environment variables at execution time. Example GitHub Actions shape:

```yaml
env:
  ONEBRAIN_API_URL: ${{ secrets.ONEBRAIN_API_URL }}
  ONEBRAIN_API_KEY: ${{ secrets.ONEBRAIN_API_KEY }}
  GITHUB_TOKEN: ${{ secrets.ONEBRAIN_GITHUB_TOKEN }}
```

Do not commit `.env` files. A committed example file may include variable names and placeholders only.
