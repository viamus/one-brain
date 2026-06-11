from __future__ import annotations

from typing import Any

import pytest

from onebrain.ingestion import analyze, commit


class FakeCaptureClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def capture_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        return {"id": f"memory-{len(self.payloads)}", **payload}


def test_analyze_markdown_creates_macro_and_section_children(tmp_path) -> None:
    source = tmp_path / "guide.md"
    source.write_text(
        "# Release Guide\n\n"
        "Coordinate the release train.\n\n"
        "## Build\n\n"
        "Run the pipeline and inspect gates.\n\n"
        "## Deploy\n\n"
        "Promote the approved artifact.\n",
        encoding="utf-8",
    )

    plan = analyze(
        tmp_path,
        scope={"project": "one-brain"},
        source_ref_prefix="test://ingestion",
    )

    assert len(plan.source_documents) == 1
    assert plan.source_documents[0].relative_path == "guide.md"
    assert plan.source_documents[0].parser == "markdown"
    assert len(plan.source_documents[0].content_hash) == 64

    macro = next(item for item in plan.items if item.item_type == "macro")
    children = [item for item in plan.items if item.item_type == "child"]

    assert macro.title == "Release Guide"
    assert macro.parent_item_id is None
    assert macro.payload["memory_type"] == "context"
    assert macro.payload["metadata"]["content_hash"] == macro.content_hash

    assert [child.title for child in children] == [
        "guide.md: Release Guide",
        "guide.md: Build",
        "guide.md: Deploy",
    ]
    assert [child.order_index for child in children] == [1, 2, 3]
    assert all(child.parent_item_id == macro.id for child in children)
    assert all(child.payload["metadata"]["parent_item_id"] == macro.id for child in children)
    assert children[1].payload["scope"] == {"project": "one-brain"}
    assert "Run the pipeline" in children[1].payload["content"]


def test_analyze_json_yaml_and_text_with_simple_parsers(tmp_path) -> None:
    (tmp_path / "config.json").write_text(
        '{"service": {"name": "api"}, "limits": {"retries": 3}}',
        encoding="utf-8",
    )
    (tmp_path / "playbook.yaml").write_text(
        "owner: supply\nsteps:\n  - build\n  - deploy\n",
        encoding="utf-8",
    )
    (tmp_path / "note.txt").write_text(
        "First operational note.\n\nSecond operational note.",
        encoding="utf-8",
    )

    plan = analyze(tmp_path)
    children = [item for item in plan.items if item.item_type == "child"]

    assert [document.parser for document in plan.source_documents] == ["json", "text", "yaml"]
    assert {child.payload["source"]["source_ref"] for child in children} == {
        "file://config.json#section-1",
        "file://config.json#section-2",
        "file://note.txt#section-1",
        "file://note.txt#section-2",
        "file://playbook.yaml#section-1",
        "file://playbook.yaml#section-2",
    }
    assert all(
        child.content_hash == child.payload["metadata"]["content_hash"] for child in children
    )
    assert any("yaml_parser_limited" in warning for warning in plan.warnings)


def test_analyze_invalid_json_warns_and_falls_back_to_text_section(tmp_path) -> None:
    source = tmp_path / "broken.json"
    source.write_text('{"open": true', encoding="utf-8")

    plan = analyze(source)

    assert len(plan.source_documents) == 1
    assert any("json_parse_failed" in warning for warning in plan.source_documents[0].warnings)
    child = next(item for item in plan.items if item.item_type == "child")
    assert child.title == "broken.json: Document"
    assert child.payload["memory_type"] == "fact"
    assert child.payload["source"]["source_ref"] == "file://broken.json#section-1"


@pytest.mark.asyncio
async def test_commit_captures_parent_before_children_and_adds_parent_memory_id(tmp_path) -> None:
    source = tmp_path / "guide.md"
    source.write_text("# Guide\n\nIntro.\n\n## Step\n\nDo the work.\n", encoding="utf-8")
    plan = analyze(source, source_ref_prefix="test://commit")
    client = FakeCaptureClient()

    result = await commit(client, plan)

    assert result.created == 3
    assert result.failed == 0
    assert [payload["metadata"]["item_type"] for payload in client.payloads] == [
        "macro",
        "child",
        "child",
    ]
    assert client.payloads[0]["source"]["source_ref"] == "test://commit/guide.md#macro"
    assert client.payloads[1]["metadata"]["parent_memory_id"] == "memory-1"
    assert client.payloads[2]["metadata"]["parent_memory_id"] == "memory-1"
    assert result.item_memory_ids[plan.items[0].id] == "memory-1"
