from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

import structlog

from onebrain_core.common.config import Settings

TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
LOGGER = structlog.get_logger(__name__)


class EmbeddingProvider(Protocol):
    dimension: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class HashEmbeddingProvider:
    """Deterministic local embeddings for offline operation and repeatable tests.

    This is not a replacement for a semantic embedding model, but it keeps the service
    fully non-LLM and gives pgvector a stable vector representation.
    """

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = TOKEN_RE.findall(text.lower())
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class FastEmbedProvider:
    def __init__(self, model_name: str, dimension: int) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "fastembed is not installed. Install the semantic extra or use "
                "ONEBRAIN_EMBEDDING_PROVIDER=hash."
            ) from exc

        self.dimension = dimension
        self._model = TextEmbedding(model_name=model_name)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed_sync, list(texts))

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        vectors = [list(vector) for vector in self._model.embed(texts)]
        for vector in vectors:
            if len(vector) != self.dimension:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
                )
        return vectors


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        dimension: int,
        timeout_seconds: float,
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("openai is not installed") from exc

        if not api_key:
            raise RuntimeError("OpenAI embeddings require ONEBRAIN_OPENAI_API_KEY")

        self.dimension = dimension
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        request: dict[str, object] = {
            "model": self._model,
            "input": [text.replace("\n", " ") for text in texts],
            "encoding_format": "float",
        }
        if self._model.startswith("text-embedding-3"):
            request["dimensions"] = self.dimension
        LOGGER.info(
            "embedding.request",
            provider="openai",
            model=self._model,
            dimensions=self.dimension,
            input_count=len(texts),
        )
        response = await self._client.embeddings.create(**request)
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        for vector in vectors:
            if len(vector) != self.dimension:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
                )
        LOGGER.info(
            "embedding.response",
            provider="openai",
            model=self._model,
            dimensions=self.dimension,
            vector_count=len(vectors),
        )
        return vectors


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dimension=settings.vector_size,
            timeout_seconds=settings.request_timeout_seconds,
        )
    if settings.embedding_provider == "fastembed":
        return FastEmbedProvider(settings.embedding_model, settings.vector_size)
    return HashEmbeddingProvider(settings.vector_size)
