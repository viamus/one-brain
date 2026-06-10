from __future__ import annotations

import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from onebrain.config import get_settings
from onebrain.db import create_engine, create_session_factory
from onebrain.embeddings import build_embedding_provider
from onebrain.schemas import (
    ContextRequest,
    CorrelationRequest,
    MemoryCreate,
    SearchFilters,
    SearchRequest,
)
from onebrain.service import OneBrainService
from onebrain.vector_store import QdrantMemoryStore

mcp = FastMCP(
    "OneBrain",
    instructions=(
        "OneBrain stores durable memories and returns deterministic context packs. "
        "Use capture only for stable, non-secret information. Use context before "
        "tasks that need prior rules, project context, decisions, workflows, or pitfalls."
    ),
)

_service: OneBrainService | None = None


def get_service() -> OneBrainService:
    global _service
    if _service is None:
        settings = get_settings()
        engine = create_engine(settings)
        _service = OneBrainService(
            settings=settings,
            session_factory=create_session_factory(engine),
            embeddings=build_embedding_provider(settings),
            vector_store=QdrantMemoryStore(settings),
        )
    return _service


@mcp.tool()
async def onebrain_capture_memory(memory: dict[str, Any]) -> dict[str, Any]:
    """Store a durable memory with optional entities, relations, tags, and scope."""

    result = await get_service().capture_memory(MemoryCreate.model_validate(memory), actor="mcp")
    return result.model_dump(mode="json", by_alias=False)


@mcp.tool()
async def onebrain_search_memory(
    query: str,
    limit: int = 10,
    memory_types: list[str] | None = None,
    tags: list[str] | None = None,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search memories using deterministic keyword search plus Qdrant vector recall."""

    filters = SearchFilters(memory_types=memory_types, tags=tags, scope=scope)
    result = await get_service().search(SearchRequest(query=query, limit=limit, filters=filters))
    return result.model_dump(mode="json")


@mcp.tool()
async def onebrain_get_context(
    task: str,
    scope: dict[str, Any] | None = None,
    max_tokens: int = 2000,
    include_rules: bool = True,
    include_related: bool = True,
) -> dict[str, Any]:
    """Return a compact context pack for an LLM task without using an LLM internally."""

    result = await get_service().compose_context(
        ContextRequest(
            task=task,
            scope=scope or {},
            max_tokens=max_tokens,
            include_rules=include_rules,
            include_related=include_related,
        )
    )
    return result.model_dump(mode="json")


@mcp.tool()
async def onebrain_correlate(
    memory_id: str | None = None,
    query: str | None = None,
    scope: dict[str, Any] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Find deterministic correlations by shared graph entities and search results."""

    parsed_id = uuid.UUID(memory_id) if memory_id else None
    result = await get_service().correlate(
        CorrelationRequest(memory_id=parsed_id, query=query, scope=scope or {}, limit=limit)
    )
    return result.model_dump(mode="json")


def run() -> None:
    mcp.run()
