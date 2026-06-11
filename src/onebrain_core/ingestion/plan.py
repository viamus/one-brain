from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from onebrain_core.schemas import MemoryCreate
from onebrain_core.text import content_hash

ALLOWED_EXTENSIONS = {"", ".json", ".md", ".markdown", ".txt", ".text", ".yaml", ".yml"}
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
}
MAX_SUMMARY_LENGTH = 220


class MemoryCaptureClient(Protocol):
    async def capture_memory(self, payload: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class SourceDocument:
    id: str
    path: str
    relative_path: str
    source_ref: str
    parser: str
    byte_length: int
    content_hash: str
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "relative_path": self.relative_path,
            "source_ref": self.source_ref,
            "parser": self.parser,
            "byte_length": self.byte_length,
            "content_hash": self.content_hash,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class IngestionItem:
    id: str
    source_document_id: str
    item_type: str
    title: str
    summary: str
    content: str
    content_hash: str
    source_ref: str
    parent_item_id: str | None
    order_index: int
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_document_id": self.source_document_id,
            "item_type": self.item_type,
            "title": self.title,
            "summary": self.summary,
            "content": self.content,
            "content_hash": self.content_hash,
            "source_ref": self.source_ref,
            "parent_item_id": self.parent_item_id,
            "order_index": self.order_index,
            "payload": copy.deepcopy(self.payload),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class IngestionPlan:
    root_path: str
    source_documents: list[SourceDocument]
    items: list[IngestionItem]
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "root_path": self.root_path,
            "source_documents": [document.as_dict() for document in self.source_documents],
            "items": [item.as_dict() for item in self.items],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class CommitItemResult:
    item_id: str
    source_ref: str
    memory_id: str | None
    status: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "source_ref": self.source_ref,
            "memory_id": self.memory_id,
            "status": self.status,
            "error": self.error,
        }


@dataclass(frozen=True)
class CommitResult:
    created: int
    failed: int
    results: list[CommitItemResult]
    item_memory_ids: dict[str, str]
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "failed": self.failed,
            "results": [result.as_dict() for result in self.results],
            "item_memory_ids": dict(self.item_memory_ids),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ParsedSection:
    title: str
    content: str
    warnings: list[str] = field(default_factory=list)


def analyze(
    path: str | Path,
    *,
    scope: dict[str, Any] | None = None,
    source_type: str = "file-ingestion",
    source_ref_prefix: str | None = None,
    include_extensions: set[str] | None = None,
    exclude_dirs: set[str] | None = None,
) -> IngestionPlan:
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"path does not exist: {root}")

    files = _candidate_files(root, include_extensions, exclude_dirs)
    documents: list[SourceDocument] = []
    items: list[IngestionItem] = []
    plan_warnings: list[str] = []
    effective_scope = dict(scope or {})

    for document_index, file_path in enumerate(files):
        relative_path = _relative_path(file_path, root)
        source_ref = _source_ref(relative_path, source_ref_prefix)
        document_id = _stable_id("doc", relative_path)
        text, read_warnings = _read_text(file_path)
        parser = _parser_for(file_path)
        sections = _parse_sections(text, parser)
        document_warnings = [*read_warnings]

        for section in sections:
            document_warnings.extend(section.warnings)

        if not text.strip():
            document_warnings.append("empty_file")
            sections = []

        document_hash = _sha256(text)
        documents.append(
            SourceDocument(
                id=document_id,
                path=str(file_path),
                relative_path=relative_path,
                source_ref=source_ref,
                parser=parser,
                byte_length=file_path.stat().st_size,
                content_hash=document_hash,
                warnings=_unique(document_warnings),
            )
        )

        if document_warnings:
            plan_warnings.extend(f"{relative_path}: {warning}" for warning in document_warnings)

        macro = _macro_item(
            document_id=document_id,
            document_index=document_index,
            relative_path=relative_path,
            source_ref=source_ref,
            source_type=source_type,
            scope=effective_scope,
            parser=parser,
            document_hash=document_hash,
            sections=sections,
            warnings=document_warnings,
        )
        items.append(macro)

        for order_index, section in enumerate(sections, start=1):
            items.append(
                _child_item(
                    document_id=document_id,
                    parent_item_id=macro.id,
                    relative_path=relative_path,
                    source_ref=source_ref,
                    source_type=source_type,
                    scope=effective_scope,
                    parser=parser,
                    section=section,
                    order_index=order_index,
                )
            )

    return IngestionPlan(
        root_path=str(root),
        source_documents=documents,
        items=items,
        warnings=_unique(plan_warnings),
    )


async def commit(client: MemoryCaptureClient, plan: IngestionPlan) -> CommitResult:
    results: list[CommitItemResult] = []
    item_memory_ids: dict[str, str] = {}
    warnings: list[str] = []

    for item in _commit_order(plan.items):
        payload = copy.deepcopy(item.payload)
        metadata = dict(payload.get("metadata") or {})
        if item.parent_item_id:
            parent_memory_id = item_memory_ids.get(item.parent_item_id)
            if parent_memory_id:
                metadata["parent_memory_id"] = parent_memory_id
            else:
                warnings.append(f"{item.id}: parent memory not available for {item.parent_item_id}")
        payload["metadata"] = metadata

        try:
            validated_payload = MemoryCreate.model_validate(payload).model_dump(mode="json")
            created = await client.capture_memory(validated_payload)
            memory_id = _created_memory_id(created)
            if memory_id:
                item_memory_ids[item.id] = memory_id
            results.append(
                CommitItemResult(
                    item_id=item.id,
                    source_ref=item.source_ref,
                    memory_id=memory_id,
                    status="created",
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                CommitItemResult(
                    item_id=item.id,
                    source_ref=item.source_ref,
                    memory_id=None,
                    status="failed",
                    error=str(exc)[:1000],
                )
            )

    return CommitResult(
        created=sum(1 for result in results if result.status == "created"),
        failed=sum(1 for result in results if result.status == "failed"),
        results=results,
        item_memory_ids=item_memory_ids,
        warnings=_unique(warnings),
    )


def _macro_item(
    *,
    document_id: str,
    document_index: int,
    relative_path: str,
    source_ref: str,
    source_type: str,
    scope: dict[str, Any],
    parser: str,
    document_hash: str,
    sections: list[ParsedSection],
    warnings: list[str],
) -> IngestionItem:
    title = _title_for_file(relative_path, sections)
    summary = _macro_summary(relative_path, sections)
    content = _macro_content(relative_path, summary, sections)
    item_id = _stable_id("item", relative_path, "macro")
    item_hash = content_hash(content, scope)
    payload = _validated_payload(
        {
            "memory_type": "context",
            "title": title,
            "content": content,
            "scope": scope,
            "tags": _tags(relative_path, parser, "macro"),
            "confidence": 0.78,
            "source": {"source_type": source_type, "source_ref": f"{source_ref}#macro"},
            "metadata": {
                "ingestion_item_id": item_id,
                "source_document_id": document_id,
                "relative_path": relative_path,
                "parser": parser,
                "item_type": "macro",
                "content_hash": item_hash,
                "document_content_hash": document_hash,
                "parent_item_id": None,
                "order_index": document_index + 1,
                "summary": summary,
            },
        }
    )
    return IngestionItem(
        id=item_id,
        source_document_id=document_id,
        item_type="macro",
        title=title,
        summary=summary,
        content=content,
        content_hash=item_hash,
        source_ref=f"{source_ref}#macro",
        parent_item_id=None,
        order_index=document_index + 1,
        payload=payload,
        warnings=_unique(warnings),
    )


def _child_item(
    *,
    document_id: str,
    parent_item_id: str,
    relative_path: str,
    source_ref: str,
    source_type: str,
    scope: dict[str, Any],
    parser: str,
    section: ParsedSection,
    order_index: int,
) -> IngestionItem:
    title = _shorten(f"{Path(relative_path).name}: {section.title}", 240)
    summary = _summary(section.content)
    content = section.content.strip() or summary
    item_id = _stable_id("item", relative_path, str(order_index), section.title)
    item_hash = content_hash(content, scope)
    child_source_ref = f"{source_ref}#section-{order_index}"
    payload = _validated_payload(
        {
            "memory_type": _memory_type_for_child(parser),
            "title": title,
            "content": content,
            "scope": scope,
            "tags": _tags(relative_path, parser, "child"),
            "confidence": 0.72,
            "source": {"source_type": source_type, "source_ref": child_source_ref},
            "metadata": {
                "ingestion_item_id": item_id,
                "source_document_id": document_id,
                "relative_path": relative_path,
                "parser": parser,
                "item_type": "child",
                "content_hash": item_hash,
                "parent_item_id": parent_item_id,
                "order_index": order_index,
                "summary": summary,
                "section_title": section.title,
            },
        }
    )
    return IngestionItem(
        id=item_id,
        source_document_id=document_id,
        item_type="child",
        title=title,
        summary=summary,
        content=content,
        content_hash=item_hash,
        source_ref=child_source_ref,
        parent_item_id=parent_item_id,
        order_index=order_index,
        payload=payload,
        warnings=list(section.warnings),
    )


def _candidate_files(
    root: Path,
    include_extensions: set[str] | None,
    exclude_dirs: set[str] | None,
) -> list[Path]:
    extensions = {item.lower() for item in (include_extensions or ALLOWED_EXTENSIONS)}
    excluded = {item.lower() for item in (exclude_dirs or DEFAULT_EXCLUDE_DIRS)}
    if root.is_file():
        files = [root]
    else:
        files = [
            item
            for item in root.rglob("*")
            if item.is_file()
            and item.suffix.lower() in extensions
            and not any(part.lower() in excluded for part in item.parts)
        ]
    return sorted(files, key=lambda item: item.as_posix().lower())


def _read_text(path: Path) -> tuple[str, list[str]]:
    try:
        return path.read_text(encoding="utf-8-sig"), []
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace"), ["unicode_replacement_used"]


def _parser_for(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in {".md", ".markdown"}:
        return "markdown"
    if extension == ".json":
        return "json"
    if extension in {".yaml", ".yml"}:
        return "yaml"
    return "text"


def _parse_sections(text: str, parser: str) -> list[ParsedSection]:
    if parser == "markdown":
        return _parse_markdown_sections(text)
    if parser == "json":
        return _parse_json_sections(text)
    if parser == "yaml":
        return _parse_yaml_sections(text)
    return _parse_text_sections(text)


def _parse_markdown_sections(text: str) -> list[ParsedSection]:
    body = _strip_frontmatter(text)
    heading_re = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*#*\s*$")
    matches = list(heading_re.finditer(body))
    if not matches:
        return [ParsedSection(title="Document", content=body.strip())]

    sections: list[ParsedSection] = []
    preface = body[: matches[0].start()].strip()
    if preface:
        sections.append(ParsedSection(title="Overview", content=preface))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        title = _clean_title(match.group(2))
        content = body[match.start() : end].strip()
        sections.append(ParsedSection(title=title, content=content))
    return sections


def _parse_json_sections(text: str) -> list[ParsedSection]:
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        warning = f"json_parse_failed:{exc.lineno}:{exc.colno}"
        return [ParsedSection(title="Document", content=text.strip(), warnings=[warning])]

    if isinstance(loaded, dict):
        sections = [
            ParsedSection(title=str(key), content=json.dumps(value, indent=2, sort_keys=True))
            for key, value in loaded.items()
        ]
        return sections or [ParsedSection(title="Document", content="{}")]

    if isinstance(loaded, list):
        sections = [
            ParsedSection(
                title=f"Item {index}",
                content=json.dumps(value, indent=2, sort_keys=True),
            )
            for index, value in enumerate(loaded, start=1)
        ]
        return sections or [ParsedSection(title="Document", content="[]")]

    return [ParsedSection(title="Document", content=json.dumps(loaded, indent=2, sort_keys=True))]


def _parse_yaml_sections(text: str) -> list[ParsedSection]:
    lines = text.splitlines()
    key_re = re.compile(r"^([A-Za-z0-9_.-][A-Za-z0-9_. -]*):(?:\s*(.*))?$")
    starts = [
        (index, match.group(1).strip())
        for index, line in enumerate(lines)
        if (match := key_re.match(line))
    ]
    warning = "yaml_parser_limited"

    if not starts:
        return [ParsedSection(title="Document", content=text.strip(), warnings=[warning])]

    sections: list[ParsedSection] = []
    for index, (start_line, title) in enumerate(starts):
        end_line = starts[index + 1][0] if index + 1 < len(starts) else len(lines)
        content = "\n".join(lines[start_line:end_line]).strip()
        sections.append(ParsedSection(title=title, content=content, warnings=[warning]))
    return sections


def _parse_text_sections(text: str) -> list[ParsedSection]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return []
    if len(paragraphs) == 1:
        return [ParsedSection(title="Document", content=paragraphs[0])]
    return [
        ParsedSection(title=f"Paragraph {index}", content=paragraph)
        for index, paragraph in enumerate(paragraphs, start=1)
    ]


def _strip_frontmatter(text: str) -> str:
    match = re.match(r"(?s)^---\s*\r?\n.*?\r?\n---\s*\r?\n?(.*)$", text)
    return match.group(1) if match else text


def _macro_content(relative_path: str, summary: str, sections: list[ParsedSection]) -> str:
    lines = [f"Source file: {relative_path}", f"Summary: {summary}"]
    if sections:
        lines.append("Sections:")
        for index, section in enumerate(sections, start=1):
            lines.append(f"{index}. {section.title} - {_summary(section.content)}")
    else:
        lines.append("Sections: none")
    return "\n".join(lines)


def _macro_summary(relative_path: str, sections: list[ParsedSection]) -> str:
    if not sections:
        return "Empty file with no ingestible sections."
    if len(sections) == 1:
        return _shorten(_summary(sections[0].content), MAX_SUMMARY_LENGTH)
    names = "; ".join(section.title for section in sections[:5])
    suffix = "" if len(sections) <= 5 else f"; +{len(sections) - 5} more"
    return _shorten(f"{relative_path} contains {len(sections)} sections: {names}{suffix}.")


def _summary(text: str) -> str:
    normalized = _clean_summary_text(text)
    if not normalized:
        return "No text content."
    sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0]
    return _shorten(sentence, MAX_SUMMARY_LENGTH)


def _clean_summary_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^#{1,6}\s+", "", stripped)
        stripped = stripped.strip("`*- ")
        if stripped:
            lines.append(stripped)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _title_for_file(relative_path: str, sections: list[ParsedSection]) -> str:
    first_heading = next(
        (section.title for section in sections if section.title not in {"Document", "Overview"}),
        None,
    )
    if first_heading:
        return _shorten(first_heading, 240)
    return _shorten(Path(relative_path).name, 240)


def _memory_type_for_child(parser: str) -> str:
    if parser in {"json", "yaml"}:
        return "fact"
    return "note"


def _tags(relative_path: str, parser: str, item_type: str) -> list[str]:
    extension = Path(relative_path).suffix.lower().lstrip(".") or "none"
    return sorted(
        {
            "ingestion",
            f"ext:{extension}",
            f"parser:{parser}",
            f"item:{item_type}",
        }
    )


def _validated_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return MemoryCreate.model_validate(payload).model_dump(mode="json")


def _commit_order(items: list[IngestionItem]) -> list[IngestionItem]:
    item_positions = {item.id: index for index, item in enumerate(items)}

    def sort_key(item: IngestionItem) -> tuple[int, int, int]:
        parent_position = item_positions.get(
            item.parent_item_id or item.id,
            item_positions[item.id],
        )
        depth = 0 if item.parent_item_id is None else 1
        return parent_position, depth, item.order_index

    return sorted(items, key=sort_key)


def _created_memory_id(created: Any) -> str | None:
    if isinstance(created, dict):
        value = created.get("id")
    else:
        value = getattr(created, "id", None)
    return str(value) if value is not None else None


def _relative_path(file_path: Path, root: Path) -> str:
    base = root.parent if root.is_file() else root
    return file_path.relative_to(base).as_posix()


def _source_ref(relative_path: str, source_ref_prefix: str | None) -> str:
    normalized = relative_path.replace("\\", "/")
    if source_ref_prefix:
        return f"{source_ref_prefix.rstrip('/')}/{normalized}"
    return f"file://{normalized}"


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _shorten(value: str, max_length: int = MAX_SUMMARY_LENGTH) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def _clean_title(value: str) -> str:
    return _shorten(re.sub(r"\s+", " ", value).strip().strip("#"), 240)


def _unique(values: list[str]) -> list[str]:
    return sorted(set(value for value in values if value))
