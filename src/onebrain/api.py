from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import ORJSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from onebrain.config import Settings, get_settings
from onebrain.db import create_engine, create_session_factory
from onebrain.embeddings import build_embedding_provider
from onebrain.logging import configure_logging
from onebrain.schemas import (
    ContextPack,
    ContextRequest,
    CorrelationRequest,
    CorrelationResponse,
    MemoryCreate,
    MemoryOut,
    SearchRequest,
    SearchResponse,
)
from onebrain.service import OneBrainService
from onebrain.vector_store import QdrantMemoryStore


def _build_service(settings: Settings, engine: AsyncEngine) -> OneBrainService:
    return OneBrainService(
        settings=settings,
        session_factory=create_session_factory(engine),
        embeddings=build_embedding_provider(settings),
        vector_store=QdrantMemoryStore(settings),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    service = _build_service(settings, engine)
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


@app.post("/v1/memories", response_model=MemoryOut, dependencies=[Depends(require_api_key)])
async def capture_memory(
    payload: MemoryCreate,
    service: Annotated[OneBrainService, Depends(get_service)],
) -> MemoryOut:
    try:
        return await service.capture_memory(payload, actor="http")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
