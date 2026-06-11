from __future__ import annotations

import math
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from itertools import combinations
from typing import Any

import structlog
from sqlalchemy import Select, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from onebrain_core.common.config import Settings
from onebrain_core.common.text import (
    content_hash,
    estimate_tokens,
    extract_heuristic_entities,
    normalize_name,
)
from onebrain_core.contracts.schemas import (
    ContextMemory,
    ContextPack,
    ContextRequest,
    CorrelationHit,
    CorrelationRequest,
    CorrelationResponse,
    EntityInput,
    GraphEdge,
    GraphNode,
    GraphRequest,
    GraphResponse,
    MemoryCreate,
    MemoryOut,
    SearchFilters,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from onebrain_core.infrastructure.embeddings import EmbeddingProvider
from onebrain_core.infrastructure.models import (
    AuditEvent,
    Entity,
    Memory,
    MemoryEntity,
    MemoryLink,
    Relation,
)
from onebrain_core.infrastructure.vector_store import QdrantMemoryStore

LOGGER = structlog.get_logger(__name__)

CORRELATION_STOPWORDS = {
    "about",
    "above",
    "active",
    "after",
    "again",
    "against",
    "also",
    "always",
    "and",
    "antes",
    "are",
    "area",
    "areas",
    "available",
    "based",
    "because",
    "been",
    "being",
    "browser",
    "cada",
    "caso",
    "catalog",
    "codex",
    "com",
    "como",
    "content",
    "context",
    "data",
    "description",
    "details",
    "deve",
    "does",
    "dos",
    "ela",
    "ele",
    "eles",
    "essa",
    "esse",
    "esta",
    "este",
    "example",
    "examples",
    "feedback",
    "false",
    "file",
    "files",
    "for",
    "from",
    "guidance",
    "had",
    "has",
    "have",
    "import",
    "imported",
    "inside",
    "into",
    "its",
    "items",
    "json",
    "latest",
    "libraries",
    "library",
    "manual",
    "mais",
    "mas",
    "metadata",
    "memoria",
    "memory",
    "module",
    "must",
    "name",
    "nao",
    "not",
    "only",
    "onebrain",
    "para",
    "pela",
    "pelo",
    "por",
    "private",
    "project",
    "que",
    "query",
    "read",
    "reference",
    "references",
    "repo",
    "repository",
    "required",
    "requires",
    "scope",
    "section",
    "sem",
    "ser",
    "should",
    "source",
    "status",
    "sua",
    "summary",
    "the",
    "this",
    "text",
    "toolbox",
    "toolkit",
    "true",
    "under",
    "uma",
    "use",
    "used",
    "uses",
    "using",
    "value",
    "values",
    "when",
    "wiki",
    "with",
    "work",
}


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

    async def get_memory_by_source_ref(self, source_ref: str) -> MemoryOut:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Memory)
                .where(Memory.source_ref == source_ref)
                .where(Memory.status == "active")
                .order_by(Memory.created_at.desc())
                .limit(1)
            )
            memory = result.scalar_one_or_none()
            if memory is None:
                raise KeyError(f"memory source_ref not found: {source_ref}")
            return MemoryOut.model_validate(memory)

    async def link_memories(
        self,
        *,
        from_memory_id: uuid.UUID | str,
        to_memory_id: uuid.UUID | str,
        link_type: str,
        confidence: float = 0.85,
        order_index: int | None = None,
        evidence: str | None = None,
        metadata: dict[str, Any] | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        from_id = uuid.UUID(str(from_memory_id))
        to_id = uuid.UUID(str(to_memory_id))
        normalized_link_type = normalize_name(link_type)
        async with self._session_factory() as session:
            result = await session.execute(
                select(MemoryLink)
                .where(MemoryLink.from_memory_id == from_id)
                .where(MemoryLink.to_memory_id == to_id)
                .where(MemoryLink.link_type == normalized_link_type)
            )
            link = result.scalar_one_or_none()
            if link is None:
                link = MemoryLink(
                    from_memory_id=from_id,
                    to_memory_id=to_id,
                    link_type=normalized_link_type,
                )
                session.add(link)

            link.confidence = confidence
            link.order_index = order_index
            link.evidence = evidence
            link.metadata_ = metadata or {}
            await session.flush()
            session.add(
                AuditEvent(
                    actor=actor,
                    action="memory.link",
                    subject_type="memory_link",
                    subject_id=link.id,
                    details={
                        "from_memory_id": str(from_id),
                        "to_memory_id": str(to_id),
                        "link_type": normalized_link_type,
                    },
                )
            )
            await session.commit()
            return {
                "id": str(link.id),
                "from_memory_id": str(from_id),
                "to_memory_id": str(to_id),
                "link_type": normalized_link_type,
                "confidence": link.confidence,
                "order_index": link.order_index,
                "evidence": link.evidence,
                "metadata": link.metadata_,
            }

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

    async def build_graph(self, request: GraphRequest) -> GraphResponse:
        memories = await self._graph_memories(request)
        memory_ids = {memory.id for memory in memories}
        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}

        for memory in memories:
            nodes[self._memory_node_id(memory.id)] = self._memory_graph_node(memory)

        entity_rows: list[tuple[uuid.UUID, str, Entity]] = []
        if memory_ids and (
            request.include_entities or request.include_relations or request.include_correlations
        ):
            entity_rows = await self._graph_memory_entities(memory_ids)

        entity_ids = {entity.id for _, _, entity in entity_rows}
        include_entity_nodes = request.include_entities or request.include_relations
        if include_entity_nodes:
            for _, _, entity in entity_rows:
                nodes.setdefault(self._entity_node_id(entity.id), self._entity_graph_node(entity))

        if request.include_entities:
            for memory_id, role, entity in entity_rows:
                edge = GraphEdge(
                    id=f"memory_entity:{memory_id}:{entity.id}:{role}",
                    source=self._memory_node_id(memory_id),
                    target=self._entity_node_id(entity.id),
                    edge_type="mentions",
                    label=role,
                    weight=0.55,
                    metadata={"role": role},
                )
                edges[edge.id] = edge

        if request.include_relations and entity_ids:
            for relation in await self._graph_relations(entity_ids):
                edge = GraphEdge(
                    id=f"relation:{relation.id}",
                    source=self._entity_node_id(relation.from_entity_id),
                    target=self._entity_node_id(relation.to_entity_id),
                    edge_type="relation",
                    label=relation.relation_type,
                    weight=max(0.2, relation.confidence),
                    confidence=relation.confidence,
                    metadata={
                        "relation_type": relation.relation_type,
                        "evidence_memory_id": str(relation.evidence_memory_id)
                        if relation.evidence_memory_id
                        else None,
                        "metadata": relation.metadata_,
                    },
                )
                edges[edge.id] = edge

        if request.include_relations and memory_ids:
            for link in await self._graph_memory_links(memory_ids):
                edge = GraphEdge(
                    id=f"memory_link:{link.id}",
                    source=self._memory_node_id(link.from_memory_id),
                    target=self._memory_node_id(link.to_memory_id),
                    edge_type="memory_link",
                    label=link.link_type,
                    weight=max(0.25, link.confidence),
                    confidence=link.confidence,
                    metadata={
                        "link_type": link.link_type,
                        "order_index": link.order_index,
                        "evidence": link.evidence,
                        "metadata": link.metadata_,
                    },
                )
                edges[edge.id] = edge

        if request.include_correlations and request.correlation_limit:
            if entity_rows:
                self._add_correlation_edges(
                    edges,
                    entity_rows,
                    limit=request.correlation_limit,
                )
            remaining = request.correlation_limit - self._correlation_edge_count(edges)
            if remaining > 0 and request.include_vector_correlations:
                vector_limit = min(remaining, max(1, int(request.correlation_limit * 0.7)))
                await self._add_vector_correlation_edges(
                    edges,
                    memories,
                    request=request,
                    limit=vector_limit,
                    max_degree=request.max_correlation_degree,
                )
            remaining = request.correlation_limit - self._correlation_edge_count(edges)
            if remaining > 0:
                self._add_facet_correlation_edges(
                    edges,
                    memories,
                    limit=remaining,
                    max_degree=request.max_correlation_degree,
                )
            self._prune_correlation_edges(
                edges,
                limit=request.correlation_limit,
                max_degree=request.max_correlation_degree,
            )
            self._annotate_graph_insights(nodes, edges)

        return GraphResponse(
            query=request.query,
            nodes=sorted(nodes.values(), key=lambda item: (item.node_type, item.label)),
            edges=sorted(edges.values(), key=lambda item: (item.edge_type, item.label or "")),
            memory_count=len(memories),
            entity_count=len(entity_ids),
        )

    async def health(self) -> dict[str, bool]:
        database_ok = False
        qdrant_ok = False
        async with self._session_factory() as session:
            await session.execute(text("select 1"))
            database_ok = True
        qdrant_ok = await self._vector_store.health()
        return {"database": database_ok, "qdrant": qdrant_ok}

    async def _safe_vector_search(self, request: SearchRequest):
        filters: dict[str, Any] = {"status": request.filters.statuses}
        if request.filters.memory_types:
            filters["memory_type"] = request.filters.memory_types
        try:
            vector = (await self._embeddings.embed([request.query]))[0]
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

    async def _graph_memories(self, request: GraphRequest) -> list[Memory]:
        if request.memory_ids:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(Memory)
                    .where(Memory.id.in_(request.memory_ids))
                    .where(Memory.status.in_(request.filters.statuses))
                )
                memories = list(result.scalars().all())
            ordered_ids = {memory_id: index for index, memory_id in enumerate(request.memory_ids)}
            return sorted(memories, key=lambda item: ordered_ids.get(item.id, len(ordered_ids)))

        if request.query:
            search = await self.search(
                SearchRequest(
                    query=request.query,
                    limit=min(request.limit, 100),
                    filters=request.filters,
                )
            )
            memory_ids = [hit.memory.id for hit in search.hits]
            memories = await self._load_memories(memory_ids)
            ordered_ids = {memory_id: index for index, memory_id in enumerate(memory_ids)}
            return sorted(memories, key=lambda item: ordered_ids.get(item.id, len(ordered_ids)))

        async with self._session_factory() as session:
            result = await session.execute(
                self._filtered_memory_select(request.filters).limit(request.limit)
            )
            return list(result.scalars().all())

    async def _graph_memory_entities(
        self,
        memory_ids: set[uuid.UUID],
    ) -> list[tuple[uuid.UUID, str, Entity]]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MemoryEntity.memory_id, MemoryEntity.role, Entity)
                .join(Entity, Entity.id == MemoryEntity.entity_id)
                .where(MemoryEntity.memory_id.in_(memory_ids))
            )
            return [(row[0], row[1], row[2]) for row in result.all()]

    async def _graph_relations(self, entity_ids: set[uuid.UUID]) -> list[Relation]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Relation)
                .where(Relation.from_entity_id.in_(entity_ids))
                .where(Relation.to_entity_id.in_(entity_ids))
                .limit(1000)
            )
            return list(result.scalars().all())

    async def _graph_memory_links(self, memory_ids: set[uuid.UUID]) -> list[MemoryLink]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MemoryLink)
                .where(MemoryLink.from_memory_id.in_(memory_ids))
                .where(MemoryLink.to_memory_id.in_(memory_ids))
                .limit(2000)
            )
            return list(result.scalars().all())

    def _add_correlation_edges(
        self,
        edges: dict[str, GraphEdge],
        entity_rows: list[tuple[uuid.UUID, str, Entity]],
        *,
        limit: int,
    ) -> None:
        memories_by_entity: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        entity_names: dict[uuid.UUID, str] = {}
        for memory_id, _, entity in entity_rows:
            memories_by_entity[entity.id].add(memory_id)
            entity_names[entity.id] = entity.name

        shared_entities_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
        for entity_id, entity_memory_ids in memories_by_entity.items():
            if len(entity_memory_ids) < 2:
                continue
            for left, right in combinations(sorted(entity_memory_ids, key=str), 2):
                pair = (str(left), str(right))
                shared_entities_by_pair[pair].add(entity_names[entity_id])

        for index, ((left, right), shared_entities) in enumerate(
            sorted(
                shared_entities_by_pair.items(),
                key=lambda item: (-len(item[1]), item[0]),
            )
        ):
            if index >= limit:
                break
            shared = sorted(shared_entities)
            edge = GraphEdge(
                id=f"correlation:{left}:{right}",
                source=f"memory:{left}",
                target=f"memory:{right}",
                edge_type="correlation",
                label="shared_entity",
                weight=min(1.0, 0.35 + len(shared) * 0.15),
                confidence=min(1.0, 0.5 + len(shared) * 0.1),
                metadata={"reasons": ["shared_entity"], "shared_entities": shared[:20]},
            )
            edges[edge.id] = edge

    async def _add_vector_correlation_edges(
        self,
        edges: dict[str, GraphEdge],
        memories: list[Memory],
        *,
        request: GraphRequest,
        limit: int,
        max_degree: int,
    ) -> None:
        candidate_memories = [
            memory for memory in memories if not self._is_low_signal_correlation_memory(memory)
        ]
        memory_by_id = {memory.id: memory for memory in candidate_memories}
        if len(candidate_memories) < 2:
            return

        try:
            vectors = await self._embeddings.embed(
                [self._embedding_text(memory) for memory in candidate_memories]
            )
        except Exception:
            return

        filters: dict[str, Any] = {"status": request.filters.statuses}
        if request.filters.memory_types:
            filters["memory_type"] = request.filters.memory_types

        vector_candidates: dict[tuple[str, str], float] = {}
        search_limit = min(
            50,
            max(request.vector_neighbors_per_memory * 4, request.vector_neighbors_per_memory + 4),
        )
        for memory, vector in zip(candidate_memories, vectors, strict=False):
            try:
                hits = await self._vector_store.search(
                    vector=vector,
                    limit=search_limit,
                    filters=filters,
                )
            except Exception as exc:
                LOGGER.warning(
                    "graph.vector_correlation_search_failed",
                    memory_id=str(memory.id),
                    error=str(exc),
                )
                continue

            accepted = 0
            for hit in hits:
                if hit.memory_id == memory.id or hit.memory_id not in memory_by_id:
                    continue
                if hit.score < request.vector_similarity_threshold:
                    continue
                left, right = sorted((str(memory.id), str(hit.memory_id)))
                pair = (left, right)
                vector_candidates[pair] = max(vector_candidates.get(pair, 0.0), hit.score)
                accepted += 1
                if accepted >= request.vector_neighbors_per_memory:
                    break

        degree_by_memory = self._correlation_degree_by_memory(edges)
        added = 0
        for (left, right), similarity in sorted(
            vector_candidates.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            if added >= limit:
                break
            edge_id = f"correlation:{left}:{right}"
            if edge_id not in edges and (
                degree_by_memory[left] >= max_degree or degree_by_memory[right] >= max_degree
            ):
                continue
            is_new = self._upsert_vector_correlation_edge(edges, left, right, similarity)
            if is_new:
                degree_by_memory[left] += 1
                degree_by_memory[right] += 1
                added += 1

    def _upsert_vector_correlation_edge(
        self,
        edges: dict[str, GraphEdge],
        left: str,
        right: str,
        similarity: float,
    ) -> bool:
        edge_id = f"correlation:{left}:{right}"
        score = similarity * 10.0
        if edge_id in edges:
            edge = edges[edge_id]
            self._add_edge_reason(edge, "vector_neighbor")
            edge.label = "semantic_neighbor"
            edge.weight = max(edge.weight, min(1.0, 0.25 + similarity * 0.75))
            edge.confidence = max(edge.confidence or 0.0, min(1.0, similarity))
            edge.metadata["vector_similarity"] = round(similarity, 6)
            edge.metadata["score"] = round(max(self._correlation_edge_rank(edge), score), 4)
            return False

        edges[edge_id] = GraphEdge(
            id=edge_id,
            source=f"memory:{left}",
            target=f"memory:{right}",
            edge_type="correlation",
            label="vector_neighbor",
            weight=min(1.0, 0.25 + similarity * 0.75),
            confidence=min(1.0, similarity),
            metadata={
                "reasons": ["vector_neighbor"],
                "vector_similarity": round(similarity, 6),
                "score": round(score, 4),
            },
        )
        return True

    def _add_facet_correlation_edges(
        self,
        edges: dict[str, GraphEdge],
        memories: list[Memory],
        *,
        limit: int,
        max_degree: int | None = None,
    ) -> None:
        facets_by_memory: dict[uuid.UUID, dict[str, float]] = {
            memory.id: self._memory_correlation_facets(memory) for memory in memories
        }
        memories_by_facet: dict[str, set[uuid.UUID]] = defaultdict(set)
        for memory_id, facets in facets_by_memory.items():
            for facet in facets:
                memories_by_facet[facet].add(memory_id)

        pair_facets: dict[tuple[str, str], set[str]] = defaultdict(set)
        pair_facet_scores: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        pair_facet_weights: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        memory_count = max(1, len(memories))
        for facet, memory_ids in memories_by_facet.items():
            if facet.startswith("context:"):
                continue
            facet_frequency = len(memory_ids)
            if facet_frequency < 2 or facet_frequency > self._max_correlation_facet_frequency(
                facet, memory_count
            ):
                continue
            facet_idf = math.log((memory_count + 1) / (facet_frequency + 0.5)) + 1.0
            for left, right in combinations(sorted(memory_ids, key=str), 2):
                pair = (str(left), str(right))
                shared_weight = min(
                    facets_by_memory[left].get(facet, 0.0),
                    facets_by_memory[right].get(facet, 0.0),
                )
                contribution = shared_weight * facet_idf
                pair_facets[pair].add(facet)
                pair_facet_scores[pair][facet] = contribution
                pair_facet_weights[pair][facet] = shared_weight

        candidates: list[tuple[str, str, float, list[tuple[str, float]]]] = []
        for (left, right), facet_scores in pair_facet_scores.items():
            ranked_scored_facets = sorted(
                facet_scores.items(),
                key=lambda item: (-item[1], item[0]),
            )
            score = sum(facet_score for _, facet_score in ranked_scored_facets[:6])
            facets = pair_facets[(left, right)]
            if not self._is_meaningful_correlation(
                score,
                facets,
                pair_facet_weights[(left, right)],
            ):
                continue
            candidates.append((left, right, score, ranked_scored_facets))

        degree_by_memory = self._correlation_degree_by_memory(edges)
        added = 0
        for left, right, score, ranked_scored_facets in sorted(
            candidates,
            key=lambda item: (-item[2], item[0], item[1]),
        ):
            if added >= limit:
                break
            if max_degree is not None and (
                degree_by_memory[left] >= max_degree or degree_by_memory[right] >= max_degree
            ):
                continue
            edge_id = f"correlation:{left}:{right}"
            ranked_facets = [facet for facet, _ in ranked_scored_facets]
            if edge_id in edges:
                self._merge_facet_correlation_edge(edges[edge_id], ranked_facets, score)
                continue
            edges[edge_id] = GraphEdge(
                id=edge_id,
                source=f"memory:{left}",
                target=f"memory:{right}",
                edge_type="correlation",
                label="semantic_overlap",
                weight=min(1.0, 0.25 + score * 0.12),
                confidence=min(1.0, 0.35 + score * 0.12),
                metadata={
                    "reasons": ["semantic_overlap"],
                    "shared_facets": ranked_facets[:20],
                    "score": round(score, 4),
                },
            )
            degree_by_memory[left] += 1
            degree_by_memory[right] += 1
            added += 1

    def _merge_facet_correlation_edge(
        self,
        edge: GraphEdge,
        ranked_facets: list[str],
        score: float,
    ) -> None:
        self._add_edge_reason(edge, "semantic_overlap")
        if edge.label == "vector_neighbor":
            edge.label = "semantic_neighbor"
        existing_facets = edge.metadata.get("shared_facets")
        if not isinstance(existing_facets, list):
            existing_facets = []
        merged_facets = list(dict.fromkeys([*existing_facets, *ranked_facets]))
        edge.metadata["shared_facets"] = merged_facets[:20]
        edge.metadata["score"] = round(max(self._correlation_edge_rank(edge), score), 4)
        edge.weight = max(edge.weight, min(1.0, 0.25 + score * 0.12))
        edge.confidence = max(edge.confidence or 0.0, min(1.0, 0.35 + score * 0.12))

    def _add_edge_reason(self, edge: GraphEdge, reason: str) -> None:
        reasons = edge.metadata.get("reasons")
        if not isinstance(reasons, list):
            reasons = []
        edge.metadata["reasons"] = sorted({*reasons, reason})

    def _memory_correlation_facets(self, memory: Memory) -> dict[str, float]:
        if self._is_low_signal_correlation_memory(memory):
            return {}

        facets: dict[str, float] = {}
        title_text = memory.title or ""
        metadata = memory.metadata_ or {}
        metadata_text = " ".join(str(value) for value in metadata.values() if value)
        content_text = memory.content[:6000]

        for term in self._correlation_terms(title_text):
            facets[f"term:{term}"] = max(facets.get(f"term:{term}", 0.0), 1.25)
        for phrase in self._correlation_phrases(title_text):
            facets[f"phrase:{phrase}"] = max(facets.get(f"phrase:{phrase}", 0.0), 1.5)
        for term in self._correlation_terms(metadata_text):
            facets[f"term:{term}"] = max(facets.get(f"term:{term}", 0.0), 0.95)
        for phrase in self._correlation_phrases(metadata_text):
            facets[f"phrase:{phrase}"] = max(facets.get(f"phrase:{phrase}", 0.0), 1.15)
        for term in self._correlation_terms(content_text):
            facets[f"term:{term}"] = max(facets.get(f"term:{term}", 0.0), 0.35)
        for phrase in self._correlation_phrases(content_text[:2000]):
            facets[f"phrase:{phrase}"] = max(facets.get(f"phrase:{phrase}", 0.0), 0.45)

        for key, value in memory.scope.items():
            if (
                key not in {"project", "catalog", "source"}
                and isinstance(value, str | int | float | bool)
                and str(value).strip()
            ):
                facets[f"context:{key}={normalize_name(str(value))}"] = 0.25
        for tag in memory.tags:
            if self._is_generic_correlation_tag(tag):
                continue
            normalized_tag = normalize_name(tag.replace(":", " "))
            if tag.startswith(("library:", "source-type:")):
                facets[f"context:{normalized_tag}"] = 0.25
            else:
                facets[f"tag:{normalized_tag}"] = 0.55
                for term in self._correlation_terms(normalized_tag):
                    facets[f"term:{term}"] = max(facets.get(f"term:{term}", 0.0), 0.5)
        if memory.source_type and memory.source_type not in {"manual", "file-import"}:
            facets[f"context:source_type={normalize_name(memory.source_type)}"] = 0.15
        return facets

    def _is_generic_correlation_tag(self, tag: str) -> bool:
        return tag in {"imported", "file-memory", "skill", "asset:skill"} or tag.startswith("ext:")

    def _is_low_signal_correlation_memory(self, memory: Memory) -> bool:
        source_ref = (memory.source_ref or "").lower().replace("\\", "/")
        if source_ref.endswith("/library.json"):
            return True
        return normalize_name(memory.title or "") == "imported memory library"

    def _max_correlation_facet_frequency(self, facet: str, memory_count: int) -> int:
        if facet.startswith("context:"):
            return 0
        if facet.startswith("phrase:"):
            return min(10, max(3, memory_count // 8))
        if facet.startswith("term:"):
            return min(12, max(3, memory_count // 8))
        return min(8, max(2, memory_count // 12))

    def _is_meaningful_correlation(
        self,
        score: float,
        facets: set[str],
        facet_weights: dict[str, float],
    ) -> bool:
        specific = [
            facet
            for facet in facets
            if facet.startswith(("term:", "phrase:", "tag:"))
            and not facet.startswith("tag:library")
        ]
        anchors = [facet for facet in specific if facet_weights.get(facet, 0.0) >= 0.9]
        phrase_count = sum(1 for facet in specific if facet.startswith("phrase:"))
        if len(anchors) >= 2 and score >= 2.1:
            return True
        if len(anchors) >= 1 and len(specific) >= 3 and score >= 3.1:
            return True
        return phrase_count >= 2 and score >= 4.2

    def _correlation_terms(self, text: str, *, limit: int = 30) -> list[str]:
        normalized = normalize_name(text)
        terms: list[str] = []
        seen: set[str] = set()
        for raw in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", normalized):
            for term in re.split(r"[_-]+", raw):
                if not self._is_correlation_term(term) or term in seen:
                    continue
                seen.add(term)
                terms.append(term)
                if len(terms) >= limit:
                    return terms
        return terms

    def _correlation_phrases(self, text: str, *, limit: int = 16) -> list[str]:
        terms = self._correlation_terms(text, limit=80)
        phrases: list[str] = []
        seen: set[str] = set()
        for left, right in zip(terms, terms[1:], strict=False):
            if left == right:
                continue
            phrase = f"{left} {right}"
            if phrase in seen:
                continue
            seen.add(phrase)
            phrases.append(phrase)
            if len(phrases) >= limit:
                return phrases
        return phrases

    def _is_correlation_term(self, term: str) -> bool:
        return (
            len(term) >= 4
            and not term.isdigit()
            and term not in CORRELATION_STOPWORDS
            and not term.startswith("chunk")
        )

    def _prune_correlation_edges(
        self,
        edges: dict[str, GraphEdge],
        *,
        limit: int,
        max_degree: int,
    ) -> None:
        correlation_edges = [edge for edge in edges.values() if edge.edge_type == "correlation"]
        kept: set[str] = set()
        degree_by_memory: defaultdict[str, int] = defaultdict(int)
        for edge in sorted(
            correlation_edges,
            key=lambda item: (-self._correlation_edge_rank(item), item.id),
        ):
            if len(kept) >= limit:
                break
            source = self._correlation_node_memory_key(edge.source)
            target = self._correlation_node_memory_key(edge.target)
            if degree_by_memory[source] >= max_degree or degree_by_memory[target] >= max_degree:
                continue
            kept.add(edge.id)
            degree_by_memory[source] += 1
            degree_by_memory[target] += 1

        for edge in correlation_edges:
            if edge.id not in kept:
                edges.pop(edge.id, None)

    def _correlation_degree_by_memory(
        self,
        edges: dict[str, GraphEdge],
    ) -> defaultdict[str, int]:
        degree_by_memory: defaultdict[str, int] = defaultdict(int)
        for edge in edges.values():
            if edge.edge_type != "correlation":
                continue
            degree_by_memory[self._correlation_node_memory_key(edge.source)] += 1
            degree_by_memory[self._correlation_node_memory_key(edge.target)] += 1
        return degree_by_memory

    def _correlation_node_memory_key(self, node_id: str) -> str:
        if node_id.startswith("memory:"):
            return node_id.removeprefix("memory:")
        return node_id

    def _correlation_edge_rank(self, edge: GraphEdge) -> float:
        metadata_score = edge.metadata.get("score")
        if isinstance(metadata_score, int | float):
            return float(metadata_score)
        shared_entities = edge.metadata.get("shared_entities")
        if isinstance(shared_entities, list):
            return len(shared_entities) * 1.5 + edge.weight
        return edge.weight + (edge.confidence or 0.0)

    def _annotate_graph_insights(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[str, GraphEdge],
    ) -> None:
        stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "degree": 0,
                "vector_degree": 0,
                "semantic_degree": 0,
                "centrality": 0.0,
                "neighbors": set(),
            }
        )
        for edge in edges.values():
            if edge.edge_type != "correlation":
                continue
            if not edge.source.startswith("memory:") or not edge.target.startswith("memory:"):
                continue
            rank = self._correlation_edge_rank(edge)
            reasons = edge.metadata.get("reasons")
            reason_set = set(reasons) if isinstance(reasons, list) else set()
            for node_id, other_id in ((edge.source, edge.target), (edge.target, edge.source)):
                stats[node_id]["degree"] += 1
                stats[node_id]["centrality"] += rank
                stats[node_id]["neighbors"].add(other_id)
                if "vector_neighbor" in reason_set:
                    stats[node_id]["vector_degree"] += 1
                if "semantic_overlap" in reason_set or "shared_entity" in reason_set:
                    stats[node_id]["semantic_degree"] += 1

        if not stats:
            return

        ranked = sorted(
            stats.items(),
            key=lambda item: (-item[1]["centrality"], item[0]),
        )
        centroid_count = max(1, min(8, len(ranked) // 10 or 1))
        centroid_ids = {
            node_id for node_id, node_stats in ranked[:centroid_count] if node_stats["degree"] >= 3
        }
        max_centrality = max(float(item["centrality"]) for item in stats.values()) or 1.0

        for node_id, node_stats in stats.items():
            node = nodes.get(node_id)
            if node is None:
                continue
            centrality = float(node_stats["centrality"])
            graph_metadata = {
                "degree": node_stats["degree"],
                "vector_degree": node_stats["vector_degree"],
                "semantic_degree": node_stats["semantic_degree"],
                "centrality": round(centrality, 4),
                "centrality_normalized": round(centrality / max_centrality, 4),
            }
            if node_id in centroid_ids:
                graph_metadata["role"] = "centroid_candidate"
            elif (
                node_stats["vector_degree"] >= 2
                and node_stats["semantic_degree"] < node_stats["degree"]
            ):
                graph_metadata["role"] = "grouping_opportunity"

            node.metadata["graph"] = graph_metadata
            node.weight = max(
                node.weight,
                1.0 + min(1.25, graph_metadata["centrality_normalized"]),
            )

    def _correlation_edge_count(self, edges: dict[str, GraphEdge]) -> int:
        return sum(1 for edge in edges.values() if edge.edge_type == "correlation")

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

    def _memory_graph_node(self, memory: Memory) -> GraphNode:
        return GraphNode(
            id=self._memory_node_id(memory.id),
            node_type="memory",
            label=self._memory_label(memory),
            subtype=memory.memory_type,
            summary=self._preview(memory.content),
            weight=max(0.35, memory.confidence),
            metadata={
                "memory_id": str(memory.id),
                "memory_type": memory.memory_type,
                "status": memory.status,
                "tags": memory.tags,
                "scope": memory.scope,
                "confidence": memory.confidence,
                "source_type": memory.source_type,
                "source_ref": memory.source_ref,
                "created_at": memory.created_at.isoformat() if memory.created_at else None,
                "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
            },
        )

    def _entity_graph_node(self, entity: Entity) -> GraphNode:
        return GraphNode(
            id=self._entity_node_id(entity.id),
            node_type="entity",
            label=entity.name,
            subtype=entity.entity_type,
            summary=entity.summary,
            weight=0.7,
            metadata={
                "entity_id": str(entity.id),
                "entity_type": entity.entity_type,
                "normalized_name": entity.normalized_name,
                "metadata": entity.metadata_,
            },
        )

    def _memory_label(self, memory: Memory) -> str:
        if memory.title:
            return self._shorten(memory.title, 80)
        return self._shorten(self._preview(memory.content), 80)

    def _preview(self, value: str, max_length: int = 280) -> str:
        return self._shorten(" ".join(value.split()), max_length)

    def _shorten(self, value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value
        return value[: max_length - 3].rstrip() + "..."

    def _memory_node_id(self, memory_id: uuid.UUID) -> str:
        return f"memory:{memory_id}"

    def _entity_node_id(self, entity_id: uuid.UUID) -> str:
        return f"entity:{entity_id}"
