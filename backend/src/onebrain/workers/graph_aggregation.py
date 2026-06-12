from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from onebrain.core.contracts.schemas import (
    GraphAggregationRequest,
    GraphAggregationResponse,
    GraphRequest,
    SearchFilters,
)
from onebrain.platform.runtime import close_runtime, get_runtime_service

RuntimeCloser = Callable[[], Awaitable[None]]
ServiceFactory = Callable[[], Any]


@dataclass(frozen=True)
class GraphAggregationJobConfig:
    query: str | None = None
    scope: dict[str, Any] = field(default_factory=dict)
    aggregate_scope: dict[str, Any] = field(default_factory=dict)
    memory_type: str | None = "context"
    limit: int = 500
    correlation_limit: int = 750
    max_degree: int = 12
    grouping_limit: int = 25
    grouping_min_size: int = 3
    min_score: float = 0.0
    source_type: str = "graph-aggregation"
    link_type: str = "aggregates"
    dry_run: bool = False

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> GraphAggregationJobConfig:
        return cls(
            query=options.get("query") or None,
            scope=parse_json_object(options.get("scope_json") or "{}", "--scope-json"),
            aggregate_scope=parse_json_object(
                options.get("aggregate_scope_json") or "{}",
                "--aggregate-scope-json",
            ),
            memory_type=options.get("memory_type") or None,
            limit=int(options.get("limit") or 500),
            correlation_limit=int(options.get("correlation_limit") or 750),
            max_degree=int(options.get("max_degree") or 12),
            grouping_limit=int(options.get("grouping_limit") or 25),
            grouping_min_size=int(options.get("grouping_min_size") or 3),
            min_score=float(options.get("min_score") or 0.0),
            source_type=options.get("source_type") or "graph-aggregation",
            link_type=options.get("link_type") or "aggregates",
            dry_run=bool(options.get("dry_run")),
        )

    @classmethod
    def from_environment(cls) -> GraphAggregationJobConfig:
        return cls(
            query=os.getenv("ONEBRAIN_GRAPH_AGGREGATION_QUERY") or None,
            scope=parse_json_object(
                os.getenv("ONEBRAIN_GRAPH_AGGREGATION_SCOPE_JSON", "{}"),
                "ONEBRAIN_GRAPH_AGGREGATION_SCOPE_JSON",
            ),
            aggregate_scope=parse_json_object(
                os.getenv("ONEBRAIN_GRAPH_AGGREGATION_AGGREGATE_SCOPE_JSON", "{}"),
                "ONEBRAIN_GRAPH_AGGREGATION_AGGREGATE_SCOPE_JSON",
            ),
            memory_type=os.getenv("ONEBRAIN_GRAPH_AGGREGATION_MEMORY_TYPE", "context") or None,
            limit=int(os.getenv("ONEBRAIN_GRAPH_AGGREGATION_LIMIT", "500")),
            correlation_limit=int(os.getenv("ONEBRAIN_GRAPH_AGGREGATION_CORRELATION_LIMIT", "750")),
            max_degree=int(os.getenv("ONEBRAIN_GRAPH_AGGREGATION_MAX_DEGREE", "12")),
            grouping_limit=int(os.getenv("ONEBRAIN_GRAPH_AGGREGATION_GROUPING_LIMIT", "25")),
            grouping_min_size=int(os.getenv("ONEBRAIN_GRAPH_AGGREGATION_GROUPING_MIN_SIZE", "3")),
            min_score=float(os.getenv("ONEBRAIN_GRAPH_AGGREGATION_MIN_SCORE", "0")),
            source_type=os.getenv("ONEBRAIN_GRAPH_AGGREGATION_SOURCE_TYPE", "graph-aggregation"),
            link_type=os.getenv("ONEBRAIN_GRAPH_AGGREGATION_LINK_TYPE", "aggregates"),
            dry_run=os.getenv("ONEBRAIN_GRAPH_AGGREGATION_DRY_RUN", "false").lower()
            in {"1", "true", "yes"},
        )

    def to_request(self) -> GraphAggregationRequest:
        return GraphAggregationRequest(
            graph=GraphRequest(
                query=self.query,
                limit=self.limit,
                filters=SearchFilters(
                    memory_types=[self.memory_type] if self.memory_type else None,
                    scope=self.scope or None,
                ),
                include_entities=False,
                include_relations=False,
                include_correlations=True,
                include_vector_correlations=True,
                correlation_limit=self.correlation_limit,
                max_correlation_degree=self.max_degree,
                include_grouping_opportunities=True,
                grouping_limit=self.grouping_limit,
                grouping_min_size=self.grouping_min_size,
            ),
            min_score=self.min_score,
            min_member_count=self.grouping_min_size,
            dry_run=self.dry_run,
            source_type=self.source_type,
            link_type=self.link_type,
            scope=self.aggregate_scope,
        )


class GraphAggregationJob:
    def __init__(
        self,
        *,
        service_factory: ServiceFactory = get_runtime_service,
        runtime_closer: RuntimeCloser = close_runtime,
    ) -> None:
        self._service_factory = service_factory
        self._runtime_closer = runtime_closer

    async def run_once(self, config: GraphAggregationJobConfig) -> GraphAggregationResponse:
        try:
            return await self._service_factory().materialize_grouping_opportunities(
                config.to_request()
            )
        finally:
            await self._runtime_closer()


def add_graph_aggregation_arguments(parser) -> None:
    env_config = GraphAggregationJobConfig.from_environment()
    parser.add_argument("--query", default=env_config.query, help="Optional graph query.")
    parser.add_argument(
        "--scope-json",
        default=json.dumps(env_config.scope),
        help="JSON scope filter for the graph.",
    )
    parser.add_argument(
        "--aggregate-scope-json",
        default=json.dumps(env_config.aggregate_scope),
        help="Optional JSON scope override for aggregate memories.",
    )
    parser.add_argument("--memory-type", default=env_config.memory_type, help="Memory type filter.")
    parser.add_argument("--limit", type=int, default=env_config.limit, help="Memory scan limit.")
    parser.add_argument("--correlation-limit", type=int, default=env_config.correlation_limit)
    parser.add_argument("--max-degree", type=int, default=env_config.max_degree)
    parser.add_argument("--grouping-limit", type=int, default=env_config.grouping_limit)
    parser.add_argument("--grouping-min-size", type=int, default=env_config.grouping_min_size)
    parser.add_argument("--min-score", type=float, default=env_config.min_score)
    parser.add_argument("--source-type", default=env_config.source_type)
    parser.add_argument("--link-type", default=env_config.link_type)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=env_config.dry_run,
        help="Detect opportunities without creating aggregate memories.",
    )


def format_graph_aggregation_result(result: GraphAggregationResponse) -> list[str]:
    lines = [
        "Graph aggregation scanned "
        f"{result.scanned} opportunities, created {result.created}, "
        f"existing {result.existing}, skipped {result.skipped}."
    ]
    for item in result.items:
        lines.append(
            f"- {item.status}: {item.label} "
            f"members={item.member_count} score={item.score:.2f} "
            f"memory={item.memory_id or '-'} source_ref={item.source_ref or '-'}"
        )
    return lines


def parse_json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be a valid JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value
