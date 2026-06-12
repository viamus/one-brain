from __future__ import annotations

import os
import uuid

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from onebrain.core.application.skills import harden_skill_payload
from onebrain.core.contracts.schemas import (
    ContextRequest,
    CorrelationRequest,
    GraphRequest,
    IngestionAnalyzeRequest,
    IngestionCommitRequest,
    MemoryCreate,
    SearchFilters,
    SearchRequest,
    SkillCreate,
)
from onebrain.core.ingestion import analyze_memory_files, commit_ingestion_plan
from onebrain.interfaces.api.openapi import openapi_schema
from onebrain.platform.http import (
    error_response,
    json_response,
    maybe_await,
    parse_body_or_error,
    require_api_key,
    validate_payload,
)
from onebrain.platform.runtime import get_runtime_service, get_runtime_settings
from onebrain.workers.graph_aggregation import GraphAggregationJobConfig
from onebrain.workers.scheduler import ScheduledJobConfig
from onebrain.workers.status import (
    JOB_NAME_GRAPH_AGGREGATION,
    graph_aggregation_status_response,
    read_job_status,
)


async def openapi_json(_request: HttpRequest) -> JsonResponse:
    return json_response(openapi_schema())


async def graph_aggregation_job_status(_request: HttpRequest) -> JsonResponse:
    try:
        scheduler = ScheduledJobConfig(
            interval_seconds=float(
                os.getenv("ONEBRAIN_GRAPH_AGGREGATION_INTERVAL_SECONDS", "3600")
            ),
            max_runs=None,
            run_immediately=True,
        )
        configuration = GraphAggregationJobConfig.from_environment()
    except ValueError as exc:
        return error_response(str(exc), status=500)

    return json_response(
        graph_aggregation_status_response(
            scheduler=scheduler,
            configuration=configuration,
            last_run=read_job_status(JOB_NAME_GRAPH_AGGREGATION),
        )
    )


@csrf_exempt
async def capture_memory(request: HttpRequest) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(MemoryCreate, body)
    if isinstance(payload, JsonResponse):
        return payload
    try:
        memory = await maybe_await(get_runtime_service().capture_memory(payload, actor="django"))
        return json_response(memory)
    except Exception as exc:
        return error_response(str(exc), status=500)


@csrf_exempt
async def capture_skill(request: HttpRequest) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(SkillCreate, body)
    if isinstance(payload, JsonResponse):
        return payload

    service = get_runtime_service()
    try:
        hardened = harden_skill_payload(payload.model_dump(mode="json"))
        source_ref = hardened.payload.get("source", {}).get("source_ref")
        if source_ref:
            try:
                existing = await maybe_await(service.get_memory_by_source_ref(str(source_ref)))
                return json_response(existing)
            except KeyError:
                pass
        memory = await maybe_await(
            service.capture_memory(
                MemoryCreate.model_validate(hardened.payload),
                actor="django",
            )
        )
        return json_response(memory)
    except Exception as exc:
        return error_response(str(exc), status=500)


@csrf_exempt
async def analyze_ingestion(request: HttpRequest) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(IngestionAnalyzeRequest, body)
    if isinstance(payload, JsonResponse):
        return payload
    try:
        return json_response(analyze_memory_files(payload))
    except FileNotFoundError as exc:
        return error_response(str(exc), status=404)
    except Exception as exc:
        return error_response(str(exc), status=500)


@csrf_exempt
async def commit_ingestion(request: HttpRequest) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(IngestionCommitRequest, body)
    if isinstance(payload, JsonResponse):
        return payload
    try:
        result = await commit_ingestion_plan(get_runtime_service(), payload, actor="django")
        return json_response(result)
    except Exception as exc:
        return error_response(str(exc), status=500)


async def get_memory_by_source_ref(request: HttpRequest) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    source_ref = request.GET.get("source_ref")
    if not source_ref:
        return error_response("source_ref is required", status=400)
    try:
        memory = await maybe_await(get_runtime_service().get_memory_by_source_ref(source_ref))
        return json_response(memory)
    except KeyError as exc:
        return error_response(str(exc), status=404)


async def get_memory(request: HttpRequest, memory_id: str) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    try:
        memory = await maybe_await(get_runtime_service().get_memory(uuid.UUID(memory_id)))
        return json_response(memory)
    except ValueError:
        return error_response("invalid memory id", status=400)
    except KeyError as exc:
        return error_response(str(exc), status=404)


@csrf_exempt
async def search(request: HttpRequest) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(SearchRequest, body)
    if isinstance(payload, JsonResponse):
        return payload
    return json_response(await maybe_await(get_runtime_service().search(payload)))


@csrf_exempt
async def search_skills(request: HttpRequest) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(SearchRequest, body)
    if isinstance(payload, JsonResponse):
        return payload
    filters = payload.filters.model_copy(update={"memory_types": ["skill"]})
    response = await maybe_await(
        get_runtime_service().search(payload.model_copy(update={"filters": filters}))
    )
    return json_response(response)


@csrf_exempt
async def graph(request: HttpRequest) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    if request.method == "GET":
        return await graph_query(request)
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(GraphRequest, body)
    if isinstance(payload, JsonResponse):
        return payload
    return json_response(await maybe_await(get_runtime_service().build_graph(payload)))


async def graph_query(request: HttpRequest) -> JsonResponse:
    memory_type = request.GET.get("memory_type") or None
    filters = SearchFilters(
        memory_types=[memory_type] if memory_type else None,
        tags=[request.GET["tag"]] if request.GET.get("tag") else None,
    )
    try:
        payload = GraphRequest(
            query=request.GET.get("query") or None,
            limit=int(request.GET.get("limit") or 100),
            filters=filters,
        )
    except ValidationError as exc:
        return error_response(exc.errors(), status=422)
    except ValueError:
        return error_response("limit must be an integer", status=400)
    return json_response(await maybe_await(get_runtime_service().build_graph(payload)))


@csrf_exempt
async def context_pack(request: HttpRequest) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(ContextRequest, body)
    if isinstance(payload, JsonResponse):
        return payload
    return json_response(await maybe_await(get_runtime_service().compose_context(payload)))


@csrf_exempt
async def correlate(request: HttpRequest) -> JsonResponse:
    auth = require_api_key(request, get_runtime_settings())
    if auth is not None:
        return auth
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(CorrelationRequest, body)
    if isinstance(payload, JsonResponse):
        return payload
    return json_response(await maybe_await(get_runtime_service().correlate(payload)))
