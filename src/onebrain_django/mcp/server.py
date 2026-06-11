from __future__ import annotations

import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from onebrain_core.application.memory_hardening import harden_memory_payload
from onebrain_core.application.memory_importer import add_hardened_memory, import_memory_files
from onebrain_core.application.service import OneBrainService
from onebrain_core.application.skills import add_hardened_skill, harden_skill_payload
from onebrain_core.common.path_mapping import resolve_mapped_path
from onebrain_core.contracts.schemas import (
    ContextRequest,
    CorrelationRequest,
    GraphRequest,
    MemoryCreate,
    SearchFilters,
    SearchRequest,
)
from onebrain_django.runtime import close_runtime, get_runtime_service, get_runtime_settings

mcp = FastMCP(
    "OneBrain",
    instructions=(
        "OneBrain stores durable memories through the MCP HTTP service and returns "
        "deterministic context packs. Use capture only for stable, non-secret "
        "information. Use context before tasks that need prior rules, project context, "
        "decisions, workflows, skills, or pitfalls."
    ),
)


class OneBrainServiceClient:
    def __init__(self, service: OneBrainService) -> None:
        self._service = service

    async def capture_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        memory = await self._service.capture_memory(
            MemoryCreate.model_validate(payload), actor="mcp"
        )
        return memory.model_dump(mode="json")

    async def get_memory_by_source_ref(self, source_ref: str) -> dict[str, Any] | None:
        try:
            memory = await self._service.get_memory_by_source_ref(source_ref)
        except KeyError:
            return None
        return memory.model_dump(mode="json")


def get_service() -> OneBrainService:
    return get_runtime_service()


def get_service_client() -> OneBrainServiceClient:
    return OneBrainServiceClient(get_service())


async def dispose_service() -> None:
    await close_runtime()


@mcp.tool()
async def onebrain_capture_memory(memory: dict[str, Any]) -> dict[str, Any]:
    """Store a durable memory through the OneBrain core service."""

    payload = MemoryCreate.model_validate(memory)
    created = await get_service().capture_memory(payload, actor="mcp")
    return created.model_dump(mode="json")


@mcp.tool()
async def onebrain_harden_memory(
    memory: dict[str, Any],
    default_scope: dict[str, Any] | None = None,
    source_type: str = "manual",
    source_ref: str | None = None,
    redact_secrets: bool = True,
) -> dict[str, Any]:
    """Validate, normalize, and redact a memory payload without storing it."""

    result = harden_memory_payload(
        memory,
        default_scope=default_scope,
        source_type=source_type,
        source_ref=source_ref,
        redact_secrets=redact_secrets,
    )
    return {
        "payload": result.payload,
        "findings": result.findings,
        "redactions": result.redactions,
    }


@mcp.tool()
async def onebrain_add_memory(
    memory: dict[str, Any],
    default_scope: dict[str, Any] | None = None,
    source_type: str = "manual",
    source_ref: str | None = None,
    redact_secrets: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Harden and store one durable memory, skipping an existing source_ref."""

    return await add_hardened_memory(
        get_service_client(),
        memory,
        default_scope=default_scope,
        source_type=source_type,
        source_ref=source_ref,
        redact_secrets=redact_secrets,
        dry_run=dry_run,
    )


@mcp.tool()
async def onebrain_harden_skill(
    skill: dict[str, Any],
    default_scope: dict[str, Any] | None = None,
    source_type: str = "skill",
    source_ref: str | None = None,
    redact_secrets: bool = True,
) -> dict[str, Any]:
    """Validate, normalize, and redact a skill payload without storing it."""

    result = harden_skill_payload(
        skill,
        default_scope=default_scope,
        source_type=source_type,
        source_ref=source_ref,
        redact_secrets=redact_secrets,
    )
    return {
        "payload": result.payload,
        "findings": result.findings,
        "redactions": result.redactions,
    }


@mcp.tool()
async def onebrain_add_skill(
    skill: dict[str, Any],
    default_scope: dict[str, Any] | None = None,
    source_type: str = "skill",
    source_ref: str | None = None,
    redact_secrets: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Harden and store one declarative skill, skipping an existing source_ref."""

    return await add_hardened_skill(
        get_service_client(),
        skill,
        default_scope=default_scope,
        source_type=source_type,
        source_ref=source_ref,
        redact_secrets=redact_secrets,
        dry_run=dry_run,
    )


@mcp.tool()
async def onebrain_import_memory_files(
    path: str,
    scope: dict[str, Any] | None = None,
    source_type: str = "file-import",
    source_ref_prefix: str | None = None,
    include_extensions: list[str] | None = None,
    exclude_dirs: list[str] | None = None,
    include_examples: bool = True,
    redact_secrets: bool = True,
    dry_run: bool = False,
    max_files: int | None = None,
    max_content_chars: int = 24000,
) -> dict[str, Any]:
    """Import text memories from a file or folder with hardening and source_ref dedupe."""

    settings = get_runtime_settings()
    resolved_path = resolve_mapped_path(path, settings.mcp_path_mappings)
    result = await import_memory_files(
        get_service_client(),
        resolved_path,
        scope=scope,
        source_type=source_type,
        source_ref_prefix=source_ref_prefix,
        include_extensions=include_extensions,
        exclude_dirs=exclude_dirs,
        include_examples=include_examples,
        redact_secrets=redact_secrets,
        dry_run=dry_run,
        max_files=max_files,
        max_content_chars=max_content_chars,
    )
    result["requested_path"] = path
    result["resolved_path"] = resolved_path
    return result


@mcp.tool()
async def onebrain_search_memory(
    query: str,
    limit: int = 10,
    memory_types: list[str] | None = None,
    tags: list[str] | None = None,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search memories through the OneBrain core service."""

    filters = SearchFilters(memory_types=memory_types, tags=tags, scope=scope)
    result = await get_service().search(SearchRequest(query=query, limit=limit, filters=filters))
    return result.model_dump(mode="json")


@mcp.tool()
async def onebrain_search_skills(
    query: str,
    limit: int = 10,
    tags: list[str] | None = None,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search declarative skills stored in OneBrain."""

    filters = SearchFilters(memory_types=["skill"], tags=tags, scope=scope)
    result = await get_service().search(SearchRequest(query=query, limit=limit, filters=filters))
    return result.model_dump(mode="json")


@mcp.tool()
async def onebrain_get_graph(
    query: str | None = None,
    limit: int = 100,
    memory_types: list[str] | None = None,
    tags: list[str] | None = None,
    scope: dict[str, Any] | None = None,
    include_entities: bool = True,
    include_relations: bool = True,
    include_correlations: bool = True,
) -> dict[str, Any]:
    """Return a graph of memories, entities, relations, and inferred correlations."""

    filters = SearchFilters(memory_types=memory_types, tags=tags, scope=scope)
    request = GraphRequest(
        query=query,
        limit=limit,
        filters=filters,
        include_entities=include_entities,
        include_relations=include_relations,
        include_correlations=include_correlations,
    )
    result = await get_service().build_graph(request)
    return result.model_dump(mode="json")


@mcp.tool()
async def onebrain_get_context(
    task: str,
    scope: dict[str, Any] | None = None,
    max_tokens: int = 2000,
    include_rules: bool = True,
    include_related: bool = True,
) -> dict[str, Any]:
    """Return a compact context pack from the OneBrain core service."""

    request = ContextRequest(
        task=task,
        scope=scope or {},
        max_tokens=max_tokens,
        include_rules=include_rules,
        include_related=include_related,
    )
    result = await get_service().compose_context(request)
    return result.model_dump(mode="json")


@mcp.tool()
async def onebrain_correlate(
    memory_id: str | None = None,
    query: str | None = None,
    scope: dict[str, Any] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Find deterministic correlations through the OneBrain core service."""

    parsed_id = uuid.UUID(memory_id) if memory_id else None
    request = CorrelationRequest(memory_id=parsed_id, query=query, scope=scope or {}, limit=limit)
    result = await get_service().correlate(request)
    return result.model_dump(mode="json")


def build_mcp_asgi_app() -> Any:
    return mcp.streamable_http_app()


def run_stdio() -> None:
    mcp.run()
