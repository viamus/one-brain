from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

BACKTICK_ENTITY_RE = re.compile(r"`([^`\n]{2,120})`")
HASHTAG_RE = re.compile(r"(?<!\w)#([\w-]{2,80})")


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", normalized)


def content_hash(content: str, scope: dict[str, Any]) -> str:
    hasher = hashlib.sha256()
    hasher.update(content.strip().encode("utf-8"))
    hasher.update(repr(sorted(scope.items())).encode("utf-8"))
    return hasher.hexdigest()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def scope_matches(candidate: dict[str, Any], wanted: dict[str, Any] | None) -> bool:
    if not wanted:
        return True
    return all(candidate.get(key) == value for key, value in wanted.items())


def extract_heuristic_entities(content: str) -> list[tuple[str, str]]:
    entities: set[tuple[str, str]] = set()
    for match in BACKTICK_ENTITY_RE.findall(content):
        entities.add((match.strip(), "concept"))
    for match in HASHTAG_RE.findall(content):
        entities.add((match.strip(), "tag"))
    return sorted(entities)
