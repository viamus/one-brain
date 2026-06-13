from __future__ import annotations

import re
from typing import Any

from onebrain.core.common.text import normalize_name

CORRELATION_STOPWORDS = {
    "about",
    "above",
    "active",
    "after",
    "again",
    "against",
    "also",
    "always",
    "ambevtech",
    "and",
    "antes",
    "are",
    "area",
    "areas",
    "available",
    "based",
    "because",
    "been",
    "being",
    "body",
    "branch",
    "browser",
    "cada",
    "caso",
    "catalog",
    "codex",
    "com",
    "como",
    "configura",
    "commit",
    "content",
    "context",
    "data",
    "description",
    "details",
    "deve",
    "does",
    "document",
    "dos",
    "ela",
    "ele",
    "eles",
    "essa",
    "esse",
    "esta",
    "este",
    "example",
    "examples",
    "feedback",
    "false",
    "file",
    "files",
    "fonte",
    "for",
    "from",
    "guidance",
    "had",
    "has",
    "have",
    "import",
    "imported",
    "inside",
    "into",
    "its",
    "manifest",
    "meta",
    "items",
    "json",
    "latest",
    "libraries",
    "library",
    "manual",
    "mais",
    "mas",
    "metadata",
    "memoria",
    "memory",
    "module",
    "must",
    "name",
    "nao",
    "not",
    "only",
    "onebrain",
    "options",
    "padr",
    "para",
    "pela",
    "pelo",
    "por",
    "private",
    "project",
    "que",
    "query",
    "read",
    "readme",
    "reference",
    "references",
    "repo",
    "repository",
    "required",
    "requires",
    "scope",
    "section",
    "sem",
    "ser",
    "should",
    "source",
    "status",
    "sua",
    "summary",
    "target",
    "the",
    "this",
    "text",
    "topic",
    "toolbox",
    "toolkit",
    "true",
    "under",
    "uma",
    "use",
    "used",
    "uses",
    "using",
    "value",
    "values",
    "when",
    "wiki",
    "with",
    "work",
}

GENERIC_MEMORY_TITLES = {
    "body",
    "document",
    "document body",
    "manifest",
    "readme",
}


def memory_correlation_facets(memory: Any) -> dict[str, float]:
    if is_low_signal_correlation_memory(memory):
        return {}

    facets: dict[str, float] = {}
    title_text = memory.title or ""
    metadata = memory.metadata_ or {}
    metadata_text = " ".join(str(value) for value in metadata.values() if value)
    content_text = memory.content[:6000]

    _add_weighted_terms(facets, title_text, term_weight=1.25, phrase_weight=1.5)
    _add_weighted_terms(facets, metadata_text, term_weight=0.95, phrase_weight=1.15)
    _add_weighted_terms(facets, content_text, term_weight=0.35, phrase_weight=0.0)
    for phrase in correlation_phrases(content_text[:2000]):
        facets[f"phrase:{phrase}"] = max(facets.get(f"phrase:{phrase}", 0.0), 0.45)

    for key, value in memory.scope.items():
        if (
            key not in {"project", "catalog", "source"}
            and isinstance(value, str | int | float | bool)
            and str(value).strip()
        ):
            facets[f"context:{key}={normalize_name(str(value))}"] = 0.25
    for tag in memory.tags:
        if is_generic_correlation_tag(tag):
            continue
        normalized_tag = normalize_name(tag.replace(":", " "))
        if tag.startswith(("library:", "source-type:")):
            facets[f"context:{normalized_tag}"] = 0.25
        else:
            facets[f"tag:{normalized_tag}"] = 0.55
            for term in correlation_terms(normalized_tag):
                facets[f"term:{term}"] = max(facets.get(f"term:{term}", 0.0), 0.5)
    if memory.source_type and memory.source_type not in {"manual", "file-import"}:
        facets[f"context:source_type={normalize_name(memory.source_type)}"] = 0.15
    return facets


def _add_weighted_terms(
    facets: dict[str, float],
    text: str,
    *,
    term_weight: float,
    phrase_weight: float,
) -> None:
    for term in correlation_terms(text):
        facets[f"term:{term}"] = max(facets.get(f"term:{term}", 0.0), term_weight)
    if phrase_weight <= 0:
        return
    for phrase in correlation_phrases(text):
        facets[f"phrase:{phrase}"] = max(facets.get(f"phrase:{phrase}", 0.0), phrase_weight)


def is_generic_correlation_tag(tag: str) -> bool:
    return tag in {"imported", "file-memory", "skill", "asset:skill"} or tag.startswith("ext:")


def is_low_signal_correlation_memory(memory: Any) -> bool:
    source_ref = (memory.source_ref or "").lower().replace("\\", "/")
    if source_ref.endswith("/library.json"):
        return True
    return normalize_name(memory.title or "") == "imported memory library"


def is_graph_memory(memory: Any) -> bool:
    metadata = memory.metadata_ or {}
    if "ingestion:child" in memory.tags:
        return False
    if metadata.get("ingestion_item_type") == "section":
        return False
    return True


def is_graph_entity(entity: Any) -> bool:
    return entity.entity_type != "source_document"


def correlation_terms(text: str, *, limit: int = 30) -> list[str]:
    normalized = normalize_name(text)
    terms: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", normalized):
        for term in re.split(r"[_-]+", raw):
            if not is_correlation_term(term) or term in seen:
                continue
            seen.add(term)
            terms.append(term)
            if len(terms) >= limit:
                return terms
    return terms


def correlation_phrases(text: str, *, limit: int = 16) -> list[str]:
    terms = correlation_terms(text, limit=80)
    phrases: list[str] = []
    seen: set[str] = set()
    for left, right in zip(terms, terms[1:], strict=False):
        if left == right:
            continue
        phrase = f"{left} {right}"
        if phrase in seen:
            continue
        seen.add(phrase)
        phrases.append(phrase)
        if len(phrases) >= limit:
            return phrases
    return phrases


def is_correlation_term(term: str) -> bool:
    return (
        len(term) >= 4
        and not term.isdigit()
        and term not in CORRELATION_STOPWORDS
        and not term.startswith("chunk")
    )
