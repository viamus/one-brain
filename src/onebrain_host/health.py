from __future__ import annotations

from django.http import HttpRequest, JsonResponse

from onebrain_host.http import error_response, json_response, maybe_await
from onebrain_host.runtime import get_runtime_service


async def healthz(_request: HttpRequest) -> JsonResponse:
    return json_response({"status": "ok"})


async def readyz(_request: HttpRequest) -> JsonResponse:
    try:
        return json_response(await maybe_await(get_runtime_service().health()))
    except Exception as exc:
        return error_response(str(exc), status=503)
