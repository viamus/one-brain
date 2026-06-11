from __future__ import annotations

import json

import pytest
from django.test import Client

from onebrain_core.config import Settings
from onebrain_core.schemas import GraphResponse, SearchResponse
from onebrain_django.runtime import clear_runtime_overrides, set_runtime_overrides

API_PREFIX = "/api/v1"


class FakeDjangoService:
    async def health(self) -> dict[str, bool]:
        return {"database": True, "qdrant": True}

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
    assert response.json() == {"database": True, "qdrant": True}


def test_django_post_requires_api_key() -> None:
    response = Client().post(
        f"{API_PREFIX}/search",
        data=json.dumps({"query": "django"}),
        content_type="application/json",
    )

    assert response.status_code == 401


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
