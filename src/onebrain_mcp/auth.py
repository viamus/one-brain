from __future__ import annotations

import secrets
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

MCP_PATH = "/mcp"


class McpApiKeyAuthMiddleware(BaseHTTPMiddleware):
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
        if not _is_mcp_request(request) or request.method == "OPTIONS":
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


def _is_mcp_request(request: Request) -> bool:
    path = request.url.path.rstrip("/")
    return path == MCP_PATH
