from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ONEBRAIN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"
    api_keys: str = ""
    api_url: str = "http://localhost:8080"
    api_key: str = ""

    database_url: str = "postgresql+asyncpg://onebrain:onebrain@localhost:5432/onebrain"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "onebrain_memories"
    vector_size: int = 384

    embedding_provider: Literal["hash", "fastembed", "openai"] = "hash"
    embedding_model: str = "text-embedding-3-small"
    openai_api_key: str | None = None

    enable_heuristic_entity_extraction: bool = False
    max_context_tokens: int = 6000
    request_timeout_seconds: float = 15.0

    @property
    def api_key_values(self) -> list[str]:
        return [item.strip() for item in self.api_keys.split(",") if item.strip()]

    @property
    def outbound_api_key(self) -> str:
        if self.api_key.strip():
            return self.api_key.strip()
        values = self.api_key_values
        return values[0] if values else ""

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        if self.environment == "production" and not self.api_key_values:
            raise ValueError("ONEBRAIN_API_KEYS is required in production")
        if self.vector_size <= 0:
            raise ValueError("ONEBRAIN_VECTOR_SIZE must be positive")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
