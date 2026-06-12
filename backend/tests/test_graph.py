from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from onebrain.core.application.service import OneBrainService
from onebrain.core.contracts.schemas import (
    ContextRequest,
    EntityInput,
    GraphAggregationRequest,
    GraphEdge,
    GraphGroupingOpportunity,
    GraphNode,
    GraphRequest,
    GraphResponse,
    MemoryOut,
    SearchHit,
    SearchRequest,
)
from onebrain.infrastructure.models import Entity, Memory


class FakeEntityScalarResult:
    def __init__(self, entity: Entity | None) -> None:
        self._entity = entity

    def first(self) -> Entity | None:
        return self._entity


class FakeEntityExecuteResult:
    def __init__(
        self,
        *,
        entity: Entity | None = None,
        inserted_id: uuid.UUID | None = None,
        fail_scalar_lookup: bool = False,
    ) -> None:
        self._entity = entity
        self._inserted_id = inserted_id
        self._fail_scalar_lookup = fail_scalar_lookup

    def scalars(self) -> FakeEntityScalarResult:
        return FakeEntityScalarResult(self._entity)

    def scalar_one(self) -> uuid.UUID:
        if self._inserted_id is None:
            raise AssertionError("expected returned entity id")
        return self._inserted_id

    def scalar_one_or_none(self) -> uuid.UUID | None:
        if self._fail_scalar_lookup:
            raise AssertionError(
                "entity lookup must tolerate duplicate rows with scalars().first()"
            )
        return self._inserted_id


class FakeEntitySession:
    def __init__(self, *results: FakeEntityExecuteResult) -> None:
        self._results = list(results)
        self.added: list[Entity] = []
        self.flushed = False

    async def execute(self, _statement: object) -> FakeEntityExecuteResult:
        if not self._results:
            raise AssertionError("unexpected entity query")
        return self._results.pop(0)

    def add(self, entity: Entity) -> None:
        self.added.append(entity)

    async def flush(self) -> None:
        self.flushed = True


def test_graph_request_normalizes_blank_query() -> None:
    request = GraphRequest(query="   ")

    assert request.query is None
    assert request.include_entities is True
    assert request.include_relations is True
    assert request.include_correlations is True
    assert request.include_vector_correlations is True
    assert request.max_correlation_degree == 6
    assert request.vector_neighbors_per_memory == 4
    assert request.include_grouping_opportunities is True
    assert request.grouping_limit == 8
    assert request.grouping_min_size == 3


def memory_for_test(**kwargs) -> Memory:
    defaults = {
        "status": "active",
        "metadata_": {},
        "vector_status": "indexed",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return Memory(**defaults)


@pytest.mark.asyncio
async def test_upsert_entity_returns_upserted_entity_by_id() -> None:
    existing = Entity(
        id=uuid.uuid4(),
        name="Portal",
        normalized_name="portal",
        entity_type="system",
        summary=None,
        metadata_={},
    )
    session = FakeEntitySession(
        FakeEntityExecuteResult(inserted_id=existing.id),
        FakeEntityExecuteResult(entity=existing, fail_scalar_lookup=True),
    )
    service = OneBrainService.__new__(OneBrainService)

    entity = await service._upsert_entity(
        session,
        EntityInput(name="Portal", entity_type="system", role="subject"),
    )

    assert entity is existing
    assert session.added == []
    assert session.flushed is False


@pytest.mark.asyncio
async def test_upsert_entity_returns_existing_entity_after_conflict_update() -> None:
    existing = Entity(
        id=uuid.uuid4(),
        name="Specialist",
        normalized_name="specialist",
        entity_type="concept",
        summary=None,
        metadata_={},
    )
    session = FakeEntitySession(
        FakeEntityExecuteResult(inserted_id=existing.id),
        FakeEntityExecuteResult(entity=existing, fail_scalar_lookup=True),
    )
    service = OneBrainService.__new__(OneBrainService)

    entity = await service._upsert_entity(
        session,
        EntityInput(name="Specialist", entity_type="concept", role="subject"),
    )

    assert entity is existing
    assert session.added == []
    assert session.flushed is False


def test_graph_response_keeps_machine_readable_nodes_and_edges() -> None:
    response = GraphResponse(
        query="skill",
        nodes=[
            {
                "id": "memory:1",
                "node_type": "memory",
                "label": "PR Reviewer",
                "subtype": "skill",
            }
        ],
        edges=[
            {
                "id": "correlation:1:2",
                "source": "memory:1",
                "target": "memory:2",
                "edge_type": "correlation",
                "label": "shared_entity",
            }
        ],
        memory_count=1,
        entity_count=0,
    )

    assert response.nodes[0].id == "memory:1"
    assert response.edges[0].edge_type == "correlation"
    assert response.grouping_opportunities == []


def test_correlation_edges_aggregate_shared_entities() -> None:
    service = OneBrainService.__new__(OneBrainService)
    left = uuid.uuid4()
    right = uuid.uuid4()
    project = Entity(
        id=uuid.uuid4(),
        name="one-brain",
        normalized_name="one-brain",
        entity_type="project",
    )
    skill = Entity(
        id=uuid.uuid4(),
        name="PR Reviewer",
        normalized_name="pr reviewer",
        entity_type="skill",
    )
    edges: dict[str, GraphEdge] = {}

    service._add_correlation_edges(
        edges,
        [
            (left, "scope", project),
            (right, "scope", project),
            (left, "subject", skill),
            (right, "subject", skill),
        ],
        limit=10,
    )

    assert len(edges) == 1
    edge = next(iter(edges.values()))
    assert edge.edge_type == "correlation"
    assert {edge.source, edge.target} == {f"memory:{left}", f"memory:{right}"}
    assert edge.metadata["shared_entities"] == ["PR Reviewer", "one-brain"]


def test_facet_correlation_edges_ignore_broad_context_only() -> None:
    service = OneBrainService.__new__(OneBrainService)
    left = Memory(
        id=uuid.uuid4(),
        memory_type="rule",
        title="A",
        content="A",
        content_hash="a",
        scope={"project": "one-brain", "library": "skills"},
        tags=["imported", "library:skills", "ext:md"],
        confidence=0.8,
        source_type="private-catalog-library",
    )
    right = Memory(
        id=uuid.uuid4(),
        memory_type="workflow",
        title="B",
        content="B",
        content_hash="b",
        scope={"project": "one-brain", "library": "skills"},
        tags=["library:skills", "file-memory"],
        confidence=0.8,
        source_type="private-catalog-library",
    )
    edges: dict[str, GraphEdge] = {}

    service._add_facet_correlation_edges(edges, [left, right], limit=10)

    assert edges == {}


def test_facet_correlation_edges_use_semantic_overlap() -> None:
    service = OneBrainService.__new__(OneBrainService)
    left = Memory(
        id=uuid.uuid4(),
        memory_type="rule",
        title="Wait For Response request headers",
        content="Use Wait For Response when request headers and response status are needed.",
        content_hash="a",
        scope={"project": "one-brain", "library": "robot-framework-browser-e2e"},
        tags=["browser-request", "library:robot-framework-browser-e2e"],
        confidence=0.8,
        source_type="private-catalog-library",
    )
    right = Memory(
        id=uuid.uuid4(),
        memory_type="pitfall",
        title="Request headers are missing from Wait For Request",
        content="Wait For Request returns the URL, so request headers need another keyword.",
        content_hash="b",
        scope={"project": "one-brain", "library": "robot-framework-browser-e2e"},
        tags=["browser-request", "file-memory"],
        confidence=0.8,
        source_type="private-catalog-library",
    )
    edges: dict[str, GraphEdge] = {}

    service._add_facet_correlation_edges(edges, [left, right], limit=10)

    assert len(edges) == 1
    edge = next(iter(edges.values()))
    assert edge.edge_type == "correlation"
    assert edge.label == "semantic_overlap"
    assert "term:request" in edge.metadata["shared_facets"]
    assert "term:headers" in edge.metadata["shared_facets"]
    assert not any(facet.startswith("context:project") for facet in edge.metadata["shared_facets"])


def test_facet_correlation_edges_ignore_generic_content_overlap() -> None:
    service = OneBrainService.__new__(OneBrainService)
    left = Memory(
        id=uuid.uuid4(),
        memory_type="pitfall",
        title="Wait For Request returns URL",
        content="Robot Framework Browser feedback explains request keyword behavior.",
        content_hash="a",
        scope={"project": "one-brain", "library": "robot-framework-browser-e2e"},
        tags=["library:robot-framework-browser-e2e", "source-type:feedback"],
        confidence=0.8,
        source_type="private-catalog-library",
    )
    right = Memory(
        id=uuid.uuid4(),
        memory_type="rule",
        title="Log To Console keeps ASCII output",
        content="Robot Framework Browser feedback explains console keyword behavior.",
        content_hash="b",
        scope={"project": "one-brain", "library": "robot-framework-browser-e2e"},
        tags=["library:robot-framework-browser-e2e", "source-type:feedback"],
        confidence=0.8,
        source_type="private-catalog-library",
    )
    edges: dict[str, GraphEdge] = {}

    service._add_facet_correlation_edges(edges, [left, right], limit=10)

    assert edges == {}


def test_facet_correlation_edges_ignore_catalog_descriptors() -> None:
    service = OneBrainService.__new__(OneBrainService)
    descriptor = Memory(
        id=uuid.uuid4(),
        memory_type="context",
        title="Imported memory: library",
        content="LGPD privacy assessment reference library",
        content_hash="a",
        scope={"project": "one-brain", "library": "lgpd-privacy-assessment-reference"},
        tags=["library:lgpd-privacy-assessment-reference"],
        confidence=0.8,
        source_type="private-catalog-library",
        source_ref="catalog://private/libraries/lgpd-privacy-assessment-reference/library.json",
    )
    fact = Memory(
        id=uuid.uuid4(),
        memory_type="fact",
        title="LGPD privacy assessment checklist",
        content="LGPD privacy assessment reference checklist",
        content_hash="b",
        scope={"project": "one-brain", "library": "lgpd-privacy-assessment-reference"},
        tags=["library:lgpd-privacy-assessment-reference"],
        confidence=0.8,
        source_type="private-catalog-library",
    )
    edges: dict[str, GraphEdge] = {}

    service._add_facet_correlation_edges(edges, [descriptor, fact], limit=10)

    assert edges == {}


def test_facet_correlation_edges_respect_max_degree() -> None:
    service = OneBrainService.__new__(OneBrainService)
    memories = [
        Memory(
            id=uuid.uuid4(),
            memory_type="fact",
            title="Invoice routing approval matrix",
            content="Invoice routing approval matrix.",
            content_hash=str(index),
            scope={"project": "one-brain"},
            tags=[],
            confidence=0.8,
            source_type="manual",
        )
        for index in range(3)
    ]
    edges: dict[str, GraphEdge] = {}

    service._add_facet_correlation_edges(edges, memories, limit=10, max_degree=1)

    assert len(edges) == 1


@pytest.mark.asyncio
async def test_vector_correlation_edges_use_rag_neighbors() -> None:
    service = OneBrainService.__new__(OneBrainService)
    left_id = uuid.uuid4()
    right_id = uuid.uuid4()
    left = Memory(
        id=left_id,
        memory_type="fact",
        title="LGPD privacy assessment",
        content="LGPD privacy assessment",
        content_hash="a",
        scope={"project": "one-brain"},
        tags=[],
        confidence=0.8,
        source_type="manual",
    )
    right = Memory(
        id=right_id,
        memory_type="fact",
        title="Privacy assessment checklist",
        content="Privacy assessment checklist",
        content_hash="b",
        scope={"project": "one-brain"},
        tags=[],
        confidence=0.8,
        source_type="manual",
    )

    class FakeEmbeddings:
        async def embed(self, texts):
            assert len(texts) == 2
            return [[1.0, 0.0], [0.8, 0.2]]

    class FakeVectorStore:
        async def search(self, *, vector, limit, filters):
            assert filters == {"status": ["active"]}
            if vector == [1.0, 0.0]:
                return [
                    SimpleNamespace(memory_id=left_id, score=1.0),
                    SimpleNamespace(memory_id=right_id, score=0.91),
                ]
            return [
                SimpleNamespace(memory_id=right_id, score=1.0),
                SimpleNamespace(memory_id=left_id, score=0.91),
            ]

    service._embeddings = FakeEmbeddings()
    service._vector_store = FakeVectorStore()
    edges: dict[str, GraphEdge] = {}

    await service._add_vector_correlation_edges(
        edges,
        [left, right],
        request=GraphRequest(
            include_entities=False,
            include_relations=False,
            vector_neighbors_per_memory=2,
            vector_similarity_threshold=0.8,
        ),
        limit=10,
        max_degree=6,
    )

    assert len(edges) == 1
    edge = next(iter(edges.values()))
    assert edge.label == "vector_neighbor"
    assert edge.metadata["reasons"] == ["vector_neighbor"]
    assert edge.metadata["vector_similarity"] == 0.91


def test_graph_insights_annotate_centroid_candidates() -> None:
    service = OneBrainService.__new__(OneBrainService)
    center_id = "memory:center"
    nodes = {
        center_id: GraphNode(
            id=center_id,
            node_type="memory",
            label="LGPD hub",
        )
    }
    edges: dict[str, GraphEdge] = {}
    for index in range(3):
        node_id = f"memory:{index}"
        nodes[node_id] = GraphNode(
            id=node_id,
            node_type="memory",
            label=f"LGPD {index}",
        )
        edges[f"correlation:center:{index}"] = GraphEdge(
            id=f"correlation:center:{index}",
            source=center_id,
            target=node_id,
            edge_type="correlation",
            label="vector_neighbor",
            weight=0.9,
            confidence=0.9,
            metadata={"reasons": ["vector_neighbor"], "score": 9.0},
        )

    service._annotate_graph_insights(nodes, edges)

    assert nodes[center_id].metadata["graph"]["degree"] == 3
    assert nodes[center_id].metadata["graph"]["role"] == "centroid_candidate"
    assert nodes[center_id].weight > 1.0


def test_graph_grouping_opportunities_build_cluster_nodes() -> None:
    service = OneBrainService.__new__(OneBrainService)
    center_id = "memory:center"
    nodes = {
        center_id: GraphNode(id=center_id, node_type="memory", label="LGPD privacy checklist"),
    }
    edges: dict[str, GraphEdge] = {}
    for index in range(3):
        node_id = f"memory:{index}"
        nodes[node_id] = GraphNode(
            id=node_id,
            node_type="memory",
            label=f"LGPD privacy assessment {index}",
        )
        edges[f"correlation:center:{index}"] = GraphEdge(
            id=f"correlation:center:{index}",
            source=center_id,
            target=node_id,
            edge_type="correlation",
            label="semantic_overlap",
            weight=0.9,
            confidence=0.9,
            metadata={
                "reasons": ["semantic_overlap", "vector_neighbor"],
                "shared_facets": ["term:lgpd", "phrase:privacy assessment"],
                "score": 8.0,
            },
        )

    opportunities = service._build_grouping_opportunities(
        nodes,
        edges,
        limit=4,
        min_size=3,
    )
    service._add_grouping_opportunity_nodes(nodes, edges, opportunities)

    assert len(opportunities) == 1
    opportunity = opportunities[0]
    assert opportunity.member_count == 4
    assert opportunity.centroid_node_id == center_id
    assert "LGPD" in opportunity.label
    assert opportunity.cohesion > 0
    assert opportunity.reasons == ["semantic_overlap", "vector_neighbor"]
    assert f"group:{opportunity.id}" in nodes
    assert nodes[f"group:{opportunity.id}"].metadata["graph"]["role"] == "grouping_opportunity"
    assert len([edge for edge in edges.values() if edge.edge_type == "group_member"]) == 4


def test_graph_grouping_opportunities_deduplicate_overlapping_seeds() -> None:
    service = OneBrainService.__new__(OneBrainService)
    nodes = {
        f"memory:{index}": GraphNode(
            id=f"memory:{index}",
            node_type="memory",
            label=f"TMS release readiness {index}",
        )
        for index in range(4)
    }
    edges: dict[str, GraphEdge] = {}
    for left, right in (("0", "1"), ("0", "2"), ("0", "3"), ("1", "2"), ("2", "3")):
        edges[f"correlation:{left}:{right}"] = GraphEdge(
            id=f"correlation:{left}:{right}",
            source=f"memory:{left}",
            target=f"memory:{right}",
            edge_type="correlation",
            label="vector_neighbor",
            weight=0.9,
            confidence=0.9,
            metadata={"reasons": ["vector_neighbor"], "score": 9.0},
        )

    opportunities = service._build_grouping_opportunities(
        nodes,
        edges,
        limit=8,
        min_size=3,
    )

    assert len(opportunities) == 1


def test_graph_grouping_opportunities_ignore_catalog_artifact_keywords() -> None:
    service = OneBrainService.__new__(OneBrainService)
    titles = [
        "Frontend Product Engineer",
        "MCP Integration Architect",
        "SonarQube technical Debt Negotiator",
    ]
    nodes = {
        f"memory:{index}": GraphNode(
            id=f"memory:{index}",
            node_type="memory",
            label=title,
        )
        for index, title in enumerate(titles)
    }
    edges: dict[str, GraphEdge] = {}
    for left, right in (("0", "1"), ("0", "2"), ("1", "2")):
        edges[f"correlation:{left}:{right}"] = GraphEdge(
            id=f"correlation:{left}:{right}",
            source=f"memory:{left}",
            target=f"memory:{right}",
            edge_type="correlation",
            label="shared_entity",
            weight=0.8,
            confidence=0.8,
            metadata={
                "reasons": ["shared_entity"],
                "shared_entities": [
                    "ambevtech",
                    "body",
                    "configura",
                    "fonte",
                    "padr",
                    "topic",
                    "architect",
                    "debt",
                ],
                "score": 7.0,
            },
        )

    opportunities = service._build_grouping_opportunities(
        nodes,
        edges,
        limit=4,
        min_size=3,
    )

    assert len(opportunities) == 1
    assert "Body" not in opportunities[0].keywords
    assert "Ambevtech" not in opportunities[0].keywords
    assert "Configura" not in opportunities[0].keywords
    assert "Fonte" not in opportunities[0].keywords
    assert "Padr" not in opportunities[0].keywords
    assert "Topic" not in opportunities[0].keywords
    assert "Body" not in opportunities[0].label
    assert "Ambevtech" not in opportunities[0].label
    assert "Configura" not in opportunities[0].label
    assert "Fonte" not in opportunities[0].label
    assert "Padr" not in opportunities[0].label
    assert "Topic" not in opportunities[0].label


@pytest.mark.asyncio
async def test_graph_aggregation_materializes_grouping_opportunity_memory() -> None:
    service = OneBrainService.__new__(OneBrainService)
    member_ids = [uuid.uuid4() for _ in range(3)]
    aggregate_id = uuid.uuid4()
    opportunity = GraphGroupingOpportunity(
        id="cluster-1",
        label="LGPD Privacy Cluster",
        summary="3 memories form a candidate cluster around LGPD privacy.",
        member_node_ids=[f"memory:{memory_id}" for memory_id in member_ids],
        member_count=3,
        centroid_node_id=f"memory:{member_ids[0]}",
        score=12.5,
        cohesion=0.8,
        separation=0.7,
        reasons=["semantic_overlap", "vector_neighbor"],
        keywords=["LGPD", "Privacy"],
    )
    members = [
        memory_for_test(
            id=memory_id,
            memory_type="context",
            title=f"LGPD source {index}",
            content=f"LGPD source content {index}",
            content_hash=f"member-{index}",
            scope={"project": "one-brain"},
            tags=[],
            confidence=0.8,
            source_type="manual",
        )
        for index, memory_id in enumerate(member_ids)
    ]
    captured_payloads = []
    links = []

    async def fake_build_graph(request: GraphRequest):
        return SimpleNamespace(
            memory_count=len(members),
            grouping_opportunities=[opportunity],
        )

    async def fake_load_memories(memory_ids):
        return [memory for memory in members if memory.id in set(memory_ids)]

    async def no_existing(source_ref):
        return None

    async def fake_capture_memory(payload, actor="system"):
        captured_payloads.append(payload)
        return SimpleNamespace(id=aggregate_id)

    async def fake_link_memories(**kwargs):
        links.append(kwargs)
        return {"id": str(uuid.uuid4())}

    service.build_graph = fake_build_graph
    service._load_memories = fake_load_memories
    service._active_memory_by_source_ref = no_existing
    service.capture_memory = fake_capture_memory
    service.link_memories = fake_link_memories

    result = await service.materialize_grouping_opportunities(
        GraphAggregationRequest(
            graph=GraphRequest(filters={"scope": {"project": "one-brain"}}),
            min_member_count=3,
        )
    )

    assert result.created == 1
    assert result.items[0].memory_id == aggregate_id
    assert result.items[0].links_created == 3
    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    assert payload.memory_type == "context"
    assert payload.title == "LGPD Privacy Cluster"
    assert "graph:aggregate" in payload.tags
    assert payload.source.source_type == "graph-aggregation"
    assert payload.metadata["member_memory_ids"] == [str(memory.id) for memory in members]
    assert len(links) == 3
    assert {link["to_memory_id"] for link in links} == set(member_ids)
    assert all(link["link_type"] == "aggregates" for link in links)


@pytest.mark.asyncio
async def test_graph_aggregation_skips_existing_aggregate_memory() -> None:
    service = OneBrainService.__new__(OneBrainService)
    member_ids = [uuid.uuid4() for _ in range(3)]
    existing_id = uuid.uuid4()
    opportunity = GraphGroupingOpportunity(
        id="cluster-1",
        label="Existing Cluster",
        summary="Existing cluster.",
        member_node_ids=[f"memory:{memory_id}" for memory_id in member_ids],
        member_count=3,
        score=10,
        cohesion=0.75,
    )
    members = [
        memory_for_test(
            id=memory_id,
            memory_type="context",
            title=f"Source {index}",
            content=f"Source content {index}",
            content_hash=f"member-{index}",
            scope={"project": "one-brain"},
            tags=[],
            confidence=0.8,
            source_type="manual",
        )
        for index, memory_id in enumerate(member_ids)
    ]
    captured = False

    async def fake_build_graph(request: GraphRequest):
        return SimpleNamespace(memory_count=len(members), grouping_opportunities=[opportunity])

    async def fake_load_memories(memory_ids):
        return [memory for memory in members if memory.id in set(memory_ids)]

    async def existing_memory(source_ref):
        return SimpleNamespace(id=existing_id)

    async def should_not_capture(payload, actor="system"):
        nonlocal captured
        captured = True
        return SimpleNamespace(id=uuid.uuid4())

    service.build_graph = fake_build_graph
    service._load_memories = fake_load_memories
    service._active_memory_by_source_ref = existing_memory
    service.capture_memory = should_not_capture

    result = await service.materialize_grouping_opportunities(
        GraphAggregationRequest(graph=GraphRequest(), min_member_count=3)
    )

    assert result.created == 0
    assert result.existing == 1
    assert result.items[0].status == "existing"
    assert result.items[0].memory_id == existing_id
    assert captured is False


def test_memory_graph_label_derives_source_context_for_generic_document_body() -> None:
    service = OneBrainService.__new__(OneBrainService)
    memory = Memory(
        id=uuid.uuid4(),
        memory_type="fact",
        title="Document body",
        content=(
            "# Document body\n\n"
            "Summary: Canonical Python entry point keeps FastAPI tracing stable.\n\n"
            "Source document: sources/platform/runtime.md\n"
            "Parent context: Runtime platform\n\n"
            "Details."
        ),
        content_hash="a",
        scope={"project": "one-brain"},
        tags=["ingestion:child"],
        confidence=0.8,
        source_type="private-catalog-library",
        source_ref="catalog://private/libraries/platform/sources/platform/runtime.md#section-1",
        metadata_={
            "relative_path": "sources/platform/runtime.md",
            "order_index": 1,
            "summary": "Canonical Python entry point keeps FastAPI tracing stable.",
        },
    )

    node = service._memory_graph_node(memory)

    assert node.label == "runtime.md: Canonical Python entry point keeps FastAPI tracing stable."
    assert node.label != "Document body"


def test_memory_graph_label_uses_source_ref_when_generic_metadata_is_missing() -> None:
    service = OneBrainService.__new__(OneBrainService)
    memory = Memory(
        id=uuid.uuid4(),
        memory_type="fact",
        title="Document",
        content="No useful headings.",
        content_hash="a",
        scope={"project": "one-brain"},
        tags=[],
        confidence=0.8,
        source_type="private-catalog-library",
        source_ref="catalog://private/libraries/platform/sources/platform/runtime.md#section-1",
    )

    assert service._memory_label(memory) == "runtime.md"


def test_memory_graph_label_humanizes_catalog_manifest_artifact() -> None:
    service = OneBrainService.__new__(OneBrainService)
    memory = Memory(
        id=uuid.uuid4(),
        memory_type="workflow",
        title="Manifest",
        content="Summary: Specialist for Azure DevOps build failure diagnostics.",
        content_hash="a",
        scope={"catalog": "private-engineering-catalog"},
        tags=["ingestion:macro"],
        confidence=0.8,
        source_type="github-private-catalog",
        source_ref=(
            "catalog://github-private-catalog/skills/"
            "ado-build-failure-diagnostician/manifest.json#document"
        ),
    )

    assert service._memory_label(memory) == "ADO Build Failure Diagnostician"


def test_memory_graph_label_humanizes_catalog_body_artifact() -> None:
    service = OneBrainService.__new__(OneBrainService)
    memory = Memory(
        id=uuid.uuid4(),
        memory_type="workflow",
        title="Body",
        content="Summary: Specialist for Azure DevOps build failure diagnostics.",
        content_hash="a",
        scope={"catalog": "private-engineering-catalog"},
        tags=["ingestion:macro"],
        confidence=0.8,
        source_type="github-private-catalog",
        metadata_={"relative_path": "skills/agent-builder/body.md"},
    )

    assert service._memory_label(memory) == "Agent Builder"


@pytest.mark.asyncio
async def test_build_graph_omits_ingestion_child_memories() -> None:
    service = OneBrainService.__new__(OneBrainService)
    context = Memory(
        id=uuid.uuid4(),
        memory_type="context",
        title="Runtime platform",
        content="Macro context with source references.",
        content_hash="a",
        scope={"project": "one-brain"},
        tags=["ingestion:macro"],
        confidence=0.88,
        source_type="private-catalog-library",
        metadata_={"ingestion_item_type": "document"},
    )
    child = Memory(
        id=uuid.uuid4(),
        memory_type="fact",
        title="runtime.md: section 1",
        content="Detailed file body.",
        content_hash="b",
        scope={"project": "one-brain"},
        tags=["ingestion:child"],
        confidence=0.88,
        source_type="private-catalog-library",
        metadata_={"ingestion_item_type": "section"},
    )

    async def fake_graph_memories(request: GraphRequest):
        return [child, context]

    service._graph_memories = fake_graph_memories

    result = await service.build_graph(
        GraphRequest(include_entities=False, include_relations=False, include_correlations=False)
    )

    assert [node.label for node in result.nodes] == ["Runtime platform"]
    assert result.memory_count == 1
    assert result.omitted == 1


@pytest.mark.asyncio
async def test_build_graph_omits_source_document_entities() -> None:
    service = OneBrainService.__new__(OneBrainService)
    memory_id = uuid.uuid4()
    memory = Memory(
        id=memory_id,
        memory_type="context",
        title="Runtime platform",
        content="Macro context with source references.",
        content_hash="a",
        scope={"project": "one-brain"},
        tags=["ingestion:macro"],
        confidence=0.88,
        source_type="private-catalog-library",
    )
    source_document = Entity(
        id=uuid.uuid4(),
        name="sources/platform/runtime.md",
        normalized_name="sources/platform/runtime.md",
        entity_type="source_document",
    )
    concept = Entity(
        id=uuid.uuid4(),
        name="Runtime platform",
        normalized_name="runtime platform",
        entity_type="concept",
    )

    async def fake_graph_memories(request: GraphRequest):
        return [memory]

    async def fake_graph_memory_entities(memory_ids: set[uuid.UUID]):
        return [
            (memory_id, "source", source_document),
            (memory_id, "subject", concept),
        ]

    service._graph_memories = fake_graph_memories
    service._graph_memory_entities = fake_graph_memory_entities

    result = await service.build_graph(
        GraphRequest(include_entities=True, include_relations=False, include_correlations=False)
    )

    assert {node.label for node in result.nodes} == {"Runtime platform"}
    assert all(node.subtype != "source_document" for node in result.nodes)
    assert result.entity_count == 1


@pytest.mark.asyncio
async def test_graph_query_caps_internal_search_limit() -> None:
    service = OneBrainService.__new__(OneBrainService)

    async def fake_search(request: SearchRequest):
        assert request.limit == 100
        return SimpleNamespace(hits=[])

    async def fake_load_memories(memory_ids):
        assert list(memory_ids) == []
        return []

    service.search = fake_search
    service._load_memories = fake_load_memories

    result = await service._graph_memories(GraphRequest(query="onebrain", limit=500))

    assert result == []


@pytest.mark.asyncio
async def test_safe_vector_search_returns_empty_when_embedding_fails() -> None:
    service = OneBrainService.__new__(OneBrainService)

    class FailingEmbeddings:
        async def embed(self, texts):
            raise RuntimeError("embedding unavailable")

    class UnusedVectorStore:
        async def search(self, **kwargs):
            raise AssertionError("vector search should not be called")

    service._embeddings = FailingEmbeddings()
    service._vector_store = UnusedVectorStore()

    assert await service._safe_vector_search(SearchRequest(query="onebrain")) == []


@pytest.mark.asyncio
async def test_safe_vector_search_passes_scope_and_tag_filters() -> None:
    service = OneBrainService.__new__(OneBrainService)
    captured = {}

    class FakeEmbeddings:
        async def embed(self, texts):
            return [[1.0, 0.0]]

    class FakeVectorStore:
        async def search(self, *, vector, limit, filters):
            captured["filters"] = filters
            return []

    service._embeddings = FakeEmbeddings()
    service._vector_store = FakeVectorStore()

    await service._safe_vector_search(
        SearchRequest(
            query="cluster",
            filters={
                "memory_types": ["context"],
                "tags": ["graph:aggregate"],
                "scope": {"catalog": "private-engineering-catalog"},
                "statuses": ["active"],
            },
        )
    )

    assert captured["filters"] == {
        "status": ["active"],
        "memory_type": ["context"],
        "tags": ["graph:aggregate"],
        "scope.catalog": "private-engineering-catalog",
    }


@pytest.mark.asyncio
async def test_compose_context_uses_graph_guided_related_memories() -> None:
    service = OneBrainService.__new__(OneBrainService)
    seed_id = uuid.uuid4()
    entity_candidate_id = uuid.uuid4()
    vector_candidate_id = uuid.uuid4()
    shared_entity = Entity(
        id=uuid.uuid4(),
        name="LGPD",
        normalized_name="lgpd",
        entity_type="concept",
    )
    memories_by_id = {
        seed_id: memory_for_test(
            id=seed_id,
            memory_type="context",
            title="LGPD privacy assessment seed",
            content="LGPD privacy assessment seed context.",
            content_hash="seed",
            scope={"project": "one-brain"},
            tags=[],
            confidence=0.9,
            source_type="manual",
        ),
        entity_candidate_id: memory_for_test(
            id=entity_candidate_id,
            memory_type="context",
            title="LGPD checklist controls",
            content="LGPD checklist controls and privacy assessment guidance.",
            content_hash="entity",
            scope={"project": "one-brain"},
            tags=[],
            confidence=0.85,
            source_type="manual",
        ),
        vector_candidate_id: memory_for_test(
            id=vector_candidate_id,
            memory_type="context",
            title="Privacy controls readiness",
            content="Privacy controls readiness for LGPD assessment.",
            content_hash="vector",
            scope={"project": "one-brain"},
            tags=[],
            confidence=0.82,
            source_type="manual",
        ),
    }

    async def fake_search(request: SearchRequest):
        assert request.include_graph is True
        return SimpleNamespace(
            hits=[
                SearchHit(
                    memory=MemoryOut.model_validate(memories_by_id[seed_id]),
                    score=0.95,
                    reasons=["keyword"],
                )
            ]
        )

    async def fake_load_memories(memory_ids):
        return [
            memories_by_id[memory_id] for memory_id in memory_ids if memory_id in memories_by_id
        ]

    async def fake_related_memories(memory_ids, scope, limit):
        assert seed_id in memory_ids
        return [
            SearchHit(
                memory=MemoryOut.model_validate(memories_by_id[entity_candidate_id]),
                score=0.55,
                reasons=["shared_entity"],
            )
        ]

    async def fake_graph_memory_entities(memory_ids):
        return [
            (seed_id, "subject", shared_entity),
            (entity_candidate_id, "subject", shared_entity),
        ]

    class FakeEmbeddings:
        async def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    class FakeVectorStore:
        async def search(self, *, vector, limit, filters):
            assert filters == {"status": ["active"]}
            return [
                SimpleNamespace(memory_id=seed_id, score=1.0),
                SimpleNamespace(memory_id=vector_candidate_id, score=0.9),
            ]

    service.search = fake_search
    service._load_memories = fake_load_memories
    service._related_memories = fake_related_memories
    service._graph_memory_entities = fake_graph_memory_entities
    service._embeddings = FakeEmbeddings()
    service._vector_store = FakeVectorStore()

    context = await service.compose_context(
        ContextRequest(task="LGPD privacy", scope={"project": "one-brain"}, include_related=True)
    )

    related_by_id = {item.id: item for item in context.related}

    assert entity_candidate_id in related_by_id
    assert vector_candidate_id in related_by_id
    assert "graph_shared_entity" in related_by_id[entity_candidate_id].reasons
    assert "graph_correlation" in related_by_id[entity_candidate_id].reasons
    assert "graph_vector_neighbor" in related_by_id[vector_candidate_id].reasons


@pytest.mark.asyncio
async def test_compose_context_falls_back_when_graph_guided_related_fails() -> None:
    service = OneBrainService.__new__(OneBrainService)
    seed_id = uuid.uuid4()
    related_id = uuid.uuid4()
    memories_by_id = {
        seed_id: memory_for_test(
            id=seed_id,
            memory_type="context",
            title="LGPD privacy seed",
            content="LGPD privacy seed context.",
            content_hash="seed",
            scope={"project": "one-brain"},
            tags=[],
            confidence=0.9,
            source_type="manual",
        ),
        related_id: memory_for_test(
            id=related_id,
            memory_type="context",
            title="Fallback related privacy controls",
            content="Fallback related privacy controls.",
            content_hash="related",
            scope={"project": "one-brain"},
            tags=[],
            confidence=0.82,
            source_type="manual",
        ),
    }

    async def fake_search(request: SearchRequest):
        return SimpleNamespace(
            hits=[
                SearchHit(
                    memory=MemoryOut.model_validate(memories_by_id[seed_id]),
                    score=0.95,
                    reasons=["keyword"],
                )
            ]
        )

    async def failing_graph_related(memory_ids, scope, limit):
        raise RuntimeError("graph unavailable")

    async def fallback_related(memory_ids, scope, limit):
        assert seed_id in memory_ids
        return [
            SearchHit(
                memory=MemoryOut.model_validate(memories_by_id[related_id]),
                score=0.5,
                reasons=["shared_entity"],
            )
        ]

    service.search = fake_search
    service._graph_guided_related_memories = failing_graph_related
    service._related_memories = fallback_related

    context = await service.compose_context(
        ContextRequest(task="LGPD privacy", scope={"project": "one-brain"}, include_related=True)
    )

    assert [item.id for item in context.related] == [related_id]
    assert context.related[0].reasons == ["shared_entity"]
