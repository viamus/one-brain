from __future__ import annotations

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from onebrain.mcp_server import ApiKeyAuthMiddleware


async def ok_endpoint(request):
    return JSONResponse({"ok": True})


def build_test_app() -> Starlette:
    app = Starlette(routes=[Route("/mcp", ok_endpoint, methods=["POST"])])
    app.add_middleware(ApiKeyAuthMiddleware, accepted_keys=["secret"], required=True)
    return app


@pytest.mark.asyncio
async def test_mcp_http_auth_requires_api_key() -> None:
    transport = httpx.ASGITransport(app=build_test_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/mcp")

    assert response.status_code == 401
    assert response.json() == {"detail": "missing API key"}


@pytest.mark.asyncio
async def test_mcp_http_auth_accepts_bearer_token() -> None:
    transport = httpx.ASGITransport(app=build_test_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/mcp", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
