from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from onebrain_core.application.memory_hardening import (
    build_file_memory_candidates,
    harden_memory_payload,
)


class MemoryApiClient(Protocol):
    async def capture_memory(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def get_memory_by_source_ref(self, source_ref: str) -> dict[str, Any] | None: ...


@dataclass
class ImportSummary:
    path: str
    dry_run: bool
    candidates: int = 0
    created: int = 0
    skipped_existing: int = 0
    failed: int = 0
    redactions: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_library: dict[str, int] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    created_ids: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "dry_run": self.dry_run,
            "candidates": self.candidates,
            "created": self.created,
            "skipped_existing": self.skipped_existing,
            "failed": self.failed,
            "redactions": self.redactions,
            "by_type": dict(sorted(self.by_type.items())),
            "by_library": dict(sorted(self.by_library.items())),
            "findings": self.findings[:100],
            "created_ids": self.created_ids[:100],
            "errors": self.errors[:100],
        }


async def import_memory_files(
    client: MemoryApiClient,
    path: str | Path,
    *,
    scope: dict[str, Any] | None = None,
    source_type: str = "file-import",
    source_ref_prefix: str | None = None,
    include_extensions: list[str] | None = None,
    exclude_dirs: list[str] | None = None,
    include_examples: bool = True,
    redact_secrets: bool = True,
    dry_run: bool = False,
    max_files: int | None = None,
    max_content_chars: int = 24_000,
) -> dict[str, Any]:
    extensions = {item.lower() for item in include_extensions} if include_extensions else None
    excluded = {item.lower() for item in exclude_dirs} if exclude_dirs else None
    candidates = build_file_memory_candidates(
        path,
        scope=scope,
        source_type=source_type,
        source_ref_prefix=source_ref_prefix,
        include_extensions=extensions,
        exclude_dirs=excluded,
        include_examples=include_examples,
        redact_secrets=redact_secrets,
        max_content_chars=max_content_chars,
        max_files=max_files,
    )

    summary = ImportSummary(path=str(path), dry_run=dry_run)
    summary.candidates = len(candidates)

    for candidate in candidates:
        summary.redactions += candidate.redactions
        summary.by_type[candidate.memory_type] = summary.by_type.get(candidate.memory_type, 0) + 1
        library = str(candidate.payload.get("scope", {}).get("library", "unknown"))
        summary.by_library[library] = summary.by_library.get(library, 0) + 1
        if candidate.findings:
            summary.findings.append(
                {
                    "source_ref": candidate.source_ref,
                    "relative_path": candidate.relative_path,
                    "findings": candidate.findings,
                    "redactions": candidate.redactions,
                }
            )

        if dry_run:
            continue

        try:
            existing = await client.get_memory_by_source_ref(candidate.source_ref)
            if existing is not None:
                summary.skipped_existing += 1
                continue
            created = await client.capture_memory(candidate.payload)
            summary.created += 1
            if memory_id := created.get("id"):
                summary.created_ids.append(str(memory_id))
        except Exception as exc:  # noqa: BLE001
            summary.failed += 1
            summary.errors.append(
                {
                    "source_ref": candidate.source_ref,
                    "relative_path": candidate.relative_path,
                    "error": str(exc)[:1000],
                }
            )

    return summary.as_dict()


async def add_hardened_memory(
    client: MemoryApiClient,
    memory: dict[str, Any],
    *,
    default_scope: dict[str, Any] | None = None,
    source_type: str = "manual",
    source_ref: str | None = None,
    redact_secrets: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    hardened = harden_memory_payload(
        memory,
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

    existing = None
    source = hardened.payload.get("source") or {}
    if source.get("source_ref"):
        existing = await client.get_memory_by_source_ref(str(source["source_ref"]))
    if existing is not None:
        result["skipped_existing"] = True
        result["memory"] = existing
        return result

    result["skipped_existing"] = False
    result["memory"] = await client.capture_memory(hardened.payload)
    return result
