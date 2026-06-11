from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from onebrain.config import Settings
from onebrain.db import create_session_factory
from onebrain.embeddings import build_embedding_provider
from onebrain.service import OneBrainService
from onebrain.vector_store import QdrantMemoryStore


def build_service(settings: Settings, engine: AsyncEngine) -> OneBrainService:
    return OneBrainService(
        settings=settings,
        session_factory=create_session_factory(engine),
        embeddings=build_embedding_provider(settings),
        vector_store=QdrantMemoryStore(settings),
    )
