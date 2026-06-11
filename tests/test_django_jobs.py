from __future__ import annotations

import io

from django.core.management import call_command

from onebrain_core.contracts.schemas import GraphAggregationResponse
from onebrain_django.api.management.commands import aggregate_graph_memories


def test_aggregate_graph_memories_command_invokes_service(monkeypatch) -> None:
    captured = {}

    class FakeService:
        async def materialize_grouping_opportunities(self, request):
            captured["request"] = request
            return GraphAggregationResponse(dry_run=True, graph_memory_count=10, scanned=2)

    async def fake_close_runtime() -> None:
        captured["closed"] = True

    monkeypatch.setattr(aggregate_graph_memories, "get_runtime_service", lambda: FakeService())
    monkeypatch.setattr(aggregate_graph_memories, "close_runtime", fake_close_runtime)

    stdout = io.StringIO()
    call_command(
        "aggregate_graph_memories",
        "--scope-json",
        '{"project": "one-brain"}',
        "--dry-run",
        stdout=stdout,
    )

    request = captured["request"]
    assert request.dry_run is True
    assert request.graph.filters.scope == {"project": "one-brain"}
    assert request.graph.include_grouping_opportunities is True
    assert captured["closed"] is True
    assert "scanned 2 opportunities" in stdout.getvalue()
