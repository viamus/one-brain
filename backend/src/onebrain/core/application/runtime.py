from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from onebrain.core.application.service import OneBrainService
from onebrain.core.common.config import Settings
from onebrain.infrastructure.database import create_session_factory
from onebrain.infrastructure.embeddings import build_embedding_provider
from onebrain.infrastructure.vector_store import PgVectorMemoryStore


def build_service(settings: Settings, engine: AsyncEngine) -> OneBrainService:
    session_factory = create_session_factory(engine)
    return OneBrainService(
        settings=settings,
        session_factory=session_factory,
        embeddings=build_embedding_provider(settings),
        vector_store=PgVectorMemoryStore(settings, session_factory),
    )
