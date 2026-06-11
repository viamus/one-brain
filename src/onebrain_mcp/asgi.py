from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from onebrain_host.runtime import close_runtime, get_runtime_settings
from onebrain_mcp.auth import MCP_PATH, McpApiKeyAuthMiddleware
from onebrain_mcp.server import build_mcp_asgi_app


async def healthz(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def build_application() -> Starlette:
    mcp_application = build_mcp_asgi_app()
    mcp_routes = [
        route for route in mcp_application.routes if getattr(route, "path", None) == MCP_PATH
    ]
    if not mcp_routes:
        raise RuntimeError("FastMCP streamable HTTP route /mcp was not registered")

    settings = get_runtime_settings()

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with mcp_application.router.lifespan_context(app):
            try:
                yield
            finally:
                await close_runtime()

    return Starlette(
        routes=[Route("/healthz", healthz, methods=["GET"]), *mcp_routes],
        middleware=[
            Middleware(
                McpApiKeyAuthMiddleware,
                accepted_keys=settings.api_key_values,
                required=settings.mcp_require_api_key,
            )
        ],
        lifespan=lifespan,
    )


application = build_application()
