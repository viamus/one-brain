from __future__ import annotations

from onebrain.core.common.text import extract_heuristic_entities, normalize_name, scope_matches


def test_normalize_name_removes_accents_and_extra_spaces() -> None:
    assert normalize_name("  Memória   Técnica  ") == "memoria tecnica"


def test_scope_matches_requires_all_requested_pairs() -> None:
    assert scope_matches({"project": "one-brain", "team": "ai"}, {"project": "one-brain"})
    assert not scope_matches({"project": "other"}, {"project": "one-brain"})


def test_extract_heuristic_entities_is_conservative() -> None:
    assert extract_heuristic_entities("Use `pgvector` for #vector-search.") == [
        ("pgvector", "concept"),
        ("vector-search", "tag"),
    ]
