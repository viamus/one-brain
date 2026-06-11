from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from onebrain_core.application.service import OneBrainService
from onebrain_core.contracts.schemas import (
    GraphEdge,
    GraphNode,
    GraphRequest,
    GraphResponse,
    SearchRequest,
)
from onebrain_core.infrastructure.models import Entity, Memory
from onebrain_django.web.graph_ui import graph_view_html


def test_graph_request_normalizes_blank_query() -> None:
    request = GraphRequest(query="   ")

    assert request.query is None
    assert request.include_entities is True
    assert request.include_relations is True
    assert request.include_correlations is True
    assert request.include_vector_correlations is True
    assert request.max_correlation_degree == 6
    assert request.vector_neighbors_per_memory == 4


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


def test_graph_view_html_points_to_graph_endpoint() -> None:
    html = graph_view_html()

    assert '<canvas id="graph"' in html
    assert 'fetch("/graph/data"' in html
    assert "include_entities: false" in html
    assert "include_relations: false" in html
    assert "apiKey" not in html
    assert "detailsJson" not in html


def test_graph_view_html_exposes_correlation_controls() -> None:
    html = graph_view_html()

    assert 'id="includeVectorCorrelations" type="checkbox" checked' in html
    assert 'id="correlationLimit" type="number" min="0" max="2000"' in html
    assert 'id="maxDegree" type="number" min="1" max="50"' in html
    assert "include_vector_correlations: includeVectorEl.checked" in html
    assert "correlation_limit: Number(correlationLimitEl.value || 250)" in html
    assert "max_correlation_degree: Number(maxDegreeEl.value || 6)" in html


def test_graph_view_html_highlights_roles_and_uses_single_animation_loop() -> None:
    html = graph_view_html()

    assert ':root[data-theme="dark"]' in html
    assert 'id="nightMode" type="checkbox"' in html
    assert 'class="legend-title">Legend</span>' in html
    assert 'id="spread"' in html
    assert "document.documentElement.dataset.theme" in html
    assert "centroid_candidate" in html
    assert "grouping_opportunity" in html
    assert "function edgeIsFocused(edge)" in html
    assert "ctx.shadowBlur = 14" in html
    assert "function layoutGraphPositions(nodes, rect)" in html
    assert "cancelAnimationFrame(animationFrameId)" in html
    assert "animationFrameId = requestAnimationFrame(tick)" in html
