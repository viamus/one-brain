from __future__ import annotations

import io

import pytest
from django.core.management import call_command
from onebrain_core.contracts.schemas import GraphAggregationResponse
from onebrain_jobs.graph_aggregation import GraphAggregationJobConfig
from onebrain_jobs.management.commands import aggregate_graph_memories, run_scheduled_jobs
from onebrain_jobs.scheduler import ScheduledJobConfig, run_scheduled_job
from onebrain_jobs.status import JOB_NAME_GRAPH_AGGREGATION, read_job_status


def test_graph_aggregation_job_config_builds_core_request() -> None:
    config = GraphAggregationJobConfig.from_options(
        {
            "scope_json": '{"project": "one-brain"}',
            "aggregate_scope_json": '{"project": "one-brain", "kind": "aggregate"}',
            "memory_type": "context",
            "limit": 500,
            "correlation_limit": 750,
            "max_degree": 12,
            "grouping_limit": 25,
            "grouping_min_size": 4,
            "min_score": 10,
            "dry_run": True,
            "source_type": "graph-aggregation",
            "link_type": "aggregates",
        }
    )

    request = config.to_request()

    assert request.dry_run is True
    assert request.min_member_count == 4
    assert request.min_score == 10
    assert request.graph.filters.scope == {"project": "one-brain"}
    assert request.graph.filters.memory_types == ["context"]
    assert request.graph.grouping_limit == 25
    assert request.scope == {"project": "one-brain", "kind": "aggregate"}


def test_aggregate_graph_memories_command_invokes_job(monkeypatch, tmp_path) -> None:
    captured = {}
    status_path = tmp_path / "jobs.json"
    monkeypatch.setenv("ONEBRAIN_JOB_STATUS_PATH", str(status_path))

    class FakeJob:
        async def run_once(self, config):
            captured["config"] = config
            return GraphAggregationResponse(dry_run=True, graph_memory_count=10, scanned=2)

    monkeypatch.setattr(aggregate_graph_memories, "GraphAggregationJob", lambda: FakeJob())

    stdout = io.StringIO()
    call_command(
        "aggregate_graph_memories",
        "--scope-json",
        '{"project": "one-brain"}',
        "--dry-run",
        stdout=stdout,
    )

    assert captured["config"].dry_run is True
    assert captured["config"].scope == {"project": "one-brain"}
    assert "scanned 2 opportunities" in stdout.getvalue()
    status = read_job_status(JOB_NAME_GRAPH_AGGREGATION, path=status_path)
    assert status is not None
    assert status["status"] == "success"
    assert status["result"]["scanned"] == 2


@pytest.mark.asyncio
async def test_run_scheduled_job_runs_max_runs_without_final_sleep() -> None:
    calls = []
    sleeps = []

    async def run_once():
        calls.append("run")
        return len(calls)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    await run_scheduled_job(
        config=ScheduledJobConfig(interval_seconds=5, max_runs=2),
        run_once=run_once,
        sleep=fake_sleep,
    )

    assert calls == ["run", "run"]
    assert sleeps == [5]


@pytest.mark.asyncio
async def test_run_scheduled_job_reports_start_and_error() -> None:
    starts = []
    errors = []

    async def run_once():
        raise RuntimeError("broken")

    with pytest.raises(RuntimeError, match="broken"):
        await run_scheduled_job(
            config=ScheduledJobConfig(interval_seconds=5, max_runs=1),
            run_once=run_once,
            on_start=lambda run_count, started_at: starts.append((run_count, started_at)),
            on_error=lambda exc, run_count, started_at: errors.append(
                (str(exc), run_count, started_at)
            ),
        )

    assert starts
    assert errors == [("broken", 1, starts[0][1])]


def test_run_scheduled_jobs_command_invokes_graph_aggregation(monkeypatch, tmp_path) -> None:
    captured = {}
    status_path = tmp_path / "jobs.json"
    monkeypatch.setenv("ONEBRAIN_JOB_STATUS_PATH", str(status_path))

    class FakeJob:
        async def run_once(self, config):
            captured["config"] = config
            return GraphAggregationResponse(dry_run=True, graph_memory_count=10, scanned=1)

    monkeypatch.setattr(run_scheduled_jobs, "GraphAggregationJob", lambda: FakeJob())

    stdout = io.StringIO()
    call_command(
        "run_scheduled_jobs",
        "--job",
        "graph-aggregation",
        "--scope-json",
        '{"project": "one-brain"}',
        "--dry-run",
        "--interval-seconds",
        "0",
        "--max-runs",
        "1",
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert captured["config"].scope == {"project": "one-brain"}
    assert captured["config"].dry_run is True
    assert "Starting scheduled job graph-aggregation" in output
    assert "scanned 1 opportunities" in output
    status = read_job_status(JOB_NAME_GRAPH_AGGREGATION, path=status_path)
    assert status is not None
    assert status["run_count"] == 1
    assert status["status"] == "success"
