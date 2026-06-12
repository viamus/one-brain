from __future__ import annotations

import pytest
from onebrain.core.common.config import Settings
from onebrain.infrastructure.vector_store import PgVectorMemoryStore, build_memory_filter_clause


def test_pgvector_filter_clause_maps_canonical_memory_filters() -> None:
    clause = build_memory_filter_clause(
        {
            "status": ["active"],
            "memory_type": ["context", "skill"],
            "tags": ["graph:aggregate", "team:platform"],
            "scope.catalog": "private-engineering-catalog",
        }
    )

    assert clause.sql == (
        "WHERE m.status IN (:status_0) "
        "AND m.memory_type IN (:memory_type_0, :memory_type_1) "
        "AND m.tags ?| ARRAY[:tag_0, :tag_1] "
        "AND m.scope ->> :scope_key_5 = :scope_value_5"
    )
    assert clause.parameters == {
        "status_0": "active",
        "memory_type_0": "context",
        "memory_type_1": "skill",
        "tag_0": "graph:aggregate",
        "tag_1": "team:platform",
        "scope_key_5": "catalog",
        "scope_value_5": "private-engineering-catalog",
    }


def test_pgvector_store_rejects_invalid_table_identifier() -> None:
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        PgVectorMemoryStore(Settings(vector_table="memory_vectors; drop table memories"), None)  # type: ignore[arg-type]
