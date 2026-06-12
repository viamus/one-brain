from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from onebrain.core.contracts.schemas import GraphRequest
from onebrain.platform.http import (
    json_response,
    maybe_await,
    parse_body_or_error,
    validate_payload,
)
from onebrain.platform.runtime import get_runtime_service

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[2]


async def graph_view(_request: HttpRequest) -> HttpResponse:
    return _react_index_response()


async def home_view(_request: HttpRequest) -> HttpResponse:
    return _react_index_response()


async def web_asset(_request: HttpRequest, asset_path: str) -> FileResponse:
    asset = _resolve_asset_path(asset_path)
    if asset is None:
        raise Http404("OneBrain Web asset not found")
    content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
    return FileResponse(asset.open("rb"), content_type=content_type)


@csrf_exempt
async def graph_data(request: HttpRequest) -> JsonResponse:
    body = parse_body_or_error(request)
    if isinstance(body, JsonResponse):
        return body
    payload = validate_payload(GraphRequest, body)
    if isinstance(payload, JsonResponse):
        return payload
    return json_response(await maybe_await(get_runtime_service().build_graph(payload)))


def _react_index_response() -> HttpResponse:
    index = _find_dist_file("index.html")
    if index is None:
        return HttpResponse(_missing_react_build_html(), content_type="text/html; charset=utf-8")
    return HttpResponse(index.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")


def _resolve_asset_path(asset_path: str) -> Path | None:
    for dist_dir in _dist_dirs():
        candidate = (dist_dir / asset_path).resolve()
        try:
            candidate.relative_to(dist_dir.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def _find_dist_file(file_name: str) -> Path | None:
    for dist_dir in _dist_dirs():
        candidate = dist_dir / file_name
        if candidate.is_file():
            return candidate
    return None


def _dist_dirs() -> list[Path]:
    configured = os.getenv("ONEBRAIN_WEB_DIST_DIR")
    dirs = []
    if configured:
        dirs.append(Path(configured))
    dirs.extend(
        [
            REPO_ROOT / "frontend" / "web" / "dist",
            PACKAGE_ROOT / "react_build",
        ]
    )
    return dirs


def _missing_react_build_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>OneBrain Web</title>
  </head>
  <body>
    <div id="root">
      <h1>OneBrain Web</h1>
      <p>React bundle not built yet. Run npm run web:build or use Docker build.</p>
    </div>
  </body>
</html>
"""
