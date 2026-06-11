from __future__ import annotations

import math

import pytest

from onebrain_core.infrastructure.embeddings import HashEmbeddingProvider


@pytest.mark.asyncio
async def test_hash_embedding_is_deterministic_and_normalized() -> None:
    provider = HashEmbeddingProvider(dimension=32)

    first = (await provider.embed(["OneBrain stores durable memories"]))[0]
    second = (await provider.embed(["OneBrain stores durable memories"]))[0]

    assert first == second
    assert len(first) == 32
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)
