from __future__ import annotations

import httpx
import pytest

from onebrain.http_client import OneBrainApiClient


@pytest.mark.asyncio
async def test_http_client_sends_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    async def fake_post(self: httpx.AsyncClient, path: str, json: dict) -> httpx.Response:
        seen["path"] = path
        seen["authorization"] = self.headers.get("authorization", "")
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", path))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = OneBrainApiClient(base_url="http://onebrain.test", api_key="secret")
    result = await client.get_context({"task": "remember this"})

    assert result == {"ok": True}
    assert seen == {"path": "/v1/context", "authorization": "Bearer secret"}


@pytest.mark.asyncio
async def test_http_client_raises_runtime_error_for_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post(self: httpx.AsyncClient, path: str, json: dict) -> httpx.Response:
        return httpx.Response(403, text="invalid API key", request=httpx.Request("POST", path))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = OneBrainApiClient(base_url="http://onebrain.test", api_key="bad")

    with pytest.raises(RuntimeError, match="403 invalid API key"):
        await client.search_memory({"query": "x"})
