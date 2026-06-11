from __future__ import annotations

from typing import Any

import pytest

from onebrain_core.application.skills import add_hardened_skill, harden_skill_payload


class FakeSkillClient:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.created: list[dict[str, Any]] = []

    async def get_memory_by_source_ref(self, source_ref: str) -> dict[str, Any] | None:
        if source_ref in self.existing:
            return {"id": "existing", "source_ref": source_ref}
        return None

    async def capture_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created.append(payload)
        return {"id": f"memory-{len(self.created)}", **payload}


def test_harden_skill_payload_builds_memory_payload() -> None:
    result = harden_skill_payload(
        {
            "name": "PR Reviewer",
            "description": "Reviews pull requests before merge.",
            "instructions": "Use api_key=super-secret only in local smoke tests.",
            "capabilities": ["Review code", "Review code", "Find missing tests"],
            "tools": ["onebrain_search_memory"],
            "tags": ["Delivery"],
        },
        default_scope={"project": "one-brain"},
    )

    assert result.redactions == 1
    assert "secret_redacted" in result.findings
    assert result.payload["memory_type"] == "skill"
    assert result.payload["title"] == "PR Reviewer"
    assert result.payload["scope"] == {"project": "one-brain"}
    assert result.payload["source"] == {
        "source_type": "skill",
        "source_ref": "skill://pr-reviewer",
    }
    assert result.payload["metadata"]["asset_type"] == "skill.spec"
    assert result.payload["metadata"]["skill_name"] == "PR Reviewer"
    assert "asset:skill" in result.payload["tags"]
    assert "capability:find-missing-tests" in result.payload["tags"]
    assert "[REDACTED]" in result.payload["content"]


@pytest.mark.asyncio
async def test_add_hardened_skill_skips_existing_source_ref() -> None:
    client = FakeSkillClient(existing={"skill://pr-reviewer"})

    result = await add_hardened_skill(
        client,
        {
            "name": "PR Reviewer",
            "instructions": "Review changes and report behavioral risks.",
        },
    )

    assert result["skipped_existing"] is True
    assert result["memory"]["id"] == "existing"
    assert client.created == []
