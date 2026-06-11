from __future__ import annotations

import inspect
import json
import secrets
import uuid
from collections.abc import Awaitable
from json import JSONDecodeError
from typing import Any, TypeVar

from django.http import HttpRequest, JsonResponse
from pydantic import BaseModel, ValidationError

from onebrain_core.config import Settings

T = TypeVar("T")


def parse_json_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, JSONDecodeError) as exc:
        raise ValueError("malformed JSON body") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def json_response(payload: Any, *, status: int = 200) -> JsonResponse:
    return JsonResponse(to_jsonable(payload), safe=not isinstance(payload, list), status=status)


def error_response(detail: Any, *, status: int) -> JsonResponse:
    return json_response({"detail": detail}, status=status)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [to_jsonable(item) for item in value]
    return value


def validate_payload(model: type[T], payload: dict[str, Any]) -> T | JsonResponse:
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        return error_response(exc.errors(), status=422)


def parse_body_or_error(request: HttpRequest) -> dict[str, object] | JsonResponse:
    try:
        return parse_json_body(request)
    except ValueError as exc:
        return error_response(str(exc), status=400)


async def maybe_await(value: T | Awaitable[T]) -> T:
    if inspect.isawaitable(value):
        return await value
    return value


def require_api_key(request: HttpRequest, settings: Settings) -> JsonResponse | None:
    accepted_keys = settings.api_key_values
    if not accepted_keys:
        return None

    authorization = request.headers.get("Authorization", "")
    candidate = request.headers.get("X-API-Key", "")
    if authorization.lower().startswith("bearer "):
        candidate = authorization[7:].strip()
    if not candidate:
        return error_response("missing API key", status=401)
    if not any(secrets.compare_digest(candidate, key) for key in accepted_keys):
        return error_response("invalid API key", status=403)
    return None
