from __future__ import annotations

from typing import Any

import pytest
from onebrain.core.application.memory_hardening import (
    build_file_memory_candidates,
    harden_memory_payload,
)
from onebrain.core.application.memory_importer import import_memory_files


class FakeMemoryClient:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.created: list[dict[str, Any]] = []

    async def get_memory_by_source_ref(self, source_ref: str) -> dict[str, Any] | None:
        if source_ref in self.existing:
            return {"id": "existing", "source_ref": source_ref}
        return None

    async def capture_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created.append(payload)
        memory_id = f"memory-{len(self.created)}"
        return {"id": memory_id, **payload}


def test_harden_memory_payload_redacts_and_defaults() -> None:
    result = harden_memory_payload(
        {
            "title": "x" * 260,
            "content": "Use api_key=super-secret for local smoke tests.",
        },
        default_scope={"project": "one-brain"},
        source_type="unit-test",
        source_ref="unit://memory",
    )

    assert result.redactions == 1
    assert "secret_redacted" in result.findings
    assert result.payload["memory_type"] == "note"
    assert result.payload["scope"] == {"project": "one-brain"}
    assert result.payload["source"] == {"source_type": "unit-test", "source_ref": "unit://memory"}
    assert "[REDACTED]" in result.payload["content"]
    assert len(result.payload["title"]) <= 240


def test_build_file_memory_candidates_uses_frontmatter_and_source_ref(tmp_path) -> None:
    library = tmp_path / "robot-framework-browser-e2e"
    library.mkdir()
    memory_file = library / "feedback_wait_for_request.md"
    memory_file.write_text(
        "---\n"
        "name: Wait For Request returns URL only\n"
        "description: Browser returns a URL string.\n"
        "type: feedback\n"
        "---\n"
        "Use Wait For Response when request metadata is needed.\n",
        encoding="utf-8",
    )

    candidates = build_file_memory_candidates(
        tmp_path,
        scope={"catalog": "private-engineering-catalog"},
        source_type="private-catalog-library",
        source_ref_prefix="catalog://private/libraries",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.memory_type == "rule"
    assert candidate.classification["method"] == "heuristic"
    assert candidate.source_ref.endswith(
        "/robot-framework-browser-e2e/feedback_wait_for_request.md"
    )
    assert candidate.payload["title"] == "Wait For Request returns URL only"
    assert candidate.payload["scope"] == {
        "catalog": "private-engineering-catalog",
        "library": "robot-framework-browser-e2e",
    }
    assert "Summary: Browser returns a URL string." in candidate.payload["content"]
    assert "source-type:feedback" in candidate.payload["tags"]
    assert candidate.payload["metadata"]["memory_classification"]["memory_type"] == "rule"


def test_build_file_memory_candidates_uses_ml_for_ambiguous_markdown(tmp_path) -> None:
    memory_file = tmp_path / "storage-choice.md"
    memory_file.write_text(
        "# Storage choice\n\n"
        "Decision: we accepted PostgreSQL as the canonical memory store. "
        "Consequences include migrations and backup ownership.\n",
        encoding="utf-8",
    )

    candidates = build_file_memory_candidates(tmp_path)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.memory_type == "decision"
    assert candidate.classification["method"] == "ml"
    assert candidate.payload["metadata"]["memory_classification"]["memory_type"] == "decision"
    assert "memory_type_classified:ml" in candidate.findings


def test_build_file_memory_candidates_classifies_skill_files(tmp_path) -> None:
    skill_dir = tmp_path / "skills" / "pr-reviewer"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "# PR Reviewer\n\nReview code changes and report behavioral risks.\n",
        encoding="utf-8",
    )

    candidates = build_file_memory_candidates(
        tmp_path,
        source_type="skill-file",
        source_ref_prefix="test://skills",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.memory_type == "skill"
    assert candidate.payload["memory_type"] == "skill"
    assert candidate.payload["source"]["source_ref"] == "test://skills/skills/pr-reviewer/SKILL.md"


@pytest.mark.asyncio
async def test_import_memory_files_dry_run_does_not_capture(tmp_path) -> None:
    (tmp_path / "memory.md").write_text("Plain operational note.", encoding="utf-8")
    client = FakeMemoryClient()

    summary = await import_memory_files(
        client,
        tmp_path,
        source_ref_prefix="test://import",
        dry_run=True,
    )

    assert summary["dry_run"] is True
    assert summary["candidates"] == 1
    assert summary["created"] == 0
    assert client.created == []


@pytest.mark.asyncio
async def test_import_memory_files_skips_existing_source_ref(tmp_path) -> None:
    (tmp_path / "memory.md").write_text("Plain operational note.", encoding="utf-8")
    source_ref = "test://import/memory.md"
    client = FakeMemoryClient(existing={source_ref})

    summary = await import_memory_files(
        client,
        tmp_path,
        source_ref_prefix="test://import",
    )

    assert summary["candidates"] == 1
    assert summary["created"] == 0
    assert summary["skipped_existing"] == 1
    assert client.created == []


@pytest.mark.asyncio
async def test_import_memory_files_captures_new_payload(tmp_path) -> None:
    (tmp_path / "memory.md").write_text("Plain operational note.", encoding="utf-8")
    client = FakeMemoryClient()

    summary = await import_memory_files(
        client,
        tmp_path,
        source_ref_prefix="test://import",
    )

    assert summary["created"] == 1
    assert summary["failed"] == 0
    assert client.created[0]["source"]["source_ref"] == "test://import/memory.md"
