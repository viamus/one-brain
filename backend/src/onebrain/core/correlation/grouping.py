from __future__ import annotations

import re
from collections import defaultdict
from hashlib import sha256

from onebrain.core.common.text import normalize_name
from onebrain.core.contracts.schemas import GraphEdge, GraphGroupingOpportunity, GraphNode
from onebrain.core.correlation.features import correlation_terms, is_correlation_term
from onebrain.core.correlation.scoring import CorrelationScorer


class CorrelationGroupingBuilder:
    """Build deterministic grouping opportunities from scored correlation edges."""

    def __init__(self, scorer: CorrelationScorer | None = None) -> None:
        self._scorer = scorer or CorrelationScorer()

    def build(
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
                key=lambda item: (-self._scorer.edge_rank(item), item.id),
            )
            member_ids = {seed}
            max_member_count = max(min_size, min(12, min_size + 6))
            for edge in ranked_edges:
                member_ids.add(edge.target if edge.source == seed else edge.source)
                if len(member_ids) >= max_member_count:
                    break
            if len(member_ids) < min_size:
                continue
            candidate = self.opportunity_for_members(
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
            if any(jaccard(candidate_members, members) >= 0.72 for members in selected_members):
                continue
            selected.append(candidate)
            selected_members.append(candidate_members)
            if len(selected) >= limit:
                break
        return selected

    def opportunity_for_members(
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
        internal_rank = sum(self._scorer.edge_rank(edge) for edge in internal_edges)
        average_rank = internal_rank / max(1, len(internal_edges))
        cohesion = min(1.0, (len(internal_edges) / possible_edges) * 1.8)
        separation = len(internal_edges) / max(1, len(internal_edges) + external_edges)
        score = self._scorer.group_score(
            average_rank=average_rank,
            cohesion=cohesion,
            separation=separation,
            member_count=len(member_ids),
        )

        keywords = self.grouping_keywords(nodes, internal_edges, member_ids)
        label = grouping_label(keywords, nodes[centroid_node_id].label)
        digest = sha256("|".join(sorted(member_ids)).encode("utf-8")).hexdigest()[:12]
        reasons = grouping_reasons(internal_edges)
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
                "score_version": self._scorer.score_version,
            },
        )

    def grouping_keywords(
        self,
        nodes: dict[str, GraphNode],
        internal_edges: list[GraphEdge],
        member_ids: set[str],
    ) -> list[str]:
        weights: defaultdict[str, float] = defaultdict(float)
        for edge in internal_edges:
            rank = self._scorer.edge_rank(edge)
            facets = edge.metadata.get("shared_facets")
            entities = edge.metadata.get("shared_entities")
            facet_values = facets if isinstance(facets, list) else []
            entity_values = entities if isinstance(entities, list) else []
            for facet in facet_values:
                keyword = keyword_from_grouping_facet(str(facet))
                if keyword:
                    weights[keyword] += rank
            for entity in entity_values:
                keyword = humanize_grouping_keyword(str(entity))
                if keyword:
                    weights[keyword] += rank * 0.8

        for node_id in member_ids:
            for term in correlation_terms(nodes[node_id].label, limit=8):
                weights[humanize_grouping_keyword(term)] += 0.35

        return [
            keyword
            for keyword, _ in sorted(
                weights.items(),
                key=lambda item: (-item[1], item[0]),
            )[:8]
        ]


def keyword_from_grouping_facet(facet: str) -> str | None:
    if ":" not in facet:
        return None
    prefix, value = facet.split(":", 1)
    if prefix not in {"term", "phrase", "tag"}:
        return None
    return humanize_grouping_keyword(value)


def humanize_grouping_keyword(value: str) -> str:
    tokens = [
        token
        for token in re.split(r"[\s_:/=-]+", normalize_name(value))
        if is_correlation_term(token)
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


def grouping_label(keywords: list[str], fallback: str) -> str:
    if keywords:
        return f"{' / '.join(keywords[:3])} Cluster"
    return f"{fallback} Cluster"


def grouping_reasons(internal_edges: list[GraphEdge]) -> list[str]:
    reasons: set[str] = set()
    for edge in internal_edges:
        raw_reasons = edge.metadata.get("reasons")
        if isinstance(raw_reasons, list):
            reasons.update(str(reason) for reason in raw_reasons)
        elif edge.label:
            reasons.add(edge.label)
    return sorted(reasons)


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
