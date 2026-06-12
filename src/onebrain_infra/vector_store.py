from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from onebrain_core.common.config import Settings


@dataclass(frozen=True)
class VectorHit:
    memory_id: uuid.UUID
    score: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class VectorFilterClause:
    sql: str
    parameters: dict[str, Any]


class MemoryVectorStore(Protocol):
    async def health(self) -> bool:
        raise NotImplementedError

    async def upsert_memory(
        self,
        *,
        memory_id: uuid.UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        raise NotImplementedError

    async def delete_memory(self, memory_id: uuid.UUID) -> None:
        raise NotImplementedError

    async def search(
        self,
        *,
        vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        raise NotImplementedError


class PgVectorMemoryStore:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.table_name = _safe_identifier(settings.vector_table)
        self.vector_size = settings.vector_size
        self._session_factory = session_factory
        self._schema_ready = False

    async def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        async with self._session_factory() as session:
            await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await session.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        memory_id uuid PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
                        embedding vector({self.vector_size}) NOT NULL,
                        payload jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                        created_at timestamptz NOT NULL DEFAULT now(),
                        updated_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            await session.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_{self.table_name}_payload_gin
                    ON {self.table_name} USING gin (payload)
                    """
                )
            )
            await session.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_{self.table_name}_embedding_hnsw
                    ON {self.table_name} USING hnsw (embedding vector_cosine_ops)
                    """
                )
            )
            await session.commit()
        self._schema_ready = True

    async def health(self) -> bool:
        async with self._session_factory() as session:
            await session.execute(text(f"SELECT 1 FROM {self.table_name} LIMIT 1"))  # noqa: S608
        return True

    async def upsert_memory(
        self,
        *,
        memory_id: uuid.UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        self._validate_vector(vector)
        await self.ensure_schema()
        upsert_sql = f"""
            INSERT INTO {self.table_name} (memory_id, embedding, payload)
            VALUES (:memory_id, (:embedding)::vector, (:payload)::jsonb)
            ON CONFLICT (memory_id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                payload = EXCLUDED.payload,
                updated_at = now()
            """  # noqa: S608
        async with self._session_factory() as session:
            await session.execute(
                text(upsert_sql),
                {
                    "memory_id": memory_id,
                    "embedding": _vector_literal(vector),
                    "payload": json.dumps(payload, separators=(",", ":")),
                },
            )
            await session.commit()

    async def delete_memory(self, memory_id: uuid.UUID) -> None:
        delete_sql = f"DELETE FROM {self.table_name} WHERE memory_id = :memory_id"  # noqa: S608
        async with self._session_factory() as session:
            await session.execute(
                text(delete_sql),
                {"memory_id": memory_id},
            )
            await session.commit()

    async def search(
        self,
        *,
        vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        self._validate_vector(vector)
        await self.ensure_schema()
        filter_clause = build_memory_filter_clause(filters or {})
        search_sql = f"""
            SELECT
                v.memory_id,
                1 - (v.embedding <=> (:embedding)::vector) AS score,
                v.payload
            FROM {self.table_name} v
            JOIN memories m ON m.id = v.memory_id
            {filter_clause.sql}
            ORDER BY v.embedding <=> (:embedding)::vector
            LIMIT :limit
            """  # noqa: S608
        query = text(search_sql)
        params: dict[str, Any] = {
            "embedding": _vector_literal(vector),
            "limit": limit,
            **filter_clause.parameters,
        }
        async with self._session_factory() as session:
            result = await session.execute(query, params)
            rows = result.mappings().all()
        return [
            VectorHit(
                memory_id=uuid.UUID(str(row["memory_id"])),
                score=float(row["score"]),
                payload=dict(row["payload"] or {}),
            )
            for row in rows
        ]

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != self.vector_size:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.vector_size}, got {len(vector)}"
            )


def build_memory_filter_clause(filters: dict[str, Any]) -> VectorFilterClause:
    clauses: list[str] = []
    parameters: dict[str, Any] = {}

    for key, value in filters.items():
        if value is None or value == []:
            continue
        if key == "status":
            clauses.append(_in_clause("m.status", "status", value, parameters))
        elif key == "memory_type":
            clauses.append(_in_clause("m.memory_type", "memory_type", value, parameters))
        elif key == "tags":
            clauses.append(_tags_clause(value, parameters))
        elif key.startswith("scope."):
            scope_key = key.removeprefix("scope.")
            if scope_key:
                param_key = f"scope_key_{len(parameters)}"
                param_value = f"scope_value_{len(parameters)}"
                parameters[param_key] = scope_key
                parameters[param_value] = str(value)
                clauses.append(f"m.scope ->> :{param_key} = :{param_value}")

    if not clauses:
        return VectorFilterClause(sql="", parameters={})
    return VectorFilterClause(sql="WHERE " + " AND ".join(clauses), parameters=parameters)


def _in_clause(
    column: str,
    prefix: str,
    value: Any,
    parameters: dict[str, Any],
) -> str:
    values = value if isinstance(value, list) else [value]
    names: list[str] = []
    for index, item in enumerate(values):
        name = f"{prefix}_{index}"
        parameters[name] = str(item)
        names.append(f":{name}")
    return f"{column} IN ({', '.join(names)})"


def _tags_clause(value: Any, parameters: dict[str, Any]) -> str:
    values = value if isinstance(value, list) else [value]
    names: list[str] = []
    for index, item in enumerate(values):
        name = f"tag_{index}"
        parameters[name] = str(item)
        names.append(f":{name}")
    return f"m.tags ?| ARRAY[{', '.join(names)}]"


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(float(value), ".12g") for value in vector) + "]"


def _safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Invalid SQL identifier: {value}")
    return value
