from __future__ import annotations

import uuid

import pytest
from onebrain.core.contracts.schemas import GraphEdge, GraphNode
from onebrain.core.correlation import (
    CORRELATION_SCORE_VERSION,
    CorrelationGroupingBuilder,
    CorrelationScorer,
    memory_correlation_facets,
)
from onebrain.infrastructure.models import Memory


def test_correlation_scorer_versions_shared_entity_rank() -> None:
    scorer = CorrelationScorer()

    score = scorer.shared_entity_edge(2)

    assert scorer.score_version == CORRELATION_SCORE_VERSION
    assert score.weight == pytest.approx(0.65)
    assert score.confidence == pytest.approx(0.7)
    assert score.score == 3.65


def test_memory_correlation_facets_filter_noise_and_keep_specific_terms() -> None:
    memory = Memory(
        id=uuid.uuid4(),
        memory_type="workflow",
        title="Invoice routing approval matrix",
        content="Invoice routing exceptions require approval matrix checks.",
        content_hash="a",
        scope={"project": "one-brain", "domain": "finance"},
        tags=["imported", "ext:md", "payment-routing"],
        confidence=0.8,
        source_type="manual",
    )

    facets = memory_correlation_facets(memory)

    assert "term:invoice" in facets
    assert "phrase:invoice routing" in facets
    assert "tag:payment-routing" in facets
    assert "context:domain=finance" in facets
    assert "tag:imported" not in facets
    assert "tag:ext md" not in facets


def test_grouping_builder_adds_score_version_to_opportunity_metadata() -> None:
    nodes = {
        "memory:center": GraphNode(id="memory:center", node_type="memory", label="LGPD checklist"),
        "memory:a": GraphNode(id="memory:a", node_type="memory", label="LGPD assessment"),
        "memory:b": GraphNode(id="memory:b", node_type="memory", label="Privacy checklist"),
    }
    edges = {
        "correlation:center:a": GraphEdge(
            id="correlation:center:a",
            source="memory:center",
            target="memory:a",
            edge_type="correlation",
            label="semantic_overlap",
            weight=0.8,
            confidence=0.8,
            metadata={
                "reasons": ["semantic_overlap"],
                "shared_facets": ["term:lgpd", "phrase:privacy assessment"],
                "score": 7.0,
                "score_version": CORRELATION_SCORE_VERSION,
            },
        ),
        "correlation:center:b": GraphEdge(
            id="correlation:center:b",
            source="memory:center",
            target="memory:b",
            edge_type="correlation",
            label="vector_neighbor",
            weight=0.85,
            confidence=0.85,
            metadata={
                "reasons": ["vector_neighbor"],
                "score": 8.0,
                "score_version": CORRELATION_SCORE_VERSION,
            },
        ),
    }

    opportunities = CorrelationGroupingBuilder().build(nodes, edges, limit=4, min_size=3)

    assert len(opportunities) == 1
    assert opportunities[0].centroid_node_id == "memory:center"
    assert opportunities[0].metadata["score_version"] == CORRELATION_SCORE_VERSION
    assert opportunities[0].metadata["internal_edges"] == 2
