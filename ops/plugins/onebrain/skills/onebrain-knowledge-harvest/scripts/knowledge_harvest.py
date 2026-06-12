#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TEXT_EXTENSIONS = {
    ".adoc",
    ".bicep",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mdx",
    ".py",
    ".ps1",
    ".rst",
    ".sh",
    ".sql",
    ".tf",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
DOC_HINTS = (
    "README",
    "ARCHITECTURE",
    "DESIGN",
    "RUNBOOK",
    "ONBOARDING",
    "CONTRIBUTING",
    "CHANGELOG",
    "docs/",
    "doc/",
)
LOCK_FILENAMES = {
    "Pipfile.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}


@dataclass
class HarvestState:
    output: Path
    clone_root: Path
    scope: dict[str, Any]
    run_id: str
    generated_at: str
    skip_clone: bool
    skip_network: bool
    documents: list[dict[str, Any]] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)

    def prepare(self) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "documents").mkdir(parents=True, exist_ok=True)
        self.clone_root.mkdir(parents=True, exist_ok=True)
        self.manifest.update(
            {
                "run_id": self.run_id,
                "generated_at": self.generated_at,
                "scope": self.scope,
                "sources": [],
                "repositories": [],
                "wikis": [],
                "work_items": [],
                "issues": [],
                "pull_requests": [],
                "active_people": {},
                "documents": self.documents,
                "errors": [],
            }
        )

    def add_error(self, provider: str, message: str, **metadata: Any) -> None:
        self.manifest["errors"].append(
            {"provider": provider, "message": message[:1000], "metadata": metadata}
        )

    def add_person(
        self, name: str | None, *, provider: str, role: str, url: str | None = None
    ) -> None:
        normalized = (name or "").strip()
        if not normalized:
            return
        people = self.manifest["active_people"]
        person = people.setdefault(
            normalized,
            {"name": normalized, "providers": sorted({provider}), "roles": {}, "urls": []},
        )
        person["providers"] = sorted(set(person.get("providers", [])) | {provider})
        roles = person.setdefault("roles", {})
        roles[role] = int(roles.get(role, 0)) + 1
        if url:
            person["urls"] = sorted(set(person.get("urls", [])) | {url})

    def write_document(
        self,
        *,
        provider: str,
        slug: str,
        title: str,
        content: str,
        metadata: dict[str, Any],
        memory_type: str = "context",
        tags: list[str] | None = None,
    ) -> Path:
        safe_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", slug.strip().lower()).strip("-")
        relative = Path(provider) / f"{safe_slug or 'document'}.md"
        path = self.output / "documents" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        body = f"# {title}\n\n{content.strip()}\n"
        path.write_text(body, encoding="utf-8")
        source_ref = f"onebrain-harvest://{provider}/{safe_slug or self.run_id}"
        doc = {
            "title": title,
            "provider": provider,
            "path": str(path.relative_to(self.output)).replace("\\", "/"),
            "source_ref": source_ref,
            "metadata": metadata,
        }
        self.documents.append(doc)
        self.memories.append(
            {
                "memory_type": memory_type,
                "title": title[:240],
                "content": body,
                "scope": {**self.scope, **metadata.get("scope", {})},
                "tags": sorted(set(["onebrain-harvest", provider, *(tags or [])])),
                "confidence": 0.82 if metadata.get("inferred") else 0.9,
                "source": {
                    "source_type": "onebrain-knowledge-harvest",
                    "source_ref": source_ref,
                },
                "entities": _entities_from_metadata(metadata),
                "metadata": {
                    "generated_by": "onebrain-knowledge-harvest",
                    "generated_at": self.generated_at,
                    "document_path": doc["path"],
                    **metadata,
                },
            }
        )
        return path

    def flush(self) -> None:
        manifest_path = self.output / "manifest.json"
        import_path = self.output / "onebrain-import.jsonl"
        self.manifest["active_people"] = dict(sorted(self.manifest["active_people"].items()))
        manifest_path.write_text(
            json.dumps(self.manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        with import_path.open("w", encoding="utf-8") as handle:
            for memory in self.memories:
                handle.write(json.dumps(memory, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Harvest enterprise source systems into a OneBrain-ready knowledge pack."
    )
    parser.add_argument("--config", required=True, help="JSON source configuration.")
    parser.add_argument("--output", required=True, help="Output directory for the knowledge pack.")
    parser.add_argument("--clone-root", help="Directory for cloned repositories.")
    parser.add_argument("--skip-clone", action="store_true", help="Do not clone Git repositories.")
    parser.add_argument("--skip-network", action="store_true", help="Only process local targets.")
    parser.add_argument("--max-items", type=int, help="Global maximum per source collection.")
    parser.add_argument("--max-files", type=int, help="Maximum local files sampled per repository.")
    parser.add_argument(
        "--ingest", action="store_true", help="Post generated memories to OneBrain."
    )
    parser.add_argument(
        "--onebrain-api-url", default=os.getenv("ONEBRAIN_API_URL", "http://127.0.0.1:8088/api/v1")
    )
    parser.add_argument("--onebrain-api-key", default=os.getenv("ONEBRAIN_API_KEY"))
    args = parser.parse_args(argv)

    config_path = Path(args.config).resolve()
    config = _load_json(config_path)
    output = Path(args.output).resolve()
    state = HarvestState(
        output=output,
        clone_root=Path(args.clone_root).resolve() if args.clone_root else output / "clones",
        scope=dict(config.get("scope") or {}),
        run_id=datetime.now(UTC).strftime("onebrain-harvest-%Y%m%d%H%M%S"),
        generated_at=datetime.now(UTC).isoformat(),
        skip_clone=args.skip_clone,
        skip_network=args.skip_network,
    )
    state.prepare()

    defaults = dict(config.get("defaults") or {})
    for target in config.get("targets", []):
        if not isinstance(target, dict):
            state.add_error("config", "target must be an object", target=target)
            continue
        merged = {**defaults, **target}
        if args.max_items:
            merged["max_items"] = args.max_items
        if args.max_files:
            merged["max_files"] = args.max_files
        _harvest_target(state, merged, config_path.parent)

    state.write_document(
        provider="meta",
        slug="harvest-summary",
        title="OneBrain Harvest Summary",
        content=_summary_document(state),
        metadata={"artifact_kind": "harvest-summary", "scope": state.scope},
        memory_type="runbook",
        tags=["summary", "knowledge-pack"],
    )
    state.flush()

    if args.ingest:
        result = ingest_memories(
            state.output / "onebrain-import.jsonl",
            api_url=args.onebrain_api_url,
            api_key=args.onebrain_api_key,
        )
        (state.output / "ingest-result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
        )

    print(json.dumps({"output": str(state.output), "memories": len(state.memories)}, indent=2))
    return 0


def _harvest_target(state: HarvestState, target: dict[str, Any], config_dir: Path) -> None:
    kind = str(target.get("kind") or "").strip().lower()
    state.manifest["sources"].append(_safe_target(target))
    if kind == "local-repository":
        harvest_local_repository(state, target, config_dir)
    elif kind == "github":
        harvest_github(state, target)
    elif kind == "azure-devops":
        harvest_azure_devops(state, target)
    elif kind == "azure-devops-mcp-export":
        harvest_azure_devops_mcp_export(state, target, config_dir)
    elif kind == "jira":
        harvest_jira(state, target)
    else:
        state.add_error("config", f"unsupported target kind: {kind}", target=_safe_target(target))


def harvest_local_repository(state: HarvestState, target: dict[str, Any], config_dir: Path) -> None:
    raw_path = Path(str(target["path"]))
    repo_path = raw_path if raw_path.is_absolute() else (config_dir / raw_path).resolve()
    if not repo_path.exists():
        state.add_error("local-repository", "path does not exist", path=str(repo_path))
        return
    name = str(target.get("name") or repo_path.name)
    metadata = _local_git_metadata(repo_path)
    docs = _sample_repository_files(repo_path, int(target.get("max_files") or 80))
    for author in metadata.get("authors", []):
        state.add_person(author.get("name"), provider="local-repository", role="commit-author")
    repo_record = {
        "provider": "local-repository",
        "name": name,
        "path": str(repo_path),
        "remote_url": metadata.get("remote_url"),
        "default_branch": metadata.get("default_branch"),
        "document_count": len(docs),
    }
    state.manifest["repositories"].append(repo_record)
    content = _repository_document(
        provider="local-repository",
        repo=repo_record,
        readme=_select_readme(docs),
        docs=docs,
        contributors=metadata.get("authors", []),
        pulls=[],
        issues=[],
        clone_result={"status": "local", "path": str(repo_path)},
    )
    state.write_document(
        provider="local-repository",
        slug=name,
        title=f"Repository Knowledge: {name}",
        content=content,
        metadata={
            "artifact_kind": "repository",
            "provider": "local-repository",
            "repository": name,
            "source_url": metadata.get("remote_url"),
            "clone_status": "local",
            "inferred": True,
            "scope": {"repository": name},
        },
        tags=["repository", "local"],
    )


def harvest_github(state: HarvestState, target: dict[str, Any]) -> None:
    if state.skip_network:
        state.add_error("github", "network skipped", target=_safe_target(target))
        return
    api_url = str(target.get("api_url") or "https://api.github.com").rstrip("/")
    token = _env_first(str(target.get("token_env") or "GITHUB_TOKEN"), "GH_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    max_items = int(target.get("max_items") or 50)
    repos = _github_repositories(api_url, headers, target, max_items, state)
    for repo in repos:
        owner = repo.get("owner", {}).get("login") or repo.get("owner") or target.get("owner")
        name = repo.get("name")
        if not owner or not name:
            continue
        contributors = _safe_github_list(
            state, api_url, headers, f"/repos/{owner}/{name}/contributors", max_items
        )
        pulls = _safe_github_list(
            state,
            api_url,
            headers,
            f"/repos/{owner}/{name}/pulls",
            max_items,
            {"state": "all", "sort": "updated", "direction": "desc"},
        )
        issues = [
            item
            for item in _safe_github_list(
                state,
                api_url,
                headers,
                f"/repos/{owner}/{name}/issues",
                max_items,
                {"state": "all", "sort": "updated", "direction": "desc"},
            )
            if "pull_request" not in item
        ]
        readme = _github_readme(api_url, headers, owner, name)
        clone_result = clone_repository(
            state=state,
            provider="github",
            name=f"{owner}-{name}",
            urls=_github_clone_urls(owner, name, repo, target, token),
            enabled=bool(target.get("clone", True)),
        )
        docs = (
            _sample_repository_files(Path(clone_result["path"]), int(target.get("max_files") or 80))
            if clone_result.get("path")
            else []
        )
        if target.get("include_wikis", True):
            wiki_result = clone_repository(
                state=state,
                provider="github-wiki",
                name=f"{owner}-{name}-wiki",
                urls=_github_wiki_urls(owner, name, target, token),
                enabled=bool(target.get("clone", True)),
            )
            state.manifest["wikis"].append(
                {"provider": "github", "repository": f"{owner}/{name}", **wiki_result}
            )
        for contributor in contributors:
            state.add_person(
                contributor.get("login"),
                provider="github",
                role="contributor",
                url=contributor.get("html_url"),
            )
        for pull in pulls:
            user = pull.get("user") or {}
            state.add_person(
                user.get("login"),
                provider="github",
                role="pull-request-author",
                url=user.get("html_url"),
            )
        for issue in issues:
            user = issue.get("user") or {}
            state.add_person(
                user.get("login"), provider="github", role="issue-author", url=user.get("html_url")
            )
        repo_record = {
            "provider": "github",
            "name": f"{owner}/{name}",
            "source_url": repo.get("html_url"),
            "clone_url": repo.get("clone_url"),
            "ssh_url": repo.get("ssh_url"),
            "default_branch": repo.get("default_branch"),
            "description": repo.get("description"),
            "language": repo.get("language"),
            "topics": repo.get("topics", []),
            "clone": clone_result,
        }
        state.manifest["repositories"].append(repo_record)
        state.manifest["pull_requests"].extend(
            _compact_pull("github", f"{owner}/{name}", pull) for pull in pulls
        )
        state.manifest["issues"].extend(
            _compact_issue("github", f"{owner}/{name}", issue) for issue in issues
        )
        state.write_document(
            provider="github",
            slug=f"{owner}-{name}",
            title=f"GitHub Repository Knowledge: {owner}/{name}",
            content=_repository_document(
                provider="github",
                repo=repo_record,
                readme=readme,
                docs=docs,
                contributors=contributors,
                pulls=pulls,
                issues=issues,
                clone_result=clone_result,
            ),
            metadata={
                "artifact_kind": "repository",
                "provider": "github",
                "repository": f"{owner}/{name}",
                "source_url": repo.get("html_url"),
                "clone_status": clone_result.get("status"),
                "inferred": True,
                "scope": {"provider": "github", "repository": f"{owner}/{name}"},
            },
            tags=["repository", "github"],
        )


def harvest_azure_devops(state: HarvestState, target: dict[str, Any]) -> None:
    if state.skip_network:
        state.add_error("azure-devops", "network skipped", target=_safe_target(target))
        return
    organization = str(target["organization"])
    token = _env_first(str(target.get("token_env") or "AZURE_DEVOPS_PAT"))
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Basic " + base64.b64encode(f":{token}".encode()).decode()
    max_items = int(target.get("max_items") or 50)
    projects = list(target.get("projects") or [])
    if not projects:
        data = _http_json(
            f"https://dev.azure.com/{organization}/_apis/projects",
            headers=headers,
            params={"api-version": "7.1", "$top": str(max_items)},
        )
        projects = [item.get("name") for item in data.get("value", []) if item.get("name")]
    for project in projects[:max_items]:
        repos_data = _http_json(
            f"https://dev.azure.com/{organization}/{urllib.parse.quote(project)}/_apis/git/repositories",
            headers=headers,
            params={"api-version": "7.1", "includeAllUrls": "true"},
        )
        for repo in repos_data.get("value", [])[:max_items]:
            repo_name = repo.get("name")
            repo_id = repo.get("id")
            pulls = _http_json(
                f"https://dev.azure.com/{organization}/{urllib.parse.quote(project)}/_apis/git/repositories/{repo_id}/pullrequests",
                headers=headers,
                params={
                    "api-version": "7.1",
                    "searchCriteria.status": "all",
                    "$top": str(max_items),
                },
            ).get("value", [])
            clone_result = clone_repository(
                state=state,
                provider="azure-devops",
                name=f"{project}-{repo_name}",
                urls=_azure_clone_urls(organization, project, repo),
                enabled=bool(target.get("clone", True)),
            )
            docs = (
                _sample_repository_files(
                    Path(clone_result["path"]), int(target.get("max_files") or 80)
                )
                if clone_result.get("path")
                else []
            )
            for pull in pulls:
                created_by = pull.get("createdBy") or {}
                state.add_person(
                    created_by.get("displayName") or created_by.get("uniqueName"),
                    provider="azure-devops",
                    role="pull-request-author",
                    url=created_by.get("_links", {}).get("avatar", {}).get("href"),
                )
            repo_record = {
                "provider": "azure-devops",
                "organization": organization,
                "project": project,
                "name": repo_name,
                "id": repo_id,
                "source_url": repo.get("webUrl") or repo.get("remoteUrl"),
                "remote_url": repo.get("remoteUrl"),
                "default_branch": repo.get("defaultBranch"),
                "clone": clone_result,
            }
            state.manifest["repositories"].append(repo_record)
            state.manifest["pull_requests"].extend(
                _compact_pull("azure-devops", f"{project}/{repo_name}", pull) for pull in pulls
            )
            state.write_document(
                provider="azure-devops",
                slug=f"{project}-{repo_name}",
                title=f"Azure DevOps Repository Knowledge: {project}/{repo_name}",
                content=_repository_document(
                    provider="azure-devops",
                    repo=repo_record,
                    readme="",
                    docs=docs,
                    contributors=[],
                    pulls=pulls,
                    issues=[],
                    clone_result=clone_result,
                ),
                metadata={
                    "artifact_kind": "repository",
                    "provider": "azure-devops",
                    "project": project,
                    "repository": repo_name,
                    "source_url": repo_record["source_url"],
                    "clone_status": clone_result.get("status"),
                    "inferred": True,
                    "scope": {
                        "provider": "azure-devops",
                        "project": project,
                        "repository": repo_name,
                    },
                },
                tags=["repository", "azure-devops"],
            )
        if target.get("include_wikis", True):
            _harvest_azure_wikis(state, organization, project, headers, max_items)
        _harvest_azure_work_items(state, organization, project, headers, target, max_items)


def harvest_azure_devops_mcp_export(
    state: HarvestState, target: dict[str, Any], config_dir: Path
) -> None:
    export_path = _resolve_config_path(str(target["path"]), config_dir)
    if not export_path.exists():
        state.add_error("azure-devops-mcp", "export path does not exist", path=str(export_path))
        return

    payload = _load_json(export_path)
    source_name = str(target.get("name") or export_path.stem)
    organization = str(payload.get("organization") or target.get("organization") or "")
    projects = _coerce_items(payload, "projects")
    repositories = _coerce_items(payload, "repositories", "repos")
    pull_requests = _coerce_items(payload, "pull_requests", "pullRequests", "pullrequests")
    work_items = _coerce_items(payload, "work_items", "workItems", "workitems")
    wikis = _coerce_items(payload, "wikis")

    for repo in repositories:
        project = _project_name(repo) or str(target.get("project") or "")
        repo_name = str(
            repo.get("name") or repo.get("repository") or repo.get("id") or "repository"
        )
        repo_record = {
            "provider": "azure-devops-mcp",
            "organization": organization or None,
            "project": project or None,
            "name": repo_name,
            "id": repo.get("id"),
            "source_url": repo.get("webUrl") or repo.get("remoteUrl") or repo.get("url"),
            "remote_url": repo.get("remoteUrl"),
            "default_branch": repo.get("defaultBranch") or repo.get("default_branch"),
            "mcp_export": str(export_path),
        }
        state.manifest["repositories"].append(repo_record)

    for pull in pull_requests:
        author = pull.get("createdBy") or pull.get("user") or pull.get("author") or {}
        if isinstance(author, dict):
            state.add_person(
                author.get("displayName") or author.get("uniqueName") or author.get("login"),
                provider="azure-devops-mcp",
                role="pull-request-author",
            )
        state.manifest["pull_requests"].append(
            _compact_pull("azure-devops-mcp", _mcp_repo_label(pull), pull)
        )

    for item in work_items:
        fields = item.get("fields") or {}
        project = str(item.get("project") or fields.get("System.TeamProject") or "")
        for field_name, role in (
            ("System.AssignedTo", "assigned-to"),
            ("System.CreatedBy", "created-by"),
            ("System.ChangedBy", "changed-by"),
        ):
            identity = fields.get(field_name) or {}
            if isinstance(identity, dict):
                state.add_person(
                    identity.get("displayName") or identity.get("uniqueName"),
                    provider="azure-devops-mcp",
                    role=role,
                )
        state.manifest["work_items"].append(
            _compact_work_item(project, item, provider="azure-devops-mcp")
        )

    for wiki in wikis:
        state.manifest["wikis"].append({"provider": "azure-devops-mcp", **wiki})
        content = str(wiki.get("content") or wiki.get("page_content") or "")
        if content or wiki.get("name") or wiki.get("id"):
            state.write_document(
                provider="azure-devops-mcp-wiki",
                slug=f"{wiki.get('project') or 'project'}-{wiki.get('name') or wiki.get('id')}",
                title=f"Azure DevOps MCP Wiki Knowledge: {wiki.get('name') or wiki.get('id')}",
                content=_wiki_document(wiki, content),
                metadata={
                    "artifact_kind": "wiki",
                    "provider": "azure-devops-mcp",
                    "project": wiki.get("project"),
                    "wiki": wiki.get("name") or wiki.get("id"),
                    "source_url": wiki.get("remoteUrl") or wiki.get("url"),
                    "inferred": not bool(content),
                    "scope": {
                        "provider": "azure-devops-mcp",
                        "project": wiki.get("project"),
                        "wiki": wiki.get("name") or wiki.get("id"),
                    },
                },
                tags=["wiki", "azure-devops", "mcp"],
            )

    state.write_document(
        provider="azure-devops-mcp",
        slug=source_name,
        title=f"Azure DevOps MCP Knowledge Export: {source_name}",
        content=_azure_mcp_export_document(
            source_name=source_name,
            organization=organization,
            projects=projects,
            repositories=repositories,
            pull_requests=pull_requests,
            work_items=work_items,
            wikis=wikis,
        ),
        metadata={
            "artifact_kind": "mcp-export",
            "provider": "azure-devops-mcp",
            "organization": organization or None,
            "source_path": str(export_path),
            "repository_count": len(repositories),
            "pull_request_count": len(pull_requests),
            "work_item_count": len(work_items),
            "wiki_count": len(wikis),
            "inferred": True,
            "scope": {"provider": "azure-devops-mcp", "organization": organization},
        },
        tags=["azure-devops", "mcp", "knowledge-export"],
    )


def harvest_jira(state: HarvestState, target: dict[str, Any]) -> None:
    if state.skip_network:
        state.add_error("jira", "network skipped", target=_safe_target(target))
        return
    base_url = str(target["base_url"]).rstrip("/")
    email = os.getenv(str(target.get("email_env") or "JIRA_EMAIL"), "")
    token = os.getenv(str(target.get("token_env") or "JIRA_API_TOKEN"), "")
    headers = {"Accept": "application/json"}
    if email and token:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()
    max_items = int(target.get("max_items") or 50)
    projects = _http_json(
        f"{base_url}/rest/api/3/project/search",
        headers=headers,
        params={"startAt": "0", "maxResults": str(min(max_items, 100))},
    ).get("values", [])
    project_keys = set(target.get("projects") or [])
    if project_keys:
        projects = [project for project in projects if project.get("key") in project_keys]
    issues = _jira_search(
        base_url, headers, str(target.get("jql") or "ORDER BY updated DESC"), max_items
    )
    for issue in issues:
        fields = issue.get("fields") or {}
        for role in ("assignee", "reporter", "creator"):
            user = fields.get(role) or {}
            state.add_person(
                user.get("displayName") or user.get("emailAddress") or user.get("accountId"),
                provider="jira",
                role=role,
            )
    state.manifest["issues"].extend(_compact_issue("jira", "jira", issue) for issue in issues)
    content = _jira_document(base_url, projects, issues)
    state.write_document(
        provider="jira",
        slug=_host_slug(base_url),
        title=f"Jira Knowledge: {_host_slug(base_url)}",
        content=content,
        metadata={
            "artifact_kind": "work-tracking",
            "provider": "jira",
            "source_url": base_url,
            "project_count": len(projects),
            "issue_count": len(issues),
            "inferred": True,
            "scope": {"provider": "jira", "host": _host_slug(base_url)},
        },
        tags=["jira", "work-tracking"],
    )


def _harvest_azure_wikis(
    state: HarvestState,
    organization: str,
    project: str,
    headers: dict[str, str],
    max_items: int,
) -> None:
    try:
        data = _http_json(
            f"https://dev.azure.com/{organization}/{urllib.parse.quote(project)}/_apis/wiki/wikis",
            headers=headers,
            params={"api-version": "7.1"},
        )
    except RuntimeError as exc:
        state.add_error("azure-devops", str(exc), project=project, artifact="wikis")
        return
    for wiki in data.get("value", [])[:max_items]:
        wiki_id = wiki.get("id") or wiki.get("name")
        page_content = ""
        try:
            page = _http_json(
                f"https://dev.azure.com/{organization}/{urllib.parse.quote(project)}/_apis/wiki/wikis/{wiki_id}/pages",
                headers={**headers, "Accept": "application/json"},
                params={
                    "api-version": "7.1",
                    "path": "/",
                    "includeContent": "true",
                    "recursionLevel": "full",
                },
            )
            page_content = str(page.get("content") or "")
        except RuntimeError as exc:
            state.add_error("azure-devops", str(exc), project=project, wiki=wiki.get("name"))
        state.manifest["wikis"].append({"provider": "azure-devops", "project": project, **wiki})
        state.write_document(
            provider="azure-devops-wiki",
            slug=f"{project}-{wiki.get('name') or wiki_id}",
            title=f"Azure DevOps Wiki Knowledge: {project}/{wiki.get('name') or wiki_id}",
            content=_wiki_document(wiki, page_content),
            metadata={
                "artifact_kind": "wiki",
                "provider": "azure-devops",
                "project": project,
                "wiki": wiki.get("name") or wiki_id,
                "source_url": wiki.get("remoteUrl") or wiki.get("url"),
                "inferred": not bool(page_content),
                "scope": {
                    "provider": "azure-devops",
                    "project": project,
                    "wiki": wiki.get("name") or wiki_id,
                },
            },
            tags=["wiki", "azure-devops"],
        )


def _harvest_azure_work_items(
    state: HarvestState,
    organization: str,
    project: str,
    headers: dict[str, str],
    target: dict[str, Any],
    max_items: int,
) -> None:
    default_wiql = (
        "Select [System.Id], [System.Title], [System.State] From WorkItems "
        "Order By [System.ChangedDate] Desc"
    )
    wiql = str(target.get("wiql") or default_wiql)
    try:
        result = _http_json(
            f"https://dev.azure.com/{organization}/{urllib.parse.quote(project)}/_apis/wit/wiql",
            headers=headers,
            method="POST",
            params={"api-version": "7.1", "$top": str(max_items)},
            payload={"query": wiql},
        )
    except RuntimeError as exc:
        state.add_error("azure-devops", str(exc), project=project, artifact="wiql")
        return
    ids = [item.get("id") for item in result.get("workItems", []) if item.get("id")][:max_items]
    work_items: list[dict[str, Any]] = []
    for chunk in _chunks(ids, 200):
        batch = _http_json(
            f"https://dev.azure.com/{organization}/{urllib.parse.quote(project)}/_apis/wit/workitemsbatch",
            headers=headers,
            method="POST",
            params={"api-version": "7.1"},
            payload={
                "ids": chunk,
                "fields": [
                    "System.Id",
                    "System.Title",
                    "System.State",
                    "System.WorkItemType",
                    "System.AssignedTo",
                    "System.CreatedBy",
                    "System.ChangedBy",
                    "System.Description",
                    "System.Tags",
                ],
            },
        )
        work_items.extend(batch.get("value", []))
    for item in work_items:
        fields = item.get("fields") or {}
        for field_name, role in (
            ("System.AssignedTo", "assigned-to"),
            ("System.CreatedBy", "created-by"),
            ("System.ChangedBy", "changed-by"),
        ):
            identity = fields.get(field_name) or {}
            if isinstance(identity, dict):
                state.add_person(
                    identity.get("displayName") or identity.get("uniqueName"),
                    provider="azure-devops",
                    role=role,
                )
        state.manifest["work_items"].append(_compact_work_item(project, item))
    state.write_document(
        provider="azure-devops-work",
        slug=f"{project}-work-items",
        title=f"Azure DevOps Work Item Knowledge: {project}",
        content=_work_items_document(project, work_items),
        metadata={
            "artifact_kind": "work-items",
            "provider": "azure-devops",
            "project": project,
            "work_item_count": len(work_items),
            "inferred": True,
            "scope": {"provider": "azure-devops", "project": project},
        },
        tags=["work-items", "azure-devops"],
    )


def clone_repository(
    *,
    state: HarvestState,
    provider: str,
    name: str,
    urls: list[str],
    enabled: bool,
) -> dict[str, Any]:
    if state.skip_clone or not enabled:
        return {"status": "skipped"}
    git_bin = shutil.which("git")
    if git_bin is None:
        return {"status": "failed", "error": "git executable not found"}
    destination = state.clone_root / re.sub(r"[^a-zA-Z0-9_.-]+", "-", name).strip("-")
    if destination.exists():
        return {"status": "existing", "path": str(destination), "url": ""}
    errors: list[str] = []
    for url in urls:
        if not url:
            continue
        try:
            completed = subprocess.run(  # noqa: S603
                [git_bin, "clone", "--depth", "1", url, str(destination)],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{_sanitize_url(url)}: {exc}")
            continue
        if completed.returncode == 0:
            return {"status": "cloned", "path": str(destination), "url": _sanitize_url(url)}
        errors.append(
            f"{_sanitize_url(url)}: {(completed.stderr or completed.stdout).strip()[:600]}"
        )
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
    return {"status": "failed", "errors": errors}


def ingest_memories(path: Path, *, api_url: str, api_key: str | None) -> dict[str, Any]:
    endpoint = api_url.rstrip("/") + "/memories"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    result = {"endpoint": endpoint, "created": 0, "failed": []}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            _http_json(endpoint, headers=headers, method="POST", payload=json.loads(line))
            result["created"] += 1
        except RuntimeError as exc:
            result["failed"].append({"line": line_number, "error": str(exc)[:1000]})
    return result


def _github_repositories(
    api_url: str,
    headers: dict[str, str],
    target: dict[str, Any],
    max_items: int,
    state: HarvestState,
) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    for repo_url in target.get("repo_urls") or []:
        parsed = _parse_github_repo(repo_url)
        if not parsed:
            state.add_error("github", "could not parse repo URL", url=repo_url)
            continue
        owner, repo = parsed
        try:
            repos.append(_http_json(f"{api_url}/repos/{owner}/{repo}", headers=headers))
        except RuntimeError:
            repos.append(
                {
                    "name": repo,
                    "owner": {"login": owner},
                    "html_url": f"https://github.com/{owner}/{repo}",
                    "clone_url": f"https://github.com/{owner}/{repo}.git",
                    "ssh_url": f"git@github.com:{owner}/{repo}.git",
                }
            )
    owner = target.get("owner")
    named_repos = target.get("repos") or []
    if owner and named_repos:
        for repo in named_repos[:max_items]:
            try:
                repos.append(_http_json(f"{api_url}/repos/{owner}/{repo}", headers=headers))
            except RuntimeError as exc:
                state.add_error("github", str(exc), owner=owner, repo=repo)
    elif owner:
        repos.extend(
            _github_list(api_url, headers, f"/orgs/{owner}/repos", max_items, {"type": "all"})
        )
    return repos[:max_items]


def _github_list(
    api_url: str,
    headers: dict[str, str],
    path: str,
    max_items: int,
    extra_params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while len(items) < max_items:
        params = {"per_page": "100", "page": str(page), **(extra_params or {})}
        data = _http_json(api_url.rstrip("/") + path, headers=headers, params=params)
        if not isinstance(data, list) or not data:
            break
        items.extend(data)
        if len(data) < 100:
            break
        page += 1
    return items[:max_items]


def _safe_github_list(
    state: HarvestState,
    api_url: str,
    headers: dict[str, str],
    path: str,
    max_items: int,
    extra_params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    try:
        return _github_list(api_url, headers, path, max_items, extra_params)
    except RuntimeError as exc:
        state.add_error("github", str(exc), path=path)
        return []


def _github_readme(api_url: str, headers: dict[str, str], owner: str, repo: str) -> str:
    try:
        data = _http_json(f"{api_url}/repos/{owner}/{repo}/readme", headers=headers)
    except RuntimeError:
        return ""
    content = data.get("content")
    if data.get("encoding") == "base64" and isinstance(content, str):
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except ValueError:
            return ""
    return ""


def _jira_search(
    base_url: str, headers: dict[str, str], jql: str, max_items: int
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    token: str | None = None
    while len(issues) < max_items:
        payload: dict[str, Any] = {
            "jql": jql,
            "maxResults": min(100, max_items - len(issues)),
            "fields": [
                "summary",
                "description",
                "issuetype",
                "status",
                "assignee",
                "reporter",
                "creator",
                "labels",
                "components",
                "updated",
                "created",
                "project",
                "parent",
            ],
        }
        if token:
            payload["nextPageToken"] = token
        try:
            data = _http_json(
                f"{base_url}/rest/api/3/search/jql",
                headers=headers,
                method="POST",
                payload=payload,
            )
        except RuntimeError:
            data = _http_json(
                f"{base_url}/rest/api/3/search",
                headers=headers,
                method="POST",
                payload=payload,
            )
        issues.extend(data.get("issues", []))
        token = data.get("nextPageToken")
        if not token or data.get("isLast") is True:
            break
    return issues[:max_items]


def _http_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    params: dict[str, str] | None = None,
    payload: Any | None = None,
    timeout: int = 45,
) -> Any:
    full_url = url
    if params:
        full_url += ("&" if "?" in full_url else "?") + urllib.parse.urlencode(params)
    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    parsed_url = urllib.parse.urlparse(full_url)
    if parsed_url.scheme not in {"http", "https"}:
        raise RuntimeError(f"Refusing unsupported URL scheme for {_sanitize_url(full_url)}")
    request = urllib.request.Request(  # noqa: S310
        full_url, data=data, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read()
            if not raw:
                return {}
            text = raw.decode("utf-8", errors="replace")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"content": text}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(
            f"{method} {_sanitize_url(full_url)} failed with HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {_sanitize_url(full_url)} failed: {exc}") from exc


def _sample_repository_files(repo_path: Path, max_files: int) -> list[dict[str, str]]:
    if not repo_path.exists():
        return []
    candidates: list[Path] = []
    for path in repo_path.rglob("*"):
        if len(candidates) >= max_files:
            break
        if not path.is_file() or path.name in LOCK_FILENAMES:
            continue
        if any(part in {".git", "node_modules", ".venv", "dist", "build"} for part in path.parts):
            continue
        relative = path.relative_to(repo_path).as_posix()
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        score = 0 if any(hint.lower() in relative.lower() for hint in DOC_HINTS) else 1
        candidates.append((score, path))  # type: ignore[arg-type]
    result: list[dict[str, str]] = []
    for _, path in sorted(candidates, key=lambda item: (item[0], item[1].as_posix()))[:max_files]:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")[:24000]
        except OSError:
            continue
        result.append({"path": path.relative_to(repo_path).as_posix(), "content": content})
    return result


def _select_readme(docs: list[dict[str, str]]) -> str:
    for doc in docs:
        if Path(doc["path"]).name.lower().startswith("readme"):
            return doc["content"]
    return ""


def _local_git_metadata(repo_path: Path) -> dict[str, Any]:
    remote_url = _git(repo_path, "remote", "get-url", "origin")
    branch = _git(repo_path, "branch", "--show-current")
    log = _git(repo_path, "log", "--format=%an <%ae>|%ad|%s", "--date=short", "-n", "100")
    authors: dict[str, dict[str, Any]] = {}
    for line in log.splitlines():
        name = line.split("|", 1)[0].strip()
        if not name:
            continue
        author = authors.setdefault(name, {"name": name, "commits": 0})
        author["commits"] += 1
    return {
        "remote_url": _sanitize_url(remote_url.strip()) if remote_url else None,
        "default_branch": branch.strip() or None,
        "authors": sorted(authors.values(), key=lambda item: item["commits"], reverse=True),
    }


def _git(repo_path: Path, *args: str) -> str:
    git_bin = shutil.which("git")
    if git_bin is None:
        return ""
    try:
        completed = subprocess.run(  # noqa: S603
            [git_bin, *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError:
        return ""
    return completed.stdout if completed.returncode == 0 else ""


def _repository_document(
    *,
    provider: str,
    repo: dict[str, Any],
    readme: str,
    docs: list[dict[str, str]],
    contributors: list[dict[str, Any]],
    pulls: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    clone_result: dict[str, Any],
) -> str:
    repo_name = repo.get("name") or repo.get("repository") or "repository"
    lines = [
        f"Provider: `{provider}`",
        f"Repository: `{repo_name}`",
        f"Source URL: {_md_value(repo.get('source_url') or repo.get('remote_url'))}",
        f"Default branch: {_md_value(repo.get('default_branch'))}",
        f"Clone status: `{clone_result.get('status', 'unknown')}`",
        "",
        "## Meaning",
        _repo_meaning(repo, readme, docs),
        "",
        "## Communication And Business Flow Signals",
        _flow_signals(docs, pulls, issues),
        "",
        "## Active People",
        _people_table(contributors),
        "",
        "## Pull Requests",
        _pull_table(pulls),
        "",
        "## Issues Or Work Items",
        _issue_table(issues),
        "",
        "## Documentation Evidence",
    ]
    for doc in docs[:20]:
        lines.append(f"- `{doc['path']}`: {_first_sentence(doc['content'])}")
    if readme:
        lines.extend(["", "## README Extract", _truncate(readme, 5000)])
    return "\n".join(lines)


def _jira_document(
    base_url: str, projects: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> str:
    lines = [f"Jira host: {base_url}", "", "## Projects"]
    for project in projects:
        project_type = project.get("projectTypeKey", "unknown")
        lines.append(f"- `{project.get('key')}` {project.get('name')} ({project_type})")
    lines.extend(
        [
            "",
            "## Issues",
            "| Key | Type | Status | Summary | Assignee |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for issue in issues[:100]:
        fields = issue.get("fields") or {}
        status = fields.get("status") or {}
        issue_type = fields.get("issuetype") or {}
        assignee = fields.get("assignee") or {}
        summary = _escape_table(str(fields.get("summary") or ""))
        assignee_name = _escape_table(str(assignee.get("displayName") or ""))
        lines.append(
            f"| {issue.get('key')} | {issue_type.get('name', '')} | {status.get('name', '')} | "
            f"{summary} | {assignee_name} |"
        )
    lines.extend(["", "## Business Flow Signals", _jira_flow_signals(issues)])
    return "\n".join(lines)


def _wiki_document(wiki: dict[str, Any], page_content: str) -> str:
    lines = [
        f"Wiki: `{wiki.get('name') or wiki.get('id')}`",
        f"Type: `{wiki.get('type', 'unknown')}`",
        f"Remote URL: {_md_value(wiki.get('remoteUrl') or wiki.get('url'))}",
        "",
        "## Content",
        _truncate(page_content, 12000)
        if page_content
        else "No root page content was available; metadata was preserved for follow-up harvesting.",
    ]
    return "\n".join(lines)


def _work_items_document(project: str, work_items: list[dict[str, Any]]) -> str:
    lines = [
        f"Project: `{project}`",
        "",
        "## Work Items",
        "| ID | Type | State | Title | Assigned To |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in work_items[:200]:
        fields = item.get("fields") or {}
        assigned = fields.get("System.AssignedTo") or {}
        assigned_name = assigned.get("displayName") if isinstance(assigned, dict) else assigned
        title = _escape_table(str(fields.get("System.Title") or ""))
        assigned_text = _escape_table(str(assigned_name or ""))
        item_type = fields.get("System.WorkItemType", "")
        item_state = fields.get("System.State", "")
        lines.append(
            f"| {item.get('id')} | {item_type} | {item_state} | {title} | {assigned_text} |"
        )
    lines.extend(["", "## Business Flow Signals", _ado_flow_signals(work_items)])
    return "\n".join(lines)


def _azure_mcp_export_document(
    *,
    source_name: str,
    organization: str,
    projects: list[dict[str, Any]],
    repositories: list[dict[str, Any]],
    pull_requests: list[dict[str, Any]],
    work_items: list[dict[str, Any]],
    wikis: list[dict[str, Any]],
) -> str:
    lines = [
        f"Source export: `{source_name}`",
        f"Organization: {_md_value(organization)}",
        "",
        "## Counts",
        f"- Projects: {len(projects)}",
        f"- Repositories: {len(repositories)}",
        f"- Pull requests: {len(pull_requests)}",
        f"- Work items: {len(work_items)}",
        f"- Wikis: {len(wikis)}",
        "",
        "## Projects",
    ]
    if projects:
        for project in projects[:100]:
            lines.append(f"- `{project.get('name') or project.get('id')}`")
    else:
        lines.append("- No project metadata was exported.")

    lines.extend(["", "## Repositories"])
    if repositories:
        for repo in repositories[:100]:
            project = _project_name(repo)
            repo_name = repo.get("name") or repo.get("repository") or repo.get("id")
            lines.append(f"- `{project or '-'}/{repo_name}`: {_md_value(repo.get('webUrl'))}")
    else:
        lines.append("- No repository metadata was exported.")

    lines.extend(["", "## Pull Requests", _pull_table(pull_requests)])
    lines.extend(["", "## Work Items", _work_items_document("mcp-export", work_items)])
    lines.extend(["", "## Wikis"])
    if wikis:
        for wiki in wikis[:100]:
            lines.append(f"- `{wiki.get('project') or '-'}/{wiki.get('name') or wiki.get('id')}`")
    else:
        lines.append("- No wiki metadata was exported.")
    return "\n".join(lines)


def _summary_document(state: HarvestState) -> str:
    manifest = state.manifest
    return "\n".join(
        [
            f"Run ID: `{state.run_id}`",
            f"Generated at: `{state.generated_at}`",
            "",
            "## Counts",
            f"- Sources: {len(manifest.get('sources', []))}",
            f"- Repositories: {len(manifest.get('repositories', []))}",
            f"- Wikis: {len(manifest.get('wikis', []))}",
            f"- Pull requests: {len(manifest.get('pull_requests', []))}",
            f"- Issues: {len(manifest.get('issues', []))}",
            f"- Work items: {len(manifest.get('work_items', []))}",
            f"- Active people: {len(manifest.get('active_people', {}))}",
            f"- Errors: {len(manifest.get('errors', []))}",
            "",
            "## Pack Files",
            "- `manifest.json`",
            "- `documents/`",
            "- `onebrain-import.jsonl`",
        ]
    )


def _repo_meaning(repo: dict[str, Any], readme: str, docs: list[dict[str, str]]) -> str:
    description = repo.get("description")
    if description:
        return f"Observed repository description: {description}"
    if readme:
        return f"Inferred from README: {_first_sentence(readme)}"
    if docs:
        return f"Inferred from documentation/source paths: {_first_sentence(docs[0]['content'])}"
    return "No explicit purpose was found; treat this repository as requiring human review."


def _flow_signals(
    docs: list[dict[str, str]], pulls: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> str:
    terms: dict[str, int] = {}
    for doc in docs[:50]:
        for token in re.findall(
            r"\b[A-Z][A-Za-z0-9]{3,}\b|\b[a-z][a-z0-9-]{4,}\b",
            doc["path"] + "\n" + doc["content"][:4000],
        ):
            normalized = token.lower()
            if normalized in {"readme", "src", "test", "tests", "package", "index", "config"}:
                continue
            terms[normalized] = terms.get(normalized, 0) + 1
    top = sorted(terms.items(), key=lambda item: item[1], reverse=True)[:20]
    lines = ["Top repeated source/document terms:"]
    lines.extend(f"- `{term}` ({count})" for term, count in top)
    if pulls:
        lines.append(
            f"- Pull request activity suggests active delivery flow ({len(pulls)} sampled PRs)."
        )
    if issues:
        lines.append(
            f"- Issue activity suggests product/support flow ({len(issues)} sampled issues)."
        )
    return "\n".join(lines)


def _jira_flow_signals(issues: list[dict[str, Any]]) -> str:
    statuses: dict[str, int] = {}
    types: dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        status = (fields.get("status") or {}).get("name")
        issue_type = (fields.get("issuetype") or {}).get("name")
        if status:
            statuses[status] = statuses.get(status, 0) + 1
        if issue_type:
            types[issue_type] = types.get(issue_type, 0) + 1
    return "\n".join(
        [
            "Status mix: " + ", ".join(f"{key}={value}" for key, value in sorted(statuses.items())),
            "Type mix: " + ", ".join(f"{key}={value}" for key, value in sorted(types.items())),
        ]
    )


def _ado_flow_signals(work_items: list[dict[str, Any]]) -> str:
    states: dict[str, int] = {}
    types: dict[str, int] = {}
    for item in work_items:
        fields = item.get("fields") or {}
        state = fields.get("System.State")
        item_type = fields.get("System.WorkItemType")
        if state:
            states[state] = states.get(state, 0) + 1
        if item_type:
            types[item_type] = types.get(item_type, 0) + 1
    return "\n".join(
        [
            "State mix: " + ", ".join(f"{key}={value}" for key, value in sorted(states.items())),
            "Type mix: " + ", ".join(f"{key}={value}" for key, value in sorted(types.items())),
        ]
    )


def _people_table(people: list[dict[str, Any]]) -> str:
    if not people:
        return "No people data was available."
    rows = ["| Person | Activity | URL |", "| --- | ---: | --- |"]
    for person in people[:25]:
        name = person.get("login") or person.get("name") or person.get("displayName") or "unknown"
        activity = person.get("contributions") or person.get("commits") or ""
        url = _md_value(person.get("html_url") or person.get("url"))
        rows.append(f"| {_escape_table(str(name))} | {activity} | {url} |")
    return "\n".join(rows)


def _pull_table(pulls: list[dict[str, Any]]) -> str:
    if not pulls:
        return "No pull request data was available."
    rows = ["| ID | State | Title | Author | URL |", "| --- | --- | --- | --- | --- |"]
    for pull in pulls[:50]:
        author = pull.get("user") or pull.get("createdBy") or {}
        pull_id = pull.get("number") or pull.get("pullRequestId") or ""
        pull_state = pull.get("state") or pull.get("status") or ""
        title = _escape_table(str(pull.get("title") or ""))
        author_name = author.get("login") or author.get("displayName") or ""
        author_text = _escape_table(str(author_name))
        url = _md_value(pull.get("html_url") or pull.get("url"))
        rows.append(f"| {pull_id} | {pull_state} | {title} | {author_text} | {url} |")
    return "\n".join(rows)


def _issue_table(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "No issue data was available."
    rows = ["| ID | State | Title | Author | URL |", "| --- | --- | --- | --- | --- |"]
    for issue in issues[:50]:
        fields = issue.get("fields") or {}
        author = issue.get("user") or fields.get("reporter") or {}
        title = issue.get("title") or fields.get("summary") or ""
        state = issue.get("state") or (fields.get("status") or {}).get("name") or ""
        issue_id = issue.get("number") or issue.get("key") or issue.get("id") or ""
        author_name = author.get("login") or author.get("displayName") or ""
        author_text = _escape_table(str(author_name))
        url = _md_value(issue.get("html_url") or issue.get("self"))
        rows.append(
            f"| {issue_id} | {state} | {_escape_table(str(title))} | {author_text} | {url} |"
        )
    return "\n".join(rows)


def _compact_pull(provider: str, repo: str, pull: dict[str, Any]) -> dict[str, Any]:
    author = pull.get("user") or pull.get("createdBy") or {}
    return {
        "provider": provider,
        "repository": repo,
        "id": pull.get("number") or pull.get("pullRequestId"),
        "title": pull.get("title"),
        "state": pull.get("state") or pull.get("status"),
        "author": author.get("login") or author.get("displayName"),
        "url": pull.get("html_url") or pull.get("url"),
    }


def _compact_issue(provider: str, repo: str, issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    author = issue.get("user") or fields.get("reporter") or {}
    return {
        "provider": provider,
        "repository": repo,
        "id": issue.get("number") or issue.get("key") or issue.get("id"),
        "title": issue.get("title") or fields.get("summary"),
        "state": issue.get("state") or (fields.get("status") or {}).get("name"),
        "author": author.get("login") or author.get("displayName"),
        "url": issue.get("html_url") or issue.get("self"),
    }


def _compact_work_item(
    project: str, item: dict[str, Any], *, provider: str = "azure-devops"
) -> dict[str, Any]:
    fields = item.get("fields") or {}
    return {
        "provider": provider,
        "project": project,
        "id": item.get("id"),
        "title": fields.get("System.Title"),
        "state": fields.get("System.State"),
        "type": fields.get("System.WorkItemType"),
        "url": item.get("url"),
    }


def _coerce_items(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = value.get("value") or value.get("items") or value.get("results")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    value = payload.get("value")
    if len(keys) == 1 and isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _project_name(value: dict[str, Any]) -> str | None:
    project = value.get("project")
    if isinstance(project, dict):
        return project.get("name") or project.get("id")
    if isinstance(project, str):
        return project
    return value.get("projectName") or value.get("project_name")


def _mcp_repo_label(value: dict[str, Any]) -> str:
    repository = value.get("repository")
    if isinstance(repository, dict):
        repo_name = repository.get("name") or repository.get("id")
    else:
        repo_name = repository or value.get("repositoryName") or value.get("repo")
    project = _project_name(value)
    if project and repo_name:
        return f"{project}/{repo_name}"
    return str(repo_name or project or "azure-devops-mcp")


def _github_clone_urls(
    owner: str, repo: str, meta: dict[str, Any], target: dict[str, Any], token: str | None
) -> list[str]:
    urls = [
        meta.get("clone_url"),
        meta.get("ssh_url"),
        f"https://github.com/{owner}/{repo}.git",
        f"git@github.com:{owner}/{repo}.git",
    ]
    if token and target.get("allow_token_in_clone_url"):
        urls.insert(
            0, f"https://x-access-token:{urllib.parse.quote(token)}@github.com/{owner}/{repo}.git"
        )
    return [url for url in urls if isinstance(url, str) and url]


def _github_wiki_urls(
    owner: str, repo: str, target: dict[str, Any], token: str | None
) -> list[str]:
    urls = [
        f"https://github.com/{owner}/{repo}.wiki.git",
        f"git@github.com:{owner}/{repo}.wiki.git",
    ]
    if token and target.get("allow_token_in_clone_url"):
        urls.insert(
            0,
            f"https://x-access-token:{urllib.parse.quote(token)}@github.com/{owner}/{repo}.wiki.git",
        )
    return urls


def _azure_clone_urls(organization: str, project: str, repo: dict[str, Any]) -> list[str]:
    repo_name = repo.get("name")
    return [
        repo.get("remoteUrl"),
        repo.get("sshUrl"),
        f"git@ssh.dev.azure.com:v3/{organization}/{project}/{repo_name}" if repo_name else "",
    ]


def _parse_github_repo(url: str) -> tuple[str, str] | None:
    match = re.search(r"github\.com[:/](?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$", url)
    if not match:
        return None
    return match.group("owner"), match.group("repo")


def _entities_from_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    entities = []
    for key, entity_type in (
        ("repository", "repository"),
        ("project", "project"),
        ("wiki", "wiki"),
    ):
        if value := metadata.get(key):
            entities.append({"name": str(value), "entity_type": entity_type, "role": "source"})
    if provider := metadata.get("provider"):
        entities.append({"name": str(provider), "entity_type": "platform", "role": "source"})
    return entities


def _safe_target(target: dict[str, Any]) -> dict[str, Any]:
    safe = dict(target)
    for key in list(safe):
        if "token" in key.lower() or "password" in key.lower() or "secret" in key.lower():
            safe[key] = "***"
    return safe


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise SystemExit(f"config must be a JSON object: {path}")
    return payload


def _resolve_config_path(path: str, config_dir: Path) -> Path:
    raw_path = Path(path)
    return raw_path if raw_path.is_absolute() else (config_dir / raw_path).resolve()


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _chunks(values: list[int], size: int) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _sanitize_url(url: str) -> str:
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", url)


def _host_slug(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9.-]+", "-", urllib.parse.urlparse(url).netloc or url).strip("-")


def _md_value(value: Any) -> str:
    return str(value) if value not in (None, "") else "-"


def _first_sentence(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip())
    if not collapsed:
        return "-"
    parts = re.split(r"(?<=[.!?])\s+", collapsed)
    return _truncate(parts[0], 280)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n\n[truncated]"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
