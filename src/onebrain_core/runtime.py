from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from onebrain_core.config import Settings
from onebrain_core.db import create_session_factory
from onebrain_core.embeddings import build_embedding_provider
from onebrain_core.service import OneBrainService
from onebrain_core.vector_store import QdrantMemoryStore


def build_service(settings: Settings, engine: AsyncEngine) -> OneBrainService:
    return OneBrainService(
        settings=settings,
        session_factory=create_session_factory(engine),
        embeddings=build_embedding_provider(settings),
        vector_store=QdrantMemoryStore(settings),
    )
