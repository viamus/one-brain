from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from onebrain.core.contracts.schemas import GraphEdge

CORRELATION_SCORE_VERSION = "deterministic-v1"


@dataclass(frozen=True)
class EdgeScore:
    score: float
    weight: float
    confidence: float


class CorrelationScorer:
    """Versioned deterministic scoring policy for graph correlation edges and clusters."""

    score_version = CORRELATION_SCORE_VERSION

    def shared_entity_edge(self, shared_count: int) -> EdgeScore:
        weight = min(1.0, 0.35 + shared_count * 0.15)
        return EdgeScore(
            score=round(shared_count * 1.5 + weight, 4),
            weight=weight,
            confidence=min(1.0, 0.5 + shared_count * 0.1),
        )

    def vector_edge(self, similarity: float) -> EdgeScore:
        return EdgeScore(
            score=round(similarity * 10.0, 4),
            weight=min(1.0, 0.25 + similarity * 0.75),
            confidence=min(1.0, similarity),
        )

    def facet_contribution(
        self,
        *,
        shared_weight: float,
        facet_frequency: int,
        memory_count: int,
    ) -> float:
        facet_idf = math.log((memory_count + 1) / (facet_frequency + 0.5)) + 1.0
        return shared_weight * facet_idf

    def facet_edge(self, score: float) -> EdgeScore:
        return EdgeScore(
            score=round(score, 4),
            weight=min(1.0, 0.25 + score * 0.12),
            confidence=min(1.0, 0.35 + score * 0.12),
        )

    def score_facets(self, ranked_scored_facets: list[tuple[str, float]]) -> float:
        return sum(facet_score for _, facet_score in ranked_scored_facets[:6])

    def is_meaningful_facet_correlation(
        self,
        *,
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

    def max_facet_frequency(self, facet: str, memory_count: int) -> int:
        if facet.startswith("context:"):
            return 0
        if facet.startswith("phrase:"):
            return min(10, max(3, memory_count // 8))
        if facet.startswith("term:"):
            return min(12, max(3, memory_count // 8))
        return min(8, max(2, memory_count // 12))

    def edge_rank(self, edge: GraphEdge) -> float:
        metadata_score = edge.metadata.get("score")
        if isinstance(metadata_score, int | float):
            return float(metadata_score)
        shared_entities = edge.metadata.get("shared_entities")
        if isinstance(shared_entities, list):
            return len(shared_entities) * 1.5 + edge.weight
        return edge.weight + (edge.confidence or 0.0)

    def group_score(
        self,
        *,
        average_rank: float,
        cohesion: float,
        separation: float,
        member_count: int,
    ) -> float:
        return average_rank * (0.65 + cohesion) * (0.65 + separation) * math.log2(member_count + 1)

    def aggregate_confidence(self, cohesion: float) -> float:
        return min(0.95, max(0.62, 0.55 + cohesion * 0.25))

    def member_link_confidence(self, cohesion: float) -> float:
        return max(0.5, cohesion)

    def metadata(self, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = {"score_version": self.score_version}
        if extra:
            metadata.update(extra)
        return metadata
