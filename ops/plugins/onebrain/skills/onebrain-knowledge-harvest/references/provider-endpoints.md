# Provider Endpoints

Use these primary sources when changing provider behavior:

- Viamus Azure DevOps MCP, preferred inside Codex when available: https://github.com/viamus/mcp-azure-devops
- GitHub REST repositories, contents, contributors, and repository metadata: https://docs.github.com/rest/repos
- GitHub REST issues: https://docs.github.com/en/rest/issues
- GitHub REST pull requests: https://docs.github.com/en/rest/pulls/pulls
- GitHub wikis are Git repositories and can be edited locally through Git workflows: https://docs.github.com/en/communities/documenting-your-project-with-wikis/adding-or-editing-wiki-pages
- Azure DevOps REST API request pattern: https://learn.microsoft.com/en-us/rest/api/azure/devops/?view=azure-devops-rest-7.2
- Azure DevOps projects list: https://learn.microsoft.com/en-us/rest/api/azure/devops/core/projects/list?view=azure-devops-rest-7.1
- Azure DevOps Git repositories list: https://learn.microsoft.com/en-us/rest/api/azure/devops/git/repositories/list?view=azure-devops-rest-7.1
- Azure DevOps pull requests list: https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-requests/get-pull-requests?view=azure-devops-rest-7.1
- Azure DevOps wikis list: https://learn.microsoft.com/en-us/rest/api/azure/devops/wiki/wikis/list?view=azure-devops-rest-7.1
- Azure DevOps wiki page get: https://learn.microsoft.com/en-us/rest/api/azure/devops/wiki/pages/get-page?view=azure-devops-rest-7.1
- Azure DevOps WIQL query: https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/wiql/query-by-wiql?view=azure-devops-rest-7.1
- Azure DevOps work items batch: https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/work-items/get-work-items-batch?view=azure-devops-rest-7.1
- Jira Cloud REST API v3 issue search: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/
- Jira Cloud REST API v3 projects: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-projects/
- Jira Cloud REST API v3 user search: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-user-search/

Provider notes:

- Prefer `mcp__mcp_azuredevops` tools for Azure DevOps in Codex. Use direct REST only as fallback or for cloud/Gemini runners without MCP.
- GitHub contributors endpoint can return cached contributor data. Treat it as activity signal, not exact audit.
- Azure DevOps Work Items Batch is limited to 200 IDs per call.
- Jira Cloud JQL search uses token pagination on newer endpoints. Preserve `nextPageToken` when available.
