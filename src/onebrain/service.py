from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from sqlalchemy import Select, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from onebrain.config import Settings
from onebrain.embeddings import EmbeddingProvider
from onebrain.models import AuditEvent, Entity, Memory, MemoryEntity, Relation
from onebrain.schemas import (
    ContextMemory,
    ContextPack,
    ContextRequest,
    CorrelationHit,
    CorrelationRequest,
    CorrelationResponse,
    EntityInput,
    MemoryCreate,
    MemoryOut,
    SearchFilters,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from onebrain.text import content_hash, estimate_tokens, extract_heuristic_entities, normalize_name
from onebrain.vector_store import QdrantMemoryStore


class OneBrainService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        embeddings: EmbeddingProvider,
        vector_store: QdrantMemoryStore,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._embeddings = embeddings
        self._vector_store = vector_store

    async def capture_memory(self, payload: MemoryCreate, actor: str = "system") -> MemoryOut:
        async with self._session_factory() as session:
            memory = Memory(
                memory_type=payload.memory_type,
                title=payload.title,
                content=payload.content.strip(),
                content_hash=content_hash(payload.content, payload.scope),
                scope=payload.scope,
                tags=payload.tags,
                confidence=payload.confidence,
                source_type=payload.source.source_type,
                source_ref=payload.source.source_ref,
                valid_from=payload.valid_from,
                valid_to=payload.valid_to,
                supersedes_id=payload.supersedes_id,
                metadata_=payload.metadata,
            )
            session.add(memory)
            await session.flush()

            entity_inputs = list(payload.entities)
            entity_inputs.extend(self._entities_from_scope(payload.scope))
            if self._settings.enable_heuristic_entity_extraction:
                entity_inputs.extend(
                    EntityInput(name=name, entity_type=kind)
                    for name, kind in extract_heuristic_entities(payload.content)
                )
            await self._attach_entities(session, memory, entity_inputs)
            for relation in payload.relations:
                from_entity = await self._upsert_entity(session, relation.from_entity)
                to_entity = await self._upsert_entity(session, relation.to_entity)
                session.add(
                    Relation(
                        from_entity_id=from_entity.id,
                        to_entity_id=to_entity.id,
                        relation_type=relation.relation_type,
                        confidence=relation.confidence,
                        valid_from=relation.valid_from,
                        valid_to=relation.valid_to,
                        evidence_memory_id=memory.id,
                        metadata_=relation.metadata,
                    )
                )

            session.add(
                AuditEvent(
                    actor=actor,
                    action="memory.capture",
                    subject_type="memory",
                    subject_id=memory.id,
                    details={"memory_type": memory.memory_type, "source_type": memory.source_type},
                )
            )
            await session.commit()

        await self.index_memory(memory.id)
        return await self.get_memory(memory.id)

    async def get_memory(self, memory_id: uuid.UUID) -> MemoryOut:
        async with self._session_factory() as session:
            memory = await session.get(Memory, memory_id)
            if memory is None:
                raise KeyError(f"memory not found: {memory_id}")
            return MemoryOut.model_validate(memory)

    async def index_memory(self, memory_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            memory = await session.get(Memory, memory_id)
            if memory is None:
                raise KeyError(f"memory not found: {memory_id}")
            vector = (await self._embeddings.embed([self._embedding_text(memory)]))[0]
            payload = self._vector_payload(memory)
            try:
                await self._vector_store.upsert_memory(
                    memory_id=memory.id,
                    vector=vector,
                    payload=payload,
                )
            except Exception as exc:
                await session.execute(
                    update(Memory)
                    .where(Memory.id == memory.id)
                    .values(vector_status="failed", vector_error=str(exc)[:2000])
                )
                await session.commit()
                raise
            await session.execute(
                update(Memory)
                .where(Memory.id == memory.id)
                .values(vector_status="indexed", vector_error=None)
            )
            await session.commit()

    async def search(self, request: SearchRequest) -> SearchResponse:
        vector_hits = await self._safe_vector_search(request)
        keyword_hits = await self._keyword_search(request.query, request.filters, request.limit)

        scores: dict[uuid.UUID, float] = {}
        reasons: dict[uuid.UUID, list[str]] = defaultdict(list)
        for hit in vector_hits:
            scores[hit.memory_id] = max(scores.get(hit.memory_id, 0.0), hit.score)
            reasons[hit.memory_id].append("vector")
        for memory_id, score in keyword_hits.items():
            scores[memory_id] = max(scores.get(memory_id, 0.0), score)
            reasons[memory_id].append("keyword")

        memories = await self._load_memories(scores.keys())
        hits = [
            SearchHit(
                memory=MemoryOut.model_validate(memory),
                score=round(scores[memory.id], 6),
                reasons=sorted(set(reasons[memory.id])),
            )
            for memory in memories
        ]
        hits.sort(key=lambda item: item.score, reverse=True)
        return SearchResponse(query=request.query, hits=hits[: request.limit])

    async def compose_context(self, request: ContextRequest) -> ContextPack:
        search_filters = request.filters.model_copy(update={"scope": request.scope or None})
        response = await self.search(
            SearchRequest(
                query=request.task,
                limit=50,
                filters=search_filters,
                include_graph=request.include_related,
            )
        )

        rules: list[ContextMemory] = []
        memories: list[ContextMemory] = []
        related: list[ContextMemory] = []
        used_ids: set[uuid.UUID] = set()
        budget_chars = request.max_tokens * 4
        used_chars = 0
        omitted = 0

        for hit in response.hits:
            item = self._context_memory(hit)
            item_chars = len(item.content) + 120
            if used_chars + item_chars > budget_chars:
                omitted += 1
                continue
            used_chars += item_chars
            used_ids.add(item.id)
            if item.memory_type == "rule" and request.include_rules:
                rules.append(item)
            else:
                memories.append(item)

        if request.include_related and used_ids:
            related_hits = await self._related_memories(used_ids, request.scope, limit=20)
            for hit in related_hits:
                if hit.memory.id in used_ids:
                    continue
                item = self._context_memory(hit)
                item_chars = len(item.content) + 120
                if used_chars + item_chars > budget_chars:
                    omitted += 1
                    continue
                used_chars += item_chars
                used_ids.add(item.id)
                related.append(item)

        return ContextPack(
            task=request.task,
            token_budget=request.max_tokens,
            estimated_tokens=estimate_tokens(
                "\n".join(item.content for item in [*rules, *memories, *related])
            ),
            rules=rules,
            memories=memories,
            related=related,
            omitted=omitted,
        )

    async def correlate(self, request: CorrelationRequest) -> CorrelationResponse:
        base_memory_ids: set[uuid.UUID] = set()
        if request.memory_id:
            base_memory_ids.add(request.memory_id)
        if request.query:
            search = await self.search(
                SearchRequest(
                    query=request.query,
                    limit=request.limit,
                    filters=SearchFilters(scope=request.scope or None),
                )
            )
            base_memory_ids.update(hit.memory.id for hit in search.hits)

        correlations: list[CorrelationHit] = []
        for memory_id in base_memory_ids:
            related = await self._related_memories({memory_id}, request.scope, request.limit)
            for hit in related:
                if hit.memory.id != memory_id:
                    correlations.append(
                        CorrelationHit(
                            memory_id=memory_id,
                            related_memory_id=hit.memory.id,
                            score=hit.score,
                            reasons=hit.reasons,
                        )
                    )
        correlations.sort(key=lambda item: item.score, reverse=True)
        return CorrelationResponse(correlations=correlations[: request.limit])

    async def health(self) -> dict[str, bool]:
        database_ok = False
        qdrant_ok = False
        async with self._session_factory() as session:
            await session.execute(text("select 1"))
            database_ok = True
        qdrant_ok = await self._vector_store.health()
        return {"database": database_ok, "qdrant": qdrant_ok}

    async def _safe_vector_search(self, request: SearchRequest):
        vector = (await self._embeddings.embed([request.query]))[0]
        filters: dict[str, Any] = {"status": request.filters.statuses}
        if request.filters.memory_types:
            filters["memory_type"] = request.filters.memory_types
        try:
            return await self._vector_store.search(
                vector=vector,
                limit=request.limit * 3,
                filters=filters,
            )
        except Exception:
            return []

    async def _keyword_search(
        self,
        query: str,
        filters: SearchFilters,
        limit: int,
    ) -> dict[uuid.UUID, float]:
        async with self._session_factory() as session:
            stmt = self._filtered_memory_select(filters)
            terms = [term for term in query.split() if len(term) > 2]
            if terms:
                ilike_terms = [f"%{term}%" for term in terms[:8]]
                stmt = stmt.where(
                    or_(
                        *[Memory.content.ilike(term) for term in ilike_terms],
                        *[Memory.title.ilike(term) for term in ilike_terms],
                    )
                )
            stmt = stmt.limit(limit * 3)
            result = await session.execute(stmt)
            memories = result.scalars().all()
        if not memories:
            return {}
        query_terms = {term.lower() for term in terms}
        scores: dict[uuid.UUID, float] = {}
        for memory in memories:
            haystack = f"{memory.title or ''} {memory.content}".lower()
            overlap = sum(1 for term in query_terms if term in haystack)
            scores[memory.id] = min(1.0, 0.35 + overlap / max(1, len(query_terms)))
        return scores

    def _filtered_memory_select(self, filters: SearchFilters) -> Select[tuple[Memory]]:
        stmt = select(Memory)
        if filters.statuses:
            stmt = stmt.where(Memory.status.in_(filters.statuses))
        if filters.memory_types:
            stmt = stmt.where(Memory.memory_type.in_(filters.memory_types))
        if filters.tags:
            normalized_tags = [tag.strip().lower() for tag in filters.tags]
            stmt = stmt.where(Memory.tags.contains(normalized_tags))
        if filters.scope:
            stmt = stmt.where(Memory.scope.contains(filters.scope))
        return stmt.order_by(Memory.confidence.desc(), Memory.updated_at.desc())

    async def _load_memories(self, memory_ids: Iterable[uuid.UUID]) -> list[Memory]:
        ids = list(memory_ids)
        if not ids:
            return []
        async with self._session_factory() as session:
            result = await session.execute(select(Memory).where(Memory.id.in_(ids)))
            return list(result.scalars().all())

    async def _related_memories(
        self,
        memory_ids: set[uuid.UUID],
        scope: dict[str, Any],
        limit: int,
    ) -> list[SearchHit]:
        async with self._session_factory() as session:
            base_entities = await session.execute(
                select(MemoryEntity.entity_id).where(MemoryEntity.memory_id.in_(memory_ids))
            )
            entity_ids = {row[0] for row in base_entities}
            if not entity_ids:
                return []
            related_result = await session.execute(
                select(Memory)
                .join(MemoryEntity, MemoryEntity.memory_id == Memory.id)
                .options(selectinload(Memory.entities))
                .where(MemoryEntity.entity_id.in_(entity_ids))
                .where(Memory.status == "active")
                .limit(limit * 3)
            )
            memories = list(related_result.scalars().unique().all())

        hits: list[SearchHit] = []
        for memory in memories:
            if scope and not all(memory.scope.get(key) == value for key, value in scope.items()):
                continue
            shared = len({item.entity_id for item in memory.entities} & entity_ids)
            hits.append(
                SearchHit(
                    memory=MemoryOut.model_validate(memory),
                    score=min(1.0, 0.4 + shared * 0.2),
                    reasons=["shared_entity"],
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:limit]

    async def _attach_entities(
        self,
        session: AsyncSession,
        memory: Memory,
        inputs: Iterable[EntityInput],
    ) -> None:
        seen: set[tuple[str, str, str]] = set()
        for entity_input in inputs:
            entity = await self._upsert_entity(session, entity_input)
            key = (str(memory.id), str(entity.id), entity_input.role)
            if key in seen:
                continue
            seen.add(key)
            session.add(
                MemoryEntity(memory_id=memory.id, entity_id=entity.id, role=entity_input.role)
            )

    async def _upsert_entity(self, session: AsyncSession, entity_input: EntityInput) -> Entity:
        normalized = normalize_name(entity_input.name)
        result = await session.execute(
            select(Entity).where(
                Entity.normalized_name == normalized,
                Entity.entity_type == entity_input.entity_type,
            )
        )
        entity = result.scalar_one_or_none()
        if entity is not None:
            return entity
        entity = Entity(
            name=entity_input.name.strip(),
            normalized_name=normalized,
            entity_type=entity_input.entity_type,
            summary=entity_input.summary,
            metadata_=entity_input.metadata,
        )
        session.add(entity)
        await session.flush()
        return entity

    def _entities_from_scope(self, scope: dict[str, Any]) -> list[EntityInput]:
        entity_inputs: list[EntityInput] = []
        for key in ("project", "repository", "repo", "team", "domain", "client"):
            value = scope.get(key)
            if isinstance(value, str) and value.strip():
                entity_inputs.append(EntityInput(name=value, entity_type=key, role="scope"))
        return entity_inputs

    def _embedding_text(self, memory: Memory) -> str:
        title = f"{memory.title}\n" if memory.title else ""
        tags = " ".join(memory.tags)
        scope = " ".join(f"{key}:{value}" for key, value in sorted(memory.scope.items()))
        return f"{title}{memory.memory_type}\n{scope}\n{tags}\n{memory.content}"

    def _vector_payload(self, memory: Memory) -> dict[str, Any]:
        return {
            "memory_id": str(memory.id),
            "memory_type": memory.memory_type,
            "status": memory.status,
            "title": memory.title,
            "tags": memory.tags,
            "scope": memory.scope,
            "confidence": memory.confidence,
            "source_type": memory.source_type,
        }

    def _context_memory(self, hit: SearchHit) -> ContextMemory:
        memory = hit.memory
        return ContextMemory(
            id=memory.id,
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            tags=memory.tags,
            scope=memory.scope,
            confidence=memory.confidence,
            score=hit.score,
            reasons=hit.reasons,
        )
