from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings

from onebrain.core.contracts.schemas import GraphAggregationResponse
from onebrain.core.correlation import correlation_scoring_profiles_payload
from onebrain.workers.graph_aggregation import GraphAggregationJobConfig
from onebrain.workers.scheduler import ScheduledJobConfig

JOB_NAME_GRAPH_AGGREGATION = "graph-aggregation"


def job_status_path() -> Path:
    raw_path = os.getenv("ONEBRAIN_JOB_STATUS_PATH")
    if raw_path:
        return Path(raw_path)
    return Path(settings.BASE_DIR) / ".onebrain-jobs.json"


def read_job_status(job_name: str, *, path: Path | None = None) -> dict[str, Any] | None:
    payload = _read_status_file(path or job_status_path())
    value = payload.get(job_name)
    return value if isinstance(value, dict) else None


def write_job_status(
    job_name: str,
    status: dict[str, Any],
    *,
    path: Path | None = None,
) -> None:
    target = path or job_status_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_status_file(target)
    payload[job_name] = status
    temp_path = target.with_suffix(f"{target.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(target)


def scheduler_config_snapshot(config: ScheduledJobConfig) -> dict[str, Any]:
    return {
        "interval_seconds": config.interval_seconds,
        "max_runs": config.max_runs,
        "run_immediately": config.run_immediately,
    }


def graph_aggregation_config_snapshot(config: GraphAggregationJobConfig) -> dict[str, Any]:
    return {
        "query": config.query,
        "scope": config.scope,
        "aggregate_scope": config.aggregate_scope,
        "memory_type": config.memory_type,
        "scoring_profile": config.scoring_profile,
        "limit": config.limit,
        "correlation_limit": config.correlation_limit,
        "max_degree": config.max_degree,
        "grouping_limit": config.grouping_limit,
        "grouping_min_size": config.grouping_min_size,
        "min_score": config.min_score,
        "source_type": config.source_type,
        "link_type": config.link_type,
        "dry_run": config.dry_run,
    }


def graph_aggregation_result_snapshot(result: GraphAggregationResponse) -> dict[str, Any]:
    return {
        "dry_run": result.dry_run,
        "graph_memory_count": result.graph_memory_count,
        "scanned": result.scanned,
        "created": result.created,
        "existing": result.existing,
        "skipped": result.skipped,
    }


def running_status_payload(
    *,
    run_count: int,
    started_at: datetime,
    scheduler: dict[str, Any],
    configuration: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "running",
        "run_count": run_count,
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "duration_seconds": None,
        "scheduler": scheduler,
        "configuration": configuration,
        "result": None,
        "error": None,
    }


def finished_status_payload(
    *,
    run_count: int,
    started_at: datetime,
    finished_at: datetime,
    scheduler: dict[str, Any],
    configuration: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "success",
        "run_count": run_count,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "scheduler": scheduler,
        "configuration": configuration,
        "result": result,
        "error": None,
    }


def failed_status_payload(
    *,
    run_count: int,
    started_at: datetime,
    finished_at: datetime,
    scheduler: dict[str, Any],
    configuration: dict[str, Any],
    error: BaseException,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "run_count": run_count,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "scheduler": scheduler,
        "configuration": configuration,
        "result": None,
        "error": {
            "type": type(error).__name__,
            "message": str(error),
        },
    }


def graph_aggregation_status_response(
    *,
    scheduler: ScheduledJobConfig,
    configuration: GraphAggregationJobConfig,
    last_run: dict[str, Any] | None,
) -> dict[str, Any]:
    scheduler_payload = scheduler_config_snapshot(scheduler)
    config_payload = graph_aggregation_config_snapshot(configuration)
    status = str(last_run.get("status")) if last_run else "not_started"
    return {
        "job": JOB_NAME_GRAPH_AGGREGATION,
        "status": status,
        "command": "onebrain-jobs run_scheduled_jobs --job graph-aggregation",
        "scheduler": scheduler_payload,
        "configuration": config_payload,
        "scoring_profiles": correlation_scoring_profiles_payload(),
        "last_run": last_run,
        "next_run_at": _next_run_at(last_run, scheduler.interval_seconds),
    }


def _read_status_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _next_run_at(last_run: dict[str, Any] | None, interval_seconds: float) -> str | None:
    if not last_run or last_run.get("status") == "running":
        return None
    finished_at = last_run.get("finished_at")
    if not isinstance(finished_at, str) or not finished_at:
        return None
    try:
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return None
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=UTC)
    return (finished + timedelta(seconds=interval_seconds)).isoformat()
