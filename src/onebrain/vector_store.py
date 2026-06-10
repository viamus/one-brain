from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from onebrain.config import Settings


@dataclass(frozen=True)
class VectorHit:
    memory_id: uuid.UUID
    score: float
    payload: dict[str, Any]


class QdrantMemoryStore:
    def __init__(self, settings: Settings) -> None:
        self.collection_name = settings.qdrant_collection
        self.vector_size = settings.vector_size
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=settings.request_timeout_seconds,
        )

    async def ensure_collection(self) -> None:
        exists = await self._client.collection_exists(self.collection_name)
        if exists:
            return
        await self._client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qm.VectorParams(size=self.vector_size, distance=qm.Distance.COSINE),
        )

    async def health(self) -> bool:
        await self._client.get_collections()
        return True

    async def upsert_memory(
        self,
        *,
        memory_id: uuid.UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        await self.ensure_collection()
        await self._client.upsert(
            collection_name=self.collection_name,
            points=[
                qm.PointStruct(
                    id=str(memory_id),
                    vector=vector,
                    payload=payload,
                )
            ],
        )

    async def delete_memory(self, memory_id: uuid.UUID) -> None:
        await self._client.delete(
            collection_name=self.collection_name,
            points_selector=qm.PointIdsList(points=[str(memory_id)]),
        )

    async def search(
        self,
        *,
        vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        await self.ensure_collection()
        query_filter = self._build_filter(filters or {})
        try:
            result = await self._client.query_points(
                collection_name=self.collection_name,
                query=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
            points = result.points
        except AttributeError:
            points = await self._client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )

        hits: list[VectorHit] = []
        for point in points:
            try:
                memory_id = uuid.UUID(str(point.id))
            except ValueError:
                continue
            hits.append(
                VectorHit(
                    memory_id=memory_id,
                    score=float(point.score),
                    payload=dict(point.payload or {}),
                )
            )
        return hits

    def _build_filter(self, filters: dict[str, Any]) -> qm.Filter | None:
        conditions: list[qm.FieldCondition] = []
        for key, value in filters.items():
            if value is None:
                continue
            if isinstance(value, list) and value:
                conditions.append(
                    qm.FieldCondition(
                        key=key,
                        match=qm.MatchAny(any=[str(item) for item in value]),
                    )
                )
            elif isinstance(value, str | int | float | bool):
                conditions.append(qm.FieldCondition(key=key, match=qm.MatchValue(value=value)))
        if not conditions:
            return None
        return qm.Filter(must=conditions)
