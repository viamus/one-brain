from __future__ import annotations

import json

import pytest
from django.test import Client
from onebrain.core.common.config import Settings
from onebrain.core.contracts.schemas import GraphResponse, SearchResponse
from onebrain.platform.runtime import clear_runtime_overrides, set_runtime_overrides
from onebrain.workers.status import JOB_NAME_GRAPH_AGGREGATION, write_job_status

API_PREFIX = "/api/v1"


class FakeDjangoService:
    async def health(self) -> dict[str, bool]:
        return {"database": True, "vector_store": True}

    async def search(self, _payload) -> SearchResponse:
        return SearchResponse(query="django", hits=[])

    async def build_graph(self, payload) -> GraphResponse:
        return GraphResponse(
            query=payload.query,
            nodes=[],
            edges=[],
            memory_count=0,
            entity_count=0,
        )


@pytest.fixture(autouse=True)
def runtime_overrides():
    set_runtime_overrides(settings=Settings(api_keys="secret"), service=FakeDjangoService())
    yield
    clear_runtime_overrides()


def test_django_readyz_is_public_even_when_api_keys_are_configured() -> None:
    response = Client().get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"database": True, "vector_store": True}


def test_django_home_serves_workbench_even_when_api_keys_are_configured() -> None:
    response = Client().get("/")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="root"' in content
    assert "OneBrain Web" in content


def test_django_openapi_json_is_public_and_describes_secured_api() -> None:
    response = Client().get("/api/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["openapi"] == "3.1.0"
    assert payload["info"]["title"] == "OneBrain API"
    assert "/api/v1/search" in payload["paths"]
    assert "/api/v1/graph" in payload["paths"]
    assert "/api/v1/jobs/graph-aggregation/status" in payload["paths"]
    assert "ApiKeyAuth" in payload["components"]["securitySchemes"]
    assert "BearerAuth" in payload["components"]["securitySchemes"]
    assert payload["paths"]["/api/v1/search"]["post"]["security"] == [
        {"ApiKeyAuth": []},
        {"BearerAuth": []},
    ]


def test_django_post_requires_api_key() -> None:
    response = Client().post(
        f"{API_PREFIX}/search",
        data=json.dumps({"query": "django"}),
        content_type="application/json",
    )

    assert response.status_code == 401


def test_django_graph_aggregation_job_status_is_public(monkeypatch, tmp_path) -> None:
    status_path = tmp_path / "jobs.json"
    monkeypatch.setenv("ONEBRAIN_JOB_STATUS_PATH", str(status_path))
    write_job_status(
        JOB_NAME_GRAPH_AGGREGATION,
        {
            "status": "success",
            "run_count": 3,
            "started_at": "2026-06-11T10:00:00+00:00",
            "finished_at": "2026-06-11T10:00:02+00:00",
            "duration_seconds": 2,
            "scheduler": {"interval_seconds": 3600},
            "configuration": {"limit": 500},
            "result": {"scanned": 8, "created": 2, "existing": 1, "skipped": 5},
            "error": None,
        },
    )

    response = Client().get(f"{API_PREFIX}/jobs/graph-aggregation/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["last_run"]["run_count"] == 3
    assert payload["configuration"]["limit"] == 500
    assert payload["configuration"]["scoring_profile"] == "deterministic-v1"
    assert any(
        profile["key"] == "logistic-regression-v1" for profile in payload["scoring_profiles"]
    )


def test_django_post_accepts_bearer_api_key() -> None:
    response = Client().post(
        f"{API_PREFIX}/search",
        data=json.dumps({"query": "django"}),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer secret",
    )

    assert response.status_code == 200
    assert response.json() == {"query": "django", "hits": []}


def test_django_rejects_malformed_json() -> None:
    response = Client().post(
        f"{API_PREFIX}/search",
        data="{broken",
        content_type="application/json",
        HTTP_X_API_KEY="secret",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "malformed JSON body"


def test_django_graph_query_rejects_invalid_limit() -> None:
    response = Client().get(f"{API_PREFIX}/graph?limit=abc", HTTP_X_API_KEY="secret")

    assert response.status_code == 400
    assert response.json()["detail"] == "limit must be an integer"


def test_django_graph_query_rejects_limit_out_of_range() -> None:
    response = Client().get(f"{API_PREFIX}/graph?limit=9999", HTTP_X_API_KEY="secret")

    assert response.status_code == 422


def test_django_legacy_v1_alias_still_routes_to_django_api() -> None:
    response = Client().post(
        "/v1/search",
        data=json.dumps({"query": "django"}),
        content_type="application/json",
        HTTP_X_API_KEY="secret",
    )

    assert response.status_code == 200
    assert response.json() == {"query": "django", "hits": []}


def test_django_graph_data_stays_public_for_local_visualization() -> None:
    set_runtime_overrides(settings=Settings(api_keys="secret"), service=FakeDjangoService())
    response = Client().post(
        "/graph/data",
        data=json.dumps({"query": "django"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["query"] == "django"
