from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from onebrain_core.application.service import OneBrainService
from onebrain_core.common.config import Settings
from onebrain_infra.database import create_session_factory
from onebrain_infra.embeddings import build_embedding_provider
from onebrain_infra.vector_store import PgVectorMemoryStore


def build_service(settings: Settings, engine: AsyncEngine) -> OneBrainService:
    session_factory = create_session_factory(engine)
    return OneBrainService(
        settings=settings,
        session_factory=session_factory,
        embeddings=build_embedding_provider(settings),
        vector_store=PgVectorMemoryStore(settings, session_factory),
    )
