from __future__ import annotations

import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from onebrain.config import get_settings
from onebrain.http_client import OneBrainApiClient
from onebrain.schemas import (
    ContextRequest,
    CorrelationRequest,
    MemoryCreate,
    SearchFilters,
    SearchRequest,
)

mcp = FastMCP(
    "OneBrain",
    instructions=(
        "OneBrain stores durable memories through the OneBrain HTTP API and returns "
        "deterministic context packs. Use capture only for stable, non-secret "
        "information. Use context before tasks that need prior rules, project context, "
        "decisions, workflows, or pitfalls."
    ),
)

_client: OneBrainApiClient | None = None


def get_client() -> OneBrainApiClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = OneBrainApiClient(
            base_url=settings.api_url,
            api_key=settings.outbound_api_key,
            timeout_seconds=settings.request_timeout_seconds,
        )
    return _client


@mcp.tool()
async def onebrain_capture_memory(memory: dict[str, Any]) -> dict[str, Any]:
    """Store a durable memory through the OneBrain HTTP API."""

    payload = MemoryCreate.model_validate(memory).model_dump(mode="json")
    return await get_client().capture_memory(payload)


@mcp.tool()
async def onebrain_search_memory(
    query: str,
    limit: int = 10,
    memory_types: list[str] | None = None,
    tags: list[str] | None = None,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search memories through the OneBrain HTTP API."""

    filters = SearchFilters(memory_types=memory_types, tags=tags, scope=scope)
    payload = SearchRequest(query=query, limit=limit, filters=filters).model_dump(mode="json")
    return await get_client().search_memory(payload)


@mcp.tool()
async def onebrain_get_context(
    task: str,
    scope: dict[str, Any] | None = None,
    max_tokens: int = 2000,
    include_rules: bool = True,
    include_related: bool = True,
) -> dict[str, Any]:
    """Return a compact context pack from the OneBrain HTTP API."""

    payload = ContextRequest(
        task=task,
        scope=scope or {},
        max_tokens=max_tokens,
        include_rules=include_rules,
        include_related=include_related,
    ).model_dump(mode="json")
    return await get_client().get_context(payload)


@mcp.tool()
async def onebrain_correlate(
    memory_id: str | None = None,
    query: str | None = None,
    scope: dict[str, Any] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Find deterministic correlations through the OneBrain HTTP API."""

    parsed_id = uuid.UUID(memory_id) if memory_id else None
    payload = CorrelationRequest(
        memory_id=parsed_id, query=query, scope=scope or {}, limit=limit
    ).model_dump(mode="json")
    return await get_client().correlate(payload)


def run() -> None:
    mcp.run()
