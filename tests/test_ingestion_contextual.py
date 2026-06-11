from __future__ import annotations

from typing import Any

import pytest

from onebrain_core.contracts.schemas import IngestionAnalyzeRequest, IngestionCommitRequest
from onebrain_core.ingestion import analyze_memory_files, commit_ingestion_plan


class FakeIngestionService:
    def __init__(self) -> None:
        self.created: list[Any] = []
        self.links: list[dict[str, Any]] = []

    async def get_memory_by_source_ref(self, source_ref: str) -> None:
        raise KeyError(source_ref)

    async def capture_memory(self, payload: Any, actor: str = "ingestion") -> dict[str, Any]:
        self.created.append(payload)
        return {"id": f"memory-{len(self.created)}"}

    async def link_memories(self, **kwargs) -> dict[str, Any]:
        self.links.append(kwargs)
        return {"id": f"link-{len(self.links)}", **kwargs}


def test_analyze_memory_files_builds_macro_and_child_items(tmp_path) -> None:
    source = tmp_path / "library" / "guide.md"
    source.parent.mkdir()
    source.write_text(
        "# Release Guide\n\nCoordinate releases.\n\n## Build\n\nRun checks.\n",
        encoding="utf-8",
    )

    plan = analyze_memory_files(
        IngestionAnalyzeRequest(
            path=str(tmp_path),
            scope={"project": "one-brain"},
            source_ref_prefix="test://catalog",
        )
    )

    assert plan.stats["documents"] == 1
    assert plan.stats["macro_items"] == 1
    assert plan.stats["child_items"] == 2
    assert plan.documents[0].relative_path == "library/guide.md"

    macro = next(item for item in plan.items if item.item_type == "document")
    children = [item for item in plan.items if item.item_type == "section"]

    assert macro.payload.memory_type == "context"
    assert macro.payload.source.source_ref == "test://catalog/library/guide.md#document"
    assert all(child.parent_item_id == macro.id for child in children)
    assert children[0].payload.metadata["parent_item_id"] == macro.id
    assert children[0].payload.scope == {"project": "one-brain", "library": "library"}


def test_analyze_memory_files_uses_specific_title_for_body_fallback(tmp_path) -> None:
    source = tmp_path / "library" / "plain.txt"
    source.parent.mkdir()
    source.write_text("Plain operational knowledge without markdown headings.", encoding="utf-8")

    plan = analyze_memory_files(IngestionAnalyzeRequest(path=str(tmp_path)))

    child = next(item for item in plan.items if item.item_type == "section")

    assert child.title == "Details: Plain"
    assert child.payload.title == "Details: Plain"
    assert child.payload.metadata["section_title"] == "Details: Plain"


@pytest.mark.asyncio
async def test_commit_ingestion_plan_creates_parent_child_links(tmp_path) -> None:
    source = tmp_path / "guide.md"
    source.write_text("# Guide\n\nIntro.\n\n## Step\n\nDo it.\n", encoding="utf-8")
    plan = analyze_memory_files(
        IngestionAnalyzeRequest(path=str(source), source_ref_prefix="test://commit")
    )
    service = FakeIngestionService()

    result = await commit_ingestion_plan(
        service,
        IngestionCommitRequest(plan=plan),
        actor="test",
    )

    assert result.created == 3
    assert result.failed == 0
    assert len(service.links) == 2
    assert {link["link_type"] for link in service.links} == {"contains"}
    assert service.links[0]["from_memory_id"] == "memory-1"
    assert service.links[0]["to_memory_id"] == "memory-2"
    assert service.links[0]["actor"] == "test"
