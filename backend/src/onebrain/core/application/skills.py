from __future__ import annotations

import re
from typing import Any, Protocol

from onebrain.core.application.memory_hardening import HardeningResult, redact_secret_text
from onebrain.core.common.text import normalize_name
from onebrain.core.contracts.schemas import EntityInput, MemoryCreate, SkillCreate


class SkillApiClient(Protocol):
    async def capture_memory(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def get_memory_by_source_ref(self, source_ref: str) -> dict[str, Any] | None: ...


def harden_skill_payload(
    skill: dict[str, Any],
    *,
    default_scope: dict[str, Any] | None = None,
    source_type: str = "skill",
    source_ref: str | None = None,
    redact_secrets: bool = True,
) -> HardeningResult:
    """Normalize, redact, and return a MemoryCreate-compatible skill payload."""

    findings: list[str] = []
    payload = dict(skill)

    if default_scope:
        merged_scope = dict(default_scope)
        merged_scope.update(payload.get("scope") or {})
        payload["scope"] = merged_scope
        findings.append("scope_merged")
    else:
        payload["scope"] = payload.get("scope") or {}

    source = dict(payload.get("source") or {})
    if not source.get("source_type"):
        source["source_type"] = source_type
        findings.append("source_type_defaulted")
    if not source.get("source_ref"):
        source["source_ref"] = source_ref or _default_source_ref(
            str(payload.get("name") or "skill"),
            str(payload["version"]) if payload.get("version") else None,
        )
        findings.append("source_ref_defaulted")
    payload["source"] = source

    redactions = 0
    if redact_secrets:
        for key in ("description", "instructions", "content", "when_to_use"):
            if payload.get(key) is None:
                continue
            redacted, count = redact_secret_text(str(payload[key]))
            payload[key] = redacted
            redactions += count
        if redactions:
            findings.append("secret_redacted")

    skill_model = SkillCreate.model_validate(payload)
    memory_payload = MemoryCreate.model_validate(
        {
            "memory_type": "skill",
            "title": skill_model.name,
            "content": _skill_content(skill_model),
            "scope": skill_model.scope,
            "tags": _skill_tags(skill_model),
            "confidence": skill_model.confidence,
            "source": skill_model.source.model_dump(mode="json"),
            "entities": [
                EntityInput(name=skill_model.name, entity_type="skill", role="subject"),
                *skill_model.entities,
            ],
            "relations": skill_model.relations,
            "valid_from": skill_model.valid_from,
            "valid_to": skill_model.valid_to,
            "supersedes_id": skill_model.supersedes_id,
            "metadata": _skill_metadata(skill_model),
        }
    )
    return HardeningResult(
        payload=memory_payload.model_dump(mode="json"),
        findings=findings,
        redactions=redactions,
    )


async def add_hardened_skill(
    client: SkillApiClient,
    skill: dict[str, Any],
    *,
    default_scope: dict[str, Any] | None = None,
    source_type: str = "skill",
    source_ref: str | None = None,
    redact_secrets: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    hardened = harden_skill_payload(
        skill,
        default_scope=default_scope,
        source_type=source_type,
        source_ref=source_ref,
        redact_secrets=redact_secrets,
    )
    result: dict[str, Any] = {
        "dry_run": dry_run,
        "payload": hardened.payload,
        "findings": hardened.findings,
        "redactions": hardened.redactions,
    }
    if dry_run:
        return result

    source = hardened.payload.get("source") or {}
    source_ref_value = source.get("source_ref")
    existing = None
    if source_ref_value:
        existing = await client.get_memory_by_source_ref(str(source_ref_value))
    if existing is not None:
        result["skipped_existing"] = True
        result["memory"] = existing
        return result

    result["skipped_existing"] = False
    result["memory"] = await client.capture_memory(hardened.payload)
    return result


def _skill_content(skill: SkillCreate) -> str:
    parts = [f"# {skill.name}"]
    if skill.description:
        parts.append(skill.description.strip())
    if skill.version:
        parts.append(f"Version: {skill.version}")
    if skill.capabilities:
        parts.append("Capabilities:\n" + _bullet_list(skill.capabilities))
    if skill.tools:
        parts.append("Tools:\n" + _bullet_list(skill.tools))
    if skill.when_to_use:
        parts.append("When to use:\n" + skill.when_to_use.strip())

    instructions = (skill.instructions or "").strip()
    content = (skill.content or "").strip()
    if instructions and content and instructions != content:
        parts.append("Instructions:\n" + instructions)
        parts.append("Content:\n" + content)
    else:
        parts.append("Instructions:\n" + (instructions or content))
    return "\n\n".join(parts)


def _skill_metadata(skill: SkillCreate) -> dict[str, Any]:
    metadata = dict(skill.metadata)
    metadata.update(
        {
            "asset_type": "skill.spec",
            "skill_name": skill.name,
        }
    )
    if skill.version:
        metadata["skill_version"] = skill.version
    if skill.capabilities:
        metadata["capabilities"] = skill.capabilities
    if skill.tools:
        metadata["tools"] = skill.tools
    if skill.description:
        metadata["description"] = skill.description
    return metadata


def _skill_tags(skill: SkillCreate) -> list[str]:
    tags = {*skill.tags, "skill", "asset:skill"}
    tags.update(f"capability:{_tag_slug(item)}" for item in skill.capabilities)
    tags.update(f"tool:{_tag_slug(item)}" for item in skill.tools)
    return sorted(tag for tag in tags if tag)


def _bullet_list(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values)


def _default_source_ref(name: str, version: str | None) -> str:
    suffix = f"@{_tag_slug(version)}" if version else ""
    return f"skill://{_tag_slug(name)}{suffix}"


def _tag_slug(value: str) -> str:
    normalized = normalize_name(value)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "skill"
