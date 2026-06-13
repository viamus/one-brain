from __future__ import annotations

from collections import defaultdict
from typing import Any

from onebrain.core.contracts.schemas import GraphEdge, GraphNode
from onebrain.core.correlation.scoring import CorrelationScorer


class CorrelationPipeline:
    """Small graph-edge operations shared by graph building and aggregation."""

    def __init__(self, scorer: CorrelationScorer | None = None) -> None:
        self._scorer = scorer or CorrelationScorer()

    def add_edge_reason(self, edge: GraphEdge, reason: str) -> None:
        reasons = edge.metadata.get("reasons")
        if not isinstance(reasons, list):
            reasons = []
        edge.metadata["reasons"] = sorted({*reasons, reason})

    def edge_count(self, edges: dict[str, GraphEdge]) -> int:
        return sum(1 for edge in edges.values() if edge.edge_type == "correlation")

    def degree_by_memory(self, edges: dict[str, GraphEdge]) -> defaultdict[str, int]:
        degree_by_memory: defaultdict[str, int] = defaultdict(int)
        for edge in edges.values():
            if edge.edge_type != "correlation":
                continue
            degree_by_memory[self.node_memory_key(edge.source)] += 1
            degree_by_memory[self.node_memory_key(edge.target)] += 1
        return degree_by_memory

    def node_memory_key(self, node_id: str) -> str:
        if node_id.startswith("memory:"):
            return node_id.removeprefix("memory:")
        return node_id

    def prune_edges(
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
            key=lambda item: (-self._scorer.edge_rank(item), item.id),
        ):
            if len(kept) >= limit:
                break
            source = self.node_memory_key(edge.source)
            target = self.node_memory_key(edge.target)
            if degree_by_memory[source] >= max_degree or degree_by_memory[target] >= max_degree:
                continue
            kept.add(edge.id)
            degree_by_memory[source] += 1
            degree_by_memory[target] += 1

        for edge in correlation_edges:
            if edge.id not in kept:
                edges.pop(edge.id, None)

    def annotate_graph_insights(
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
            rank = self._scorer.edge_rank(edge)
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
