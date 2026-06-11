from __future__ import annotations

import asyncio
import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from onebrain_core.contracts.schemas import (
    GraphAggregationRequest,
    GraphRequest,
    SearchFilters,
)
from onebrain_django.runtime import close_runtime, get_runtime_service


class Command(BaseCommand):
    help = "Materialize graph grouping opportunities as aggregate OneBrain memories."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--query", default=None, help="Optional graph query.")
        parser.add_argument("--scope-json", default="{}", help="JSON scope filter for the graph.")
        parser.add_argument("--aggregate-scope-json", default=None, help="Optional scope override.")
        parser.add_argument("--memory-type", default="context", help="Memory type filter.")
        parser.add_argument("--limit", type=int, default=400, help="Memory limit for graph scan.")
        parser.add_argument("--correlation-limit", type=int, default=250)
        parser.add_argument("--max-degree", type=int, default=6)
        parser.add_argument("--grouping-limit", type=int, default=8)
        parser.add_argument("--grouping-min-size", type=int, default=3)
        parser.add_argument("--min-score", type=float, default=0.0)
        parser.add_argument("--source-type", default="graph-aggregation")
        parser.add_argument("--link-type", default="aggregates")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        asyncio.run(self._handle_async(options))

    async def _handle_async(self, options: dict[str, Any]) -> None:
        try:
            scope = _parse_json_object(options["scope_json"], "--scope-json")
            aggregate_scope = (
                _parse_json_object(options["aggregate_scope_json"], "--aggregate-scope-json")
                if options["aggregate_scope_json"]
                else {}
            )
            request = GraphAggregationRequest(
                graph=GraphRequest(
                    query=options["query"],
                    limit=options["limit"],
                    filters=SearchFilters(
                        memory_types=[options["memory_type"]] if options["memory_type"] else None,
                        scope=scope or None,
                    ),
                    include_entities=False,
                    include_relations=False,
                    include_correlations=True,
                    include_vector_correlations=True,
                    correlation_limit=options["correlation_limit"],
                    max_correlation_degree=options["max_degree"],
                    include_grouping_opportunities=True,
                    grouping_limit=options["grouping_limit"],
                    grouping_min_size=options["grouping_min_size"],
                ),
                min_score=options["min_score"],
                min_member_count=options["grouping_min_size"],
                dry_run=options["dry_run"],
                source_type=options["source_type"],
                link_type=options["link_type"],
                scope=aggregate_scope,
            )
            result = await get_runtime_service().materialize_grouping_opportunities(request)
        finally:
            await close_runtime()

        self.stdout.write(
            self.style.SUCCESS(
                "Graph aggregation scanned "
                f"{result.scanned} opportunities, created {result.created}, "
                f"existing {result.existing}, skipped {result.skipped}."
            )
        )
        for item in result.items:
            self.stdout.write(
                f"- {item.status}: {item.label} "
                f"members={item.member_count} score={item.score:.2f} "
                f"memory={item.memory_id or '-'} source_ref={item.source_ref or '-'}"
            )


def _parse_json_object(raw: str, option_name: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise CommandError(f"{option_name} must be a valid JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise CommandError(f"{option_name} must be a JSON object")
    return value
