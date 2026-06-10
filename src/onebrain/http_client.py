from __future__ import annotations

from typing import Any

import httpx


class OneBrainApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def capture_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/v1/memories", payload)

    async def search_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/v1/search", payload)

    async def get_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/v1/context", payload)

    async def correlate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/v1/correlate", payload)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = self._headers()
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.post(path, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text[:1000]
            raise RuntimeError(
                f"OneBrain API request failed: {response.status_code} {detail}"
            ) from exc
        return response.json()

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}
