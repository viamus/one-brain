from __future__ import annotations

import math
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from hashlib import sha256
from itertools import combinations
from pathlib import PurePosixPath
from typing import Any

import structlog
from onebrain_infra.embeddings import EmbeddingProvider
from onebrain_infra.models import (
    AuditEvent,
    Entity,
    Memory,
    MemoryEntity,
    MemoryLink,
    Relation,
)
from onebrain_infra.vector_store import MemoryVectorStore
from sqlalchemy import Select, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from onebrain_core.common.config import Settings
from onebrain_core.common.text import (
    content_hash,
    estimate_tokens,
    extract_heuristic_entities,
    normalize_name,
    scope_matches,
)
from onebrain_core.contracts.schemas import (
    ContextMemory,
    ContextPack,
    ContextRequest,
    CorrelationHit,
    CorrelationRequest,
    CorrelationResponse,
    EntityInput,
    GraphAggregationItem,
    GraphAggregationRequest,
    GraphAggregationResponse,
    GraphEdge,
    GraphGroupingOpportunity,
    GraphNode,
    GraphRequest,
    GraphResponse,
    MemoryCreate,
    MemoryOut,
    SearchFilters,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SourceRef,
)

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
    "ambevtech",
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
    "body",
    "branch",
    "browser",
    "cada",
    "caso",
    "catalog",
    "codex",
    "com",
    "como",
    "configura",
    "commit",
    "content",
    "context",
    "data",
    "description",
    "details",
    "deve",
    "does",
    "document",
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
    "fonte",
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
    "manifest",
    "meta",
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
    "options",
    "padr",
    "para",
    "pela",
    "pelo",
    "por",
    "private",
    "project",
    "que",
    "query",
    "read",
    "readme",
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
    "target",
    "the",
    "this",
    "text",
    "topic",
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

GENERIC_MEMORY_TITLES = {
    "body",
    "document",
    "document body",
    "manifest",
    "readme",
}


class OneBrainService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        embeddings: EmbeddingProvider,
        vector_store: MemoryVectorStore,
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
        related_hits: list[SearchHit] = []
        if request.include_related and response.hits:
            seed_ids = {hit.memory.id for hit in response.hits[:12]}
            try:
                related_hits = await self._graph_guided_related_memories(
                    seed_ids,
                    request.scope,
                    limit=20,
                )
            except Exception as exc:
                LOGGER.warning(
                    "context.graph_guided_related_failed",
                    seed_count=len(seed_ids),
                    error=str(exc),
                )
                related_hits = await self._related_memories(seed_ids, request.scope, limit=20)
        direct_budget_chars = budget_chars
        if related_hits:
            related_reserve_chars = min(
                int(budget_chars * 0.28),
                sum(len(hit.memory.content) + 120 for hit in related_hits),
            )
            direct_budget_chars = max(0, budget_chars - related_reserve_chars)

        for hit in response.hits:
            item = self._context_memory(hit)
            item_chars = len(item.content) + 120
            if used_chars + item_chars > direct_budget_chars:
                omitted += 1
                continue
            used_chars += item_chars
            used_ids.add(item.id)
            if item.memory_type == "rule" and request.include_rules:
                rules.append(item)
            else:
                memories.append(item)

        if related_hits:
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
        candidate_memories = await self._graph_memories(request)
        memories = [memory for memory in candidate_memories if self._is_graph_memory(memory)]
        omitted = len(candidate_memories) - len(memories)
        memory_ids = {memory.id for memory in memories}
        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}

        for memory in memories:
            nodes[self._memory_node_id(memory.id)] = self._memory_graph_node(memory)

        entity_rows: list[tuple[uuid.UUID, str, Entity]] = []
        if memory_ids and (
            request.include_entities or request.include_relations or request.include_correlations
        ):
            entity_rows = [
                row
                for row in await self._graph_memory_entities(memory_ids)
                if self._is_graph_entity(row[2])
            ]

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

        grouping_opportunities: list[GraphGroupingOpportunity] = []
        if request.include_grouping_opportunities and request.include_correlations:
            grouping_opportunities = self._build_grouping_opportunities(
                nodes,
                edges,
                limit=request.grouping_limit,
                min_size=request.grouping_min_size,
            )
            self._add_grouping_opportunity_nodes(nodes, edges, grouping_opportunities)

        return GraphResponse(
            query=request.query,
            nodes=sorted(nodes.values(), key=lambda item: (item.node_type, item.label)),
            edges=sorted(edges.values(), key=lambda item: (item.edge_type, item.label or "")),
            memory_count=len(memories),
            entity_count=len(entity_ids),
            omitted=omitted,
            grouping_opportunities=grouping_opportunities,
        )

    async def materialize_grouping_opportunities(
        self,
        request: GraphAggregationRequest,
        *,
        actor: str = "onebrain-jobs",
    ) -> GraphAggregationResponse:
        graph_request = request.graph.model_copy(
            update={
                "include_correlations": True,
                "include_grouping_opportunities": True,
                "grouping_min_size": max(
                    request.graph.grouping_min_size,
                    request.min_member_count,
                ),
            }
        )
        graph = await self.build_graph(graph_request)

        items: list[GraphAggregationItem] = []
        created = 0
        existing = 0
        skipped = 0
        for opportunity in graph.grouping_opportunities:
            if opportunity.score < request.min_score:
                skipped += 1
                items.append(
                    self._grouping_aggregation_item(
                        opportunity,
                        status="skipped",
                        reason="below_min_score",
                    )
                )
                continue

            member_ids = self._grouping_member_ids(opportunity)
            member_memories = [
                memory
                for memory in await self._load_memories(member_ids)
                if not self._is_graph_aggregate_memory(memory)
            ]
            member_memories.sort(key=lambda memory: (memory.title or "", str(memory.id)))
            if len(member_memories) < request.min_member_count:
                skipped += 1
                items.append(
                    self._grouping_aggregation_item(
                        opportunity,
                        status="skipped",
                        reason="not_enough_source_members",
                        member_count=len(member_memories),
                    )
                )
                continue

            source_ref = self._grouping_aggregate_source_ref(member_memories)
            existing_memory = await self._active_memory_by_source_ref(source_ref)
            if existing_memory is not None:
                existing += 1
                items.append(
                    self._grouping_aggregation_item(
                        opportunity,
                        status="existing",
                        reason="already_materialized",
                        memory_id=existing_memory.id,
                        source_ref=source_ref,
                        member_count=len(member_memories),
                    )
                )
                continue

            if request.dry_run:
                items.append(
                    self._grouping_aggregation_item(
                        opportunity,
                        status="dry_run",
                        source_ref=source_ref,
                        member_count=len(member_memories),
                    )
                )
                continue

            payload = self._grouping_aggregate_memory_create(
                opportunity,
                member_memories,
                request,
                source_ref=source_ref,
            )
            aggregate_memory = await self.capture_memory(payload, actor=actor)
            links_created = 0
            for index, member in enumerate(member_memories):
                await self.link_memories(
                    from_memory_id=aggregate_memory.id,
                    to_memory_id=member.id,
                    link_type=request.link_type,
                    confidence=max(0.5, opportunity.cohesion),
                    order_index=index,
                    evidence=opportunity.summary,
                    metadata={
                        "aggregation_kind": "graph_grouping_opportunity",
                        "opportunity_id": opportunity.id,
                        "opportunity_score": opportunity.score,
                    },
                    actor=actor,
                )
                links_created += 1
            created += 1
            items.append(
                self._grouping_aggregation_item(
                    opportunity,
                    status="created",
                    memory_id=aggregate_memory.id,
                    source_ref=source_ref,
                    member_count=len(member_memories),
                    links_created=links_created,
                )
            )

        return GraphAggregationResponse(
            dry_run=request.dry_run,
            graph_memory_count=graph.memory_count,
            scanned=len(graph.grouping_opportunities),
            created=created,
            existing=existing,
            skipped=skipped,
            items=items,
        )

    async def health(self) -> dict[str, bool]:
        database_ok = False
        vector_store_ok = False
        async with self._session_factory() as session:
            await session.execute(text("select 1"))
            database_ok = True
        vector_store_ok = await self._vector_store.health()
        return {"database": database_ok, "vector_store": vector_store_ok}

    async def _safe_vector_search(self, request: SearchRequest):
        filters: dict[str, Any] = {"status": request.filters.statuses}
        if request.filters.memory_types:
            filters["memory_type"] = request.filters.memory_types
        if request.filters.tags:
            filters["tags"] = request.filters.tags
        if request.filters.scope:
            for key, value in request.filters.scope.items():
                filters[f"scope.{key}"] = value
        try:
            vector = (await self._embeddings.embed([request.query]))[0]
            return await self._vector_store.search(
                vector=vector,
                limit=request.limit * 3,
                filters=filters,
            )
        except Exception as exc:
            LOGGER.warning(
                "search.vector_failed",
                query=request.query,
                error=str(exc),
            )
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

    async def _graph_guided_related_memories(
        self,
        memory_ids: set[uuid.UUID],
        scope: dict[str, Any],
        limit: int,
    ) -> list[SearchHit]:
        seed_memories = await self._load_memories(memory_ids)
        if not seed_memories:
            return []

        candidate_scores: defaultdict[uuid.UUID, float] = defaultdict(float)
        candidate_reasons: defaultdict[uuid.UUID, set[str]] = defaultdict(set)

        for hit in await self._related_memories(memory_ids, scope, limit=limit * 2):
            candidate_scores[hit.memory.id] = max(candidate_scores[hit.memory.id], hit.score)
            candidate_reasons[hit.memory.id].update(hit.reasons)
            candidate_reasons[hit.memory.id].add("graph_shared_entity")

        for hit in await self._vector_neighbors_for_memories(seed_memories, scope, limit=limit * 2):
            if hit.memory.id in memory_ids:
                continue
            candidate_scores[hit.memory.id] = max(candidate_scores[hit.memory.id], hit.score)
            candidate_reasons[hit.memory.id].update(hit.reasons)

        candidate_memories = await self._load_memories(candidate_scores.keys())
        if not candidate_memories:
            return []

        scoped_candidates = [
            memory
            for memory in candidate_memories
            if memory.id not in memory_ids and scope_matches(memory.scope, scope)
        ]
        candidate_by_id = {memory.id: memory for memory in scoped_candidates}
        if not candidate_by_id:
            return []

        graph_memories = [*seed_memories, *scoped_candidates]
        graph_memory_ids = {memory.id for memory in graph_memories}
        nodes = {
            self._memory_node_id(memory.id): self._memory_graph_node(memory)
            for memory in graph_memories
            if self._is_graph_memory(memory)
        }
        edges: dict[str, GraphEdge] = {}

        entity_rows = [
            row
            for row in await self._graph_memory_entities(graph_memory_ids)
            if self._is_graph_entity(row[2])
        ]
        if entity_rows:
            self._add_correlation_edges(edges, entity_rows, limit=limit * 12)
        self._add_facet_correlation_edges(
            edges,
            graph_memories,
            limit=limit * 12,
            max_degree=12,
        )

        seed_node_ids = {self._memory_node_id(memory_id) for memory_id in memory_ids}
        for edge in edges.values():
            candidate_node_id = self._edge_candidate_connected_to_seed(edge, seed_node_ids)
            if candidate_node_id is None:
                continue
            candidate_id = uuid.UUID(candidate_node_id.removeprefix("memory:"))
            if candidate_id not in candidate_by_id:
                continue
            rank = self._correlation_edge_rank(edge)
            candidate_scores[candidate_id] = max(
                candidate_scores[candidate_id], min(1.0, rank / 10)
            )
            candidate_reasons[candidate_id].add("graph_correlation")
            raw_reasons = edge.metadata.get("reasons")
            if isinstance(raw_reasons, list):
                candidate_reasons[candidate_id].update(str(reason) for reason in raw_reasons)

        opportunities = self._build_grouping_opportunities(
            nodes,
            edges,
            limit=6,
            min_size=3,
        )
        for opportunity in opportunities:
            if not seed_node_ids.intersection(opportunity.member_node_ids):
                continue
            for member_node_id in opportunity.member_node_ids:
                if not member_node_id.startswith("memory:"):
                    continue
                member_id = uuid.UUID(member_node_id.removeprefix("memory:"))
                if member_id not in candidate_by_id:
                    continue
                group_boost = min(0.18, opportunity.score / 80)
                candidate_scores[member_id] = min(1.0, candidate_scores[member_id] + group_boost)
                candidate_reasons[member_id].add("graph_grouping_opportunity")

        hits = [
            SearchHit(
                memory=MemoryOut.model_validate(memory),
                score=round(candidate_scores[memory.id], 6),
                reasons=sorted(candidate_reasons[memory.id]),
            )
            for memory in candidate_by_id.values()
        ]
        hits.sort(key=lambda item: (-item.score, item.memory.title or "", str(item.memory.id)))
        return hits[:limit]

    async def _vector_neighbors_for_memories(
        self,
        memories: list[Memory],
        scope: dict[str, Any],
        *,
        limit: int,
    ) -> list[SearchHit]:
        try:
            vectors = await self._embeddings.embed(
                [self._embedding_text(memory) for memory in memories]
            )
        except Exception as exc:
            LOGGER.warning(
                "context.graph_vector_neighbor_embedding_failed",
                memory_count=len(memories),
                error=str(exc),
            )
            return []

        scores: defaultdict[uuid.UUID, float] = defaultdict(float)
        filters: dict[str, Any] = {"status": ["active"]}
        for memory, vector in zip(memories, vectors, strict=False):
            try:
                hits = await self._vector_store.search(vector=vector, limit=limit, filters=filters)
            except Exception as exc:
                LOGGER.warning(
                    "context.graph_vector_neighbor_search_failed",
                    memory_id=str(memory.id),
                    error=str(exc),
                )
                continue
            for hit in hits:
                if hit.memory_id == memory.id:
                    continue
                scores[hit.memory_id] = max(scores[hit.memory_id], min(1.0, hit.score))

        loaded = await self._load_memories(scores.keys())
        return [
            SearchHit(
                memory=MemoryOut.model_validate(memory),
                score=round(scores[memory.id], 6),
                reasons=["graph_vector_neighbor"],
            )
            for memory in loaded
            if scope_matches(memory.scope, scope)
        ]

    def _edge_candidate_connected_to_seed(
        self,
        edge: GraphEdge,
        seed_node_ids: set[str],
    ) -> str | None:
        source_is_seed = edge.source in seed_node_ids
        target_is_seed = edge.target in seed_node_ids
        if source_is_seed and not target_is_seed:
            return edge.target
        if target_is_seed and not source_is_seed:
            return edge.source
        return None

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

    def _is_graph_memory(self, memory: Memory) -> bool:
        metadata = memory.metadata_ or {}
        if "ingestion:child" in memory.tags:
            return False
        if metadata.get("ingestion_item_type") == "section":
            return False
        return True

    def _is_graph_entity(self, entity: Entity) -> bool:
        return entity.entity_type != "source_document"

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

    def _build_grouping_opportunities(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[str, GraphEdge],
        *,
        limit: int,
        min_size: int,
    ) -> list[GraphGroupingOpportunity]:
        if limit <= 0:
            return []

        correlation_edges = [
            edge
            for edge in edges.values()
            if edge.edge_type == "correlation"
            and edge.source.startswith("memory:")
            and edge.target.startswith("memory:")
            and edge.source in nodes
            and edge.target in nodes
        ]
        if not correlation_edges:
            return []

        adjacency: dict[str, list[GraphEdge]] = defaultdict(list)
        for edge in correlation_edges:
            adjacency[edge.source].append(edge)
            adjacency[edge.target].append(edge)

        candidates: list[GraphGroupingOpportunity] = []
        for seed, seed_edges in adjacency.items():
            if len(seed_edges) + 1 < min_size:
                continue
            ranked_edges = sorted(
                seed_edges,
                key=lambda item: (-self._correlation_edge_rank(item), item.id),
            )
            member_ids = {seed}
            max_member_count = max(min_size, min(12, min_size + 6))
            for edge in ranked_edges:
                member_ids.add(edge.target if edge.source == seed else edge.source)
                if len(member_ids) >= max_member_count:
                    break
            if len(member_ids) < min_size:
                continue
            candidate = self._grouping_opportunity_for_members(
                nodes,
                correlation_edges,
                member_ids,
                centroid_node_id=seed,
            )
            if candidate:
                candidates.append(candidate)

        selected: list[GraphGroupingOpportunity] = []
        selected_members: list[set[str]] = []
        for candidate in sorted(
            candidates,
            key=lambda item: (-item.score, -item.member_count, item.label, item.id),
        ):
            candidate_members = set(candidate.member_node_ids)
            if any(
                self._jaccard(candidate_members, members) >= 0.72 for members in selected_members
            ):
                continue
            selected.append(candidate)
            selected_members.append(candidate_members)
            if len(selected) >= limit:
                break
        return selected

    def _grouping_opportunity_for_members(
        self,
        nodes: dict[str, GraphNode],
        correlation_edges: list[GraphEdge],
        member_ids: set[str],
        *,
        centroid_node_id: str,
    ) -> GraphGroupingOpportunity | None:
        internal_edges: list[GraphEdge] = []
        external_edges = 0
        for edge in correlation_edges:
            source_in = edge.source in member_ids
            target_in = edge.target in member_ids
            if source_in and target_in:
                internal_edges.append(edge)
            elif source_in or target_in:
                external_edges += 1

        if len(internal_edges) < max(2, len(member_ids) - 1):
            return None

        possible_edges = max(1, len(member_ids) * (len(member_ids) - 1) // 2)
        internal_rank = sum(self._correlation_edge_rank(edge) for edge in internal_edges)
        average_rank = internal_rank / max(1, len(internal_edges))
        cohesion = min(1.0, (len(internal_edges) / possible_edges) * 1.8)
        separation = len(internal_edges) / max(1, len(internal_edges) + external_edges)
        score = (
            average_rank * (0.65 + cohesion) * (0.65 + separation) * math.log2(len(member_ids) + 1)
        )

        keywords = self._grouping_keywords(nodes, internal_edges, member_ids)
        label = self._grouping_label(keywords, nodes[centroid_node_id].label)
        digest = sha256("|".join(sorted(member_ids)).encode("utf-8")).hexdigest()[:12]
        reasons = self._grouping_reasons(internal_edges)
        member_labels = [nodes[node_id].label for node_id in sorted(member_ids)]
        summary = (
            f"{len(member_ids)} memories form a candidate cluster around "
            f"{', '.join(keywords[:3]) if keywords else nodes[centroid_node_id].label}."
        )
        return GraphGroupingOpportunity(
            id=digest,
            label=label,
            summary=summary,
            member_node_ids=sorted(member_ids),
            member_count=len(member_ids),
            centroid_node_id=centroid_node_id,
            score=round(score, 4),
            cohesion=round(cohesion, 4),
            separation=round(separation, 4),
            reasons=reasons,
            keywords=keywords,
            metadata={
                "internal_edges": len(internal_edges),
                "external_edges": external_edges,
                "average_edge_rank": round(average_rank, 4),
                "sample_members": member_labels[:8],
            },
        )

    def _add_grouping_opportunity_nodes(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[str, GraphEdge],
        opportunities: list[GraphGroupingOpportunity],
    ) -> None:
        for opportunity in opportunities:
            group_node_id = f"group:{opportunity.id}"
            nodes[group_node_id] = GraphNode(
                id=group_node_id,
                node_type="group",
                subtype="grouping",
                label=opportunity.label,
                summary=opportunity.summary,
                weight=1.35 + min(1.2, opportunity.score / 20.0),
                metadata={
                    "graph": {
                        "role": "grouping_opportunity",
                        "member_count": opportunity.member_count,
                        "cohesion": opportunity.cohesion,
                        "separation": opportunity.separation,
                        "score": opportunity.score,
                    },
                    "grouping": opportunity.model_dump(mode="json"),
                },
            )
            for member_node_id in opportunity.member_node_ids:
                if member_node_id not in nodes:
                    continue
                edge_id = f"group_member:{opportunity.id}:{member_node_id}"
                edges[edge_id] = GraphEdge(
                    id=edge_id,
                    source=group_node_id,
                    target=member_node_id,
                    edge_type="group_member",
                    label="member",
                    weight=0.5,
                    confidence=max(0.35, opportunity.cohesion),
                    metadata={
                        "group_id": opportunity.id,
                        "score": opportunity.score,
                        "reasons": opportunity.reasons,
                    },
                )
                node_group_ids = nodes[member_node_id].metadata.setdefault("group_ids", [])
                if isinstance(node_group_ids, list) and opportunity.id not in node_group_ids:
                    node_group_ids.append(opportunity.id)

    async def _active_memory_by_source_ref(self, source_ref: str) -> MemoryOut | None:
        try:
            return await self.get_memory_by_source_ref(source_ref)
        except KeyError:
            return None

    def _grouping_member_ids(self, opportunity: GraphGroupingOpportunity) -> list[uuid.UUID]:
        memory_ids: list[uuid.UUID] = []
        for node_id in opportunity.member_node_ids:
            if not node_id.startswith("memory:"):
                continue
            try:
                memory_ids.append(uuid.UUID(node_id.removeprefix("memory:")))
            except ValueError:
                continue
        return sorted(set(memory_ids), key=str)

    def _is_graph_aggregate_memory(self, memory: Memory) -> bool:
        metadata = memory.metadata_ or {}
        return (
            "graph:aggregate" in memory.tags
            or metadata.get("aggregation_kind") == "graph_grouping_opportunity"
        )

    def _grouping_aggregate_source_ref(self, member_memories: list[Memory]) -> str:
        digest = sha256(
            "|".join(sorted(str(memory.id) for memory in member_memories)).encode()
        ).hexdigest()
        return f"onebrain://graph/grouping/{digest[:16]}"

    def _grouping_aggregate_memory_create(
        self,
        opportunity: GraphGroupingOpportunity,
        member_memories: list[Memory],
        request: GraphAggregationRequest,
        *,
        source_ref: str,
    ) -> MemoryCreate:
        scope = (
            request.scope
            or request.graph.filters.scope
            or self._common_memory_scope(member_memories)
        )
        member_ids = [str(memory.id) for memory in member_memories]
        member_titles = [self._memory_label(memory) for memory in member_memories]
        return MemoryCreate(
            memory_type="context",
            title=opportunity.label,
            content=self._grouping_aggregate_content(opportunity, member_memories),
            scope=scope,
            tags=[
                "auto:generated",
                "graph:aggregate",
                "grouping:opportunity",
                "knowledge:aggregate",
            ],
            confidence=min(0.95, max(0.62, 0.55 + opportunity.cohesion * 0.25)),
            source=SourceRef(source_type=request.source_type, source_ref=source_ref),
            entities=[
                EntityInput(
                    name=opportunity.label,
                    entity_type="knowledge_cluster",
                    role="subject",
                ),
                *[
                    EntityInput(name=keyword, entity_type="concept", role="cluster_keyword")
                    for keyword in opportunity.keywords[:8]
                ],
            ],
            metadata={
                "aggregation_kind": "graph_grouping_opportunity",
                "aggregation_version": "v1",
                "opportunity": opportunity.model_dump(mode="json"),
                "member_memory_ids": member_ids,
                "member_titles": member_titles,
                "source_member_count": len(member_memories),
            },
        )

    def _common_memory_scope(self, memories: list[Memory]) -> dict[str, Any]:
        if not memories:
            return {}
        keys = set(memories[0].scope)
        for memory in memories[1:]:
            keys &= set(memory.scope)
        scope: dict[str, Any] = {}
        for key in sorted(keys):
            value = memories[0].scope.get(key)
            if all(memory.scope.get(key) == value for memory in memories):
                scope[key] = value
        return scope

    def _grouping_aggregate_content(
        self,
        opportunity: GraphGroupingOpportunity,
        member_memories: list[Memory],
    ) -> str:
        keywords = ", ".join(opportunity.keywords[:8]) or "not available"
        reasons = ", ".join(opportunity.reasons[:8]) or "not available"
        member_lines = [
            f"- {self._memory_label(memory)}: {self._preview(memory.content, 180)}"
            for memory in member_memories[:12]
        ]
        return "\n".join(
            [
                f"Graph aggregate memory: {opportunity.label}",
                "",
                "Summary",
                opportunity.summary,
                "",
                "Cluster signals",
                f"- Members: {len(member_memories)}",
                f"- Score: {opportunity.score:.2f}",
                f"- Cohesion: {opportunity.cohesion:.2f}",
                f"- Separation: {opportunity.separation:.2f}",
                f"- Keywords: {keywords}",
                f"- Reasons: {reasons}",
                "",
                "Source memories",
                *member_lines,
            ]
        )

    def _grouping_aggregation_item(
        self,
        opportunity: GraphGroupingOpportunity,
        *,
        status: str,
        reason: str | None = None,
        memory_id: uuid.UUID | None = None,
        source_ref: str | None = None,
        member_count: int | None = None,
        links_created: int = 0,
    ) -> GraphAggregationItem:
        return GraphAggregationItem(
            opportunity_id=opportunity.id,
            label=opportunity.label,
            status=status,
            reason=reason,
            memory_id=memory_id,
            source_ref=source_ref,
            member_count=member_count if member_count is not None else opportunity.member_count,
            score=opportunity.score,
            links_created=links_created,
        )

    def _grouping_keywords(
        self,
        nodes: dict[str, GraphNode],
        internal_edges: list[GraphEdge],
        member_ids: set[str],
    ) -> list[str]:
        weights: defaultdict[str, float] = defaultdict(float)
        for edge in internal_edges:
            rank = self._correlation_edge_rank(edge)
            facets = edge.metadata.get("shared_facets")
            entities = edge.metadata.get("shared_entities")
            facet_values = facets if isinstance(facets, list) else []
            entity_values = entities if isinstance(entities, list) else []
            for facet in facet_values:
                keyword = self._keyword_from_grouping_facet(str(facet))
                if keyword:
                    weights[keyword] += rank
            for entity in entity_values:
                keyword = self._humanize_grouping_keyword(str(entity))
                if keyword:
                    weights[keyword] += rank * 0.8

        for node_id in member_ids:
            for term in self._correlation_terms(nodes[node_id].label, limit=8):
                weights[self._humanize_grouping_keyword(term)] += 0.35

        return [
            keyword
            for keyword, _ in sorted(
                weights.items(),
                key=lambda item: (-item[1], item[0]),
            )[:8]
        ]

    def _keyword_from_grouping_facet(self, facet: str) -> str | None:
        if ":" not in facet:
            return None
        prefix, value = facet.split(":", 1)
        if prefix not in {"term", "phrase", "tag"}:
            return None
        return self._humanize_grouping_keyword(value)

    def _humanize_grouping_keyword(self, value: str) -> str:
        tokens = [
            token
            for token in re.split(r"[\s_:/=-]+", normalize_name(value))
            if self._is_correlation_term(token)
        ][:4]
        acronyms = {
            "acl",
            "ado",
            "api",
            "ci",
            "css",
            "e2e",
            "gdpr",
            "http",
            "lgpd",
            "mcp",
            "rpa",
            "sso",
            "tms",
            "xml",
        }
        return " ".join(token.upper() if token in acronyms else token.title() for token in tokens)

    def _grouping_label(self, keywords: list[str], fallback: str) -> str:
        if keywords:
            return f"{' / '.join(keywords[:3])} Cluster"
        return f"{fallback} Cluster"

    def _grouping_reasons(self, internal_edges: list[GraphEdge]) -> list[str]:
        reasons: set[str] = set()
        for edge in internal_edges:
            raw_reasons = edge.metadata.get("reasons")
            if isinstance(raw_reasons, list):
                reasons.update(str(reason) for reason in raw_reasons)
            elif edge.label:
                reasons.add(edge.label)
        return sorted(reasons)

    def _jaccard(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

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
        title = (memory.title or "").strip()
        if title and not self._is_generic_memory_title(title):
            return self._shorten(title, 80)
        derived_label = self._derived_memory_label(memory)
        if derived_label:
            return self._shorten(derived_label, 80)
        return self._shorten(self._preview(memory.content), 80)

    def _is_generic_memory_title(self, value: str) -> bool:
        normalized = re.sub(r"\s+\(\d+/\d+\)$", "", normalize_name(value)).strip()
        return normalized in GENERIC_MEMORY_TITLES

    def _derived_memory_label(self, memory: Memory) -> str | None:
        metadata = memory.metadata_ or {}
        relative_path = (
            self._metadata_string(metadata, "relative_path")
            or self._source_document_from_content(memory.content)
            or self._source_path_from_ref(memory.source_ref)
        )
        source_label = self._source_file_label(relative_path)
        section_title = self._metadata_string(metadata, "section_title")
        summary = self._metadata_string(metadata, "summary") or self._summary_from_content(
            memory.content
        )

        if source_label and self._is_named_catalog_artifact(relative_path):
            return source_label
        if section_title and not self._is_generic_memory_title(section_title):
            if source_label:
                return f"{source_label}: {section_title}"
            return section_title
        if source_label and summary and not self._is_generic_summary(summary):
            return f"{source_label}: {summary}"
        if source_label and (order_index := metadata.get("order_index")):
            return f"{source_label}: section {order_index}"
        if source_label:
            return source_label
        if summary and not self._is_generic_summary(summary):
            return summary
        return None

    def _metadata_string(self, metadata: dict[str, Any], key: str) -> str | None:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _source_document_from_content(self, content: str) -> str | None:
        match = re.search(r"(?im)^Source document:\s*(.+?)\s*$", content)
        if match:
            return match.group(1).strip()
        match = re.search(r"(?im)^Source file:\s*(.+?)\s*$", content)
        if match:
            return match.group(1).strip()
        return None

    def _source_path_from_ref(self, source_ref: str | None) -> str | None:
        if not source_ref:
            return None
        return source_ref.split("#", 1)[0].strip()

    def _source_file_label(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.replace("\\", "/").rstrip("/")
        if not normalized:
            return None
        path = PurePosixPath(normalized)
        name = path.name
        if self._is_named_catalog_artifact(normalized):
            parent = path.parent.name
            if parent:
                return self._humanize_source_label(parent)
        return name or normalized

    def _is_named_catalog_artifact(self, value: str | None) -> bool:
        if not value:
            return False
        name = PurePosixPath(value.replace("\\", "/").rstrip("/")).name.lower()
        return name in {"body.md", "manifest.json", "workflow.json", "library.json", "readme.md"}

    def _humanize_source_label(self, value: str) -> str:
        cleaned = re.sub(r"^(feedback|reference|project|memory|skill)_", "", value.strip())
        tokens = [token for token in re.split(r"[\s_.-]+", normalize_name(cleaned)) if token]
        acronyms = {
            "acl",
            "ado",
            "api",
            "ci",
            "css",
            "e2e",
            "gdpr",
            "http",
            "lgpd",
            "mcp",
            "rpa",
            "sso",
            "tms",
            "ui",
            "xml",
        }
        return " ".join(token.upper() if token in acronyms else token.title() for token in tokens)

    def _summary_from_content(self, content: str) -> str | None:
        match = re.search(r"(?im)^Summary:\s*(.+?)\s*$", content)
        if not match:
            return None
        return match.group(1).strip()

    def _is_generic_summary(self, value: str) -> bool:
        normalized = normalize_name(value)
        return normalized in {"no textual content available", "document body", "document"}

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
