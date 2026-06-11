from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, ORJSONResponse

from onebrain.config import Settings, get_settings
from onebrain.db import create_engine
from onebrain.graph_ui import graph_view_html
from onebrain.logging import configure_logging
from onebrain.runtime import build_service
from onebrain.schemas import (
    ContextPack,
    ContextRequest,
    CorrelationRequest,
    CorrelationResponse,
    GraphRequest,
    GraphResponse,
    MemoryCreate,
    MemoryOut,
    MemoryType,
    SearchFilters,
    SearchRequest,
    SearchResponse,
    SkillCreate,
)
from onebrain.service import OneBrainService
from onebrain.skills import harden_skill_payload


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    service = build_service(settings, engine)
    app.state.settings = settings
    app.state.engine = engine
    app.state.service = service
    yield
    await engine.dispose()


app = FastAPI(
    title="OneBrain",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)


def get_service(request: Request) -> OneBrainService:
    return request.app.state.service


def get_runtime_settings(request: Request) -> Settings:
    return request.app.state.settings


async def require_api_key(
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.api_key_values:
        return
    candidate = x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        candidate = authorization[7:].strip()
    if not candidate:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing API key")
    if not any(secrets.compare_digest(candidate, key) for key in settings.api_key_values):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid API key")


Auth = Annotated[None, Depends(require_api_key)]


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(service: Annotated[OneBrainService, Depends(get_service)]) -> dict[str, bool]:
    try:
        return await service.health()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/graph", response_class=HTMLResponse)
async def graph_view() -> HTMLResponse:
    return HTMLResponse(graph_view_html())


@app.post("/v1/memories", response_model=MemoryOut, dependencies=[Depends(require_api_key)])
async def capture_memory(
    payload: MemoryCreate,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> MemoryOut:
    try:
        return await service.capture_memory(payload, actor="http")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/v1/skills", response_model=MemoryOut, dependencies=[Depends(require_api_key)])
async def capture_skill(
    payload: SkillCreate,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> MemoryOut:
    try:
        hardened = harden_skill_payload(payload.model_dump(mode="json"))
        source_ref = hardened.payload.get("source", {}).get("source_ref")
        if source_ref:
            try:
                return await service.get_memory_by_source_ref(str(source_ref))
            except KeyError:
                pass
        return await service.capture_memory(
            MemoryCreate.model_validate(hardened.payload), actor="http"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/v1/memories/by-source", response_model=MemoryOut, dependencies=[Depends(require_api_key)]
)
async def get_memory_by_source_ref(
    source_ref: str,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> MemoryOut:
    try:
        return await service.get_memory_by_source_ref(source_ref)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/v1/memories/{memory_id}", response_model=MemoryOut, dependencies=[Depends(require_api_key)]
)
async def get_memory(
    memory_id: str,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> MemoryOut:
    try:
        import uuid

        return await service.get_memory(uuid.UUID(memory_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid memory id") from exc


@app.post("/v1/search", response_model=SearchResponse, dependencies=[Depends(require_api_key)])
async def search(
    payload: SearchRequest,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> SearchResponse:
    return await service.search(payload)


@app.post(
    "/v1/skills/search", response_model=SearchResponse, dependencies=[Depends(require_api_key)]
)
async def search_skills(
    payload: SearchRequest,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> SearchResponse:
    filters = payload.filters.model_copy(update={"memory_types": ["skill"]})
    return await service.search(payload.model_copy(update={"filters": filters}))


@app.post("/v1/graph", response_model=GraphResponse, dependencies=[Depends(require_api_key)])
async def graph(
    payload: GraphRequest,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> GraphResponse:
    return await service.build_graph(payload)


@app.post("/graph/data", response_model=GraphResponse)
async def graph_data(
    payload: GraphRequest,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> GraphResponse:
    return await service.build_graph(payload)


@app.get("/v1/graph", response_model=GraphResponse, dependencies=[Depends(require_api_key)])
async def graph_query(
    service: Annotated[OneBrainService, Depends(get_service)],
    query: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    memory_type: MemoryType | None = None,
    tag: str | None = None,
) -> GraphResponse:
    filters = SearchFilters(
        memory_types=[memory_type] if memory_type else None,
        tags=[tag] if tag else None,
    )
    return await service.build_graph(GraphRequest(query=query, limit=limit, filters=filters))


@app.post("/v1/context", response_model=ContextPack, dependencies=[Depends(require_api_key)])
async def context_pack(
    payload: ContextRequest,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> ContextPack:
    return await service.compose_context(payload)


@app.post(
    "/v1/correlate", response_model=CorrelationResponse, dependencies=[Depends(require_api_key)]
)
async def correlate(
    payload: CorrelationRequest,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> CorrelationResponse:
    return await service.correlate(payload)


def run() -> None:
    uvicorn.run("onebrain.api:app", host="0.0.0.0", port=8080, reload=False)  # noqa: S104
