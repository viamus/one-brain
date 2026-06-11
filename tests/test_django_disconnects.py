from __future__ import annotations

import pytest
from django.core.exceptions import RequestAborted

from onebrain_django.disconnects import DisconnectTolerantAsgiApp


async def _receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(message: dict[str, object]) -> None:
    assert message


@pytest.mark.asyncio
async def test_disconnect_tolerant_asgi_app_suppresses_request_aborted() -> None:
    async def app(scope, receive, send):  # noqa: ANN001
        raise RequestAborted()

    tolerant_app = DisconnectTolerantAsgiApp(app)

    await tolerant_app({"type": "http", "path": "/readyz"}, _receive, _send)


@pytest.mark.asyncio
async def test_disconnect_tolerant_asgi_app_reraises_real_errors() -> None:
    async def app(scope, receive, send):  # noqa: ANN001
        raise RuntimeError("real failure")

    tolerant_app = DisconnectTolerantAsgiApp(app)

    with pytest.raises(RuntimeError, match="real failure"):
        await tolerant_app({"type": "http", "path": "/api/v1/ingestion/commit"}, _receive, _send)
