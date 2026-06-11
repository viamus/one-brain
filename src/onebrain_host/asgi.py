from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Mount

from onebrain_host.disconnects import DisconnectTolerantAsgiApp

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onebrain_host.settings")


def build_application() -> Starlette:
    from onebrain_host.runtime import close_runtime, get_runtime_settings
    from onebrain_mcp.auth import MCP_PATH, McpApiKeyAuthMiddleware
    from onebrain_mcp.server import build_mcp_asgi_app

    django_application = DisconnectTolerantAsgiApp(get_asgi_application())
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
        routes=[
            *mcp_routes,
            Mount("/", app=django_application),
        ],
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
