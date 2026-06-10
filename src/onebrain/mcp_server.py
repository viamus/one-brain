from __future__ import annotations

import secrets
import uuid
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from onebrain.config import get_settings
from onebrain.http_client import OneBrainApiClient
from onebrain.schemas import (
    ContextRequest,
    CorrelationRequest,
    MemoryCreate,
    SearchFilters,
    SearchRequest,
)

HEALTH_PATH = "/healthz"

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


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Any,
        *,
        accepted_keys: list[str],
        required: bool,
    ) -> None:
        super().__init__(app)
        self.accepted_keys = accepted_keys
        self.required = required

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.url.path == HEALTH_PATH or request.method == "OPTIONS":
            return await call_next(request)
        if not self.required:
            return await call_next(request)
        if not self.accepted_keys:
            return JSONResponse(
                {"detail": "MCP API key authentication is not configured"},
                status_code=503,
            )

        candidate = request.headers.get("x-api-key", "")
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            candidate = authorization[7:].strip()

        if not candidate:
            return JSONResponse({"detail": "missing API key"}, status_code=401)
        if not any(secrets.compare_digest(candidate, key) for key in self.accepted_keys):
            return JSONResponse({"detail": "invalid API key"}, status_code=403)
        return await call_next(request)


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


@mcp.custom_route(HEALTH_PATH, methods=["GET"], include_in_schema=False)
async def healthz(_: Request) -> Response:
    return JSONResponse({"status": "ok"})


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


def run_http() -> None:
    settings = get_settings()
    app = mcp.streamable_http_app()
    app.add_middleware(
        ApiKeyAuthMiddleware,
        accepted_keys=settings.api_key_values,
        required=settings.mcp_require_api_key,
    )
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port, log_level="info")
