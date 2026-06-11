from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from onebrain_core.graph_ui import graph_view_html
from onebrain_core.schemas import GraphRequest
from onebrain_django.http import (
    error_response,
    json_response,
    maybe_await,
    parse_body_or_error,
    validate_payload,
)
from onebrain_django.runtime import get_runtime_service


async def healthz(_request: HttpRequest) -> JsonResponse:
    return json_response({"status": "ok"})


async def readyz(_request: HttpRequest) -> JsonResponse:
    try:
        return json_response(await maybe_await(get_runtime_service().health()))
    except Exception as exc:
        return error_response(str(exc), status=503)


async def graph_view(_request: HttpRequest) -> HttpResponse:
    return HttpResponse(graph_view_html(), content_type="text/html; charset=utf-8")


@csrf_exempt
async def graph_data(request: HttpRequest) -> JsonResponse:
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(GraphRequest, body)
    if isinstance(payload, JsonResponse):
        return payload
    return json_response(await maybe_await(get_runtime_service().build_graph(payload)))
