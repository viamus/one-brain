from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Protocol

from onebrain_core.application.memory_hardening import (
    ALLOWED_TEXT_EXTENSIONS,
    DEFAULT_EXCLUDE_DIRS,
    chunk_text,
    classify_file_memory_result,
    harden_memory_payload,
    parse_frontmatter,
)
from onebrain_core.common.text import content_hash, normalize_name
from onebrain_core.contracts.schemas import (
    EntityInput,
    IngestionAnalyzeRequest,
    IngestionCommitRequest,
    IngestionCommitResult,
    IngestionDocument,
    IngestionItem,
    IngestionPlan,
)


class IngestionServiceClient(Protocol):
    async def capture_memory(self, payload: Any, actor: str = "ingestion") -> Any: ...

    async def get_memory_by_source_ref(self, source_ref: str) -> Any: ...

    async def link_memories(
        self,
        *,
        from_memory_id: str,
        to_memory_id: str,
        link_type: str,
        confidence: float = 0.85,
        order_index: int | None = None,
        evidence: str | None = None,
        metadata: dict[str, Any] | None = None,
        actor: str = "ingestion",
    ) -> Any: ...


def analyze_memory_files(request: IngestionAnalyzeRequest) -> IngestionPlan:
    root = Path(request.path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"path does not exist: {root}")

    files = (
        [root]
        if root.is_file()
        else _iter_text_files(
            root,
            set(request.include_extensions or ALLOWED_TEXT_EXTENSIONS),
            set(request.exclude_dirs or DEFAULT_EXCLUDE_DIRS),
        )
    )
    documents: list[IngestionDocument] = []
    items: list[IngestionItem] = []
    warnings: list[str] = []

    for file_path in files[: request.max_files]:
        try:
            text = file_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            warnings.append(f"{file_path}: decoded with replacement characters")
        if not text.strip():
            continue
        if not request.include_examples and "examples" in {
            part.lower() for part in file_path.parts
        }:
            continue

        relative = _relative_path(file_path, root)
        parsed = parse_frontmatter(text)
        title = _title_for_file(relative, parsed.metadata, parsed.body)
        summary = _summary_for_file(relative, parsed.metadata, parsed.body)
        source_ref = _source_ref_for_file(relative, request.source_ref_prefix)
        document_id = _stable_id("document", source_ref)
        sections = _sections_for_file(
            parsed.body.strip(),
            request.max_content_chars,
            fallback_title=f"Details: {title}",
        )
        document = IngestionDocument(
            id=document_id,
            relative_path=relative,
            source_ref=source_ref,
            title=title,
            summary=summary,
            content_hash=content_hash(text, {"source_ref": source_ref}),
            byte_length=file_path.stat().st_size,
            item_count=1 + len(sections),
            metadata={
                "file_name": file_path.name,
                "file_extension": file_path.suffix.lower(),
                "had_frontmatter": parsed.has_frontmatter,
            },
        )
        documents.append(document)

        macro_item = _macro_item(
            request,
            document=document,
            title=title,
            summary=summary,
            parsed_body=parsed.body,
            file_extension=file_path.suffix.lower(),
        )
        items.append(macro_item)
        for index, section in enumerate(sections, start=1):
            items.append(
                _section_item(
                    request,
                    document=document,
                    parent=macro_item,
                    section=section,
                    order_index=index,
                    file_extension=file_path.suffix.lower(),
                )
            )

    stats = {
        "documents": len(documents),
        "items": len(items),
        "macro_items": sum(1 for item in items if item.item_type == "document"),
        "child_items": sum(1 for item in items if item.item_type != "document"),
    }
    return IngestionPlan(
        path=str(root),
        source_type=request.source_type,
        source_ref_prefix=request.source_ref_prefix,
        documents=documents,
        items=items,
        warnings=warnings,
        stats=stats,
    )


async def commit_ingestion_plan(
    client: IngestionServiceClient,
    request: IngestionCommitRequest,
    *,
    actor: str = "ingestion",
) -> IngestionCommitResult:
    result = IngestionCommitResult(
        dry_run=request.dry_run,
        documents=len(request.plan.documents),
        items=len(request.plan.items),
    )
    if request.dry_run:
        return result

    parent_links: list[tuple[IngestionItem, str, str]] = []
    for item in request.plan.items:
        source_ref = item.payload.source.source_ref
        try:
            existing = await _get_existing(client, source_ref)
            if existing is not None:
                memory_id = _memory_id(existing)
                result.skipped_existing += 1
            else:
                created = await client.capture_memory(item.payload, actor=actor)
                memory_id = _memory_id(created)
                result.created += 1
                result.created_ids.append(memory_id)
            result.memory_id_by_item_id[item.id] = memory_id
            if item.parent_item_id:
                parent_links.append((item, item.parent_item_id, memory_id))
        except Exception as exc:
            result.failed += 1
            result.errors.append(
                {"item_id": item.id, "source_ref": source_ref or "", "error": str(exc)[:1000]}
            )

    for item, parent_item_id, child_memory_id in parent_links:
        parent_memory_id = result.memory_id_by_item_id.get(parent_item_id)
        if not parent_memory_id:
            continue
        try:
            await client.link_memories(
                from_memory_id=parent_memory_id,
                to_memory_id=child_memory_id,
                link_type="contains",
                confidence=0.9,
                order_index=item.order_index,
                evidence=item.source_ref,
                metadata={
                    "document_id": item.document_id,
                    "item_id": item.id,
                    "parent_item_id": parent_item_id,
                },
                actor=actor,
            )
        except Exception as exc:
            result.errors.append(
                {
                    "item_id": item.id,
                    "source_ref": item.source_ref,
                    "error": f"link failed: {str(exc)[:1000]}",
                }
            )
    return result


def _macro_item(
    request: IngestionAnalyzeRequest,
    *,
    document: IngestionDocument,
    title: str,
    summary: str,
    parsed_body: str,
    file_extension: str,
) -> IngestionItem:
    source_ref = f"{document.source_ref}#document"
    content = (
        f"# {title}\n\n"
        f"Summary: {summary}\n\n"
        f"Source document: {document.relative_path}\n"
        f"Document hash: {document.content_hash}\n\n"
        "This is the macro context memory for the source document. Child memories contain "
        "the detailed sections extracted from this file."
    )
    payload = _memory_payload(
        request,
        memory_type="context",
        title=title,
        content=content,
        source_ref=source_ref,
        relative_path=document.relative_path,
        file_extension=file_extension,
        tags=["ingestion:macro", "memory-link:parent"],
        metadata={
            "ingestion_item_type": "document",
            "document_id": document.id,
            "summary": summary,
        },
    )
    return IngestionItem(
        id=_stable_id("item", source_ref),
        document_id=document.id,
        item_type="document",
        memory_type="context",
        title=title,
        summary=summary,
        source_ref=source_ref,
        payload=payload,
        metadata={"role": "macro_context"},
    )


def _section_item(
    request: IngestionAnalyzeRequest,
    *,
    document: IngestionDocument,
    parent: IngestionItem,
    section: dict[str, str],
    order_index: int,
    file_extension: str,
) -> IngestionItem:
    source_ref = f"{document.source_ref}#section-{order_index}"
    section_title = section["title"]
    summary = _summary_for_text(section["body"])
    classification = classify_file_memory_result(
        document.relative_path,
        {},
        file_extension,
        title=section_title,
        content=section["body"],
    )
    memory_type = classification.memory_type
    content = (
        f"# {section_title}\n\n"
        f"Summary: {summary}\n\n"
        f"Source document: {document.relative_path}\n"
        f"Parent context: {parent.title}\n\n"
        f"{section['body'].strip()}"
    )
    payload = _memory_payload(
        request,
        memory_type=memory_type,
        title=section_title,
        content=content,
        source_ref=source_ref,
        relative_path=document.relative_path,
        file_extension=file_extension,
        tags=["ingestion:child", f"parent:{normalize_name(parent.title)}"],
        metadata={
            "ingestion_item_type": "section",
            "document_id": document.id,
            "parent_item_id": parent.id,
            "order_index": order_index,
            "section_title": section_title,
            "summary": summary,
            "memory_classification": classification.as_metadata(),
        },
    )
    return IngestionItem(
        id=_stable_id("item", source_ref),
        document_id=document.id,
        parent_item_id=parent.id,
        order_index=order_index,
        item_type="section",
        memory_type=memory_type,
        title=section_title,
        summary=summary,
        source_ref=source_ref,
        payload=payload,
        metadata={"role": "child_context"},
    )


def _memory_payload(
    request: IngestionAnalyzeRequest,
    *,
    memory_type: str,
    title: str,
    content: str,
    source_ref: str,
    relative_path: str,
    file_extension: str,
    tags: list[str],
    metadata: dict[str, Any],
):
    hardened = harden_memory_payload(
        {
            "memory_type": memory_type,
            "title": title,
            "content": content,
            "scope": _scope_for_file(request.scope, relative_path),
            "tags": [*tags, f"ext:{file_extension.lstrip('.') or 'none'}"],
            "confidence": 0.88,
            "source": {"source_type": request.source_type, "source_ref": source_ref},
            "entities": [
                EntityInput(name=relative_path, entity_type="source_document", role="source")
            ],
            "metadata": {
                **metadata,
                "relative_path": relative_path,
                "file_extension": file_extension,
                "ingestion_version": "contextual-v1",
            },
        },
        redact_secrets=request.redact_secrets,
    )
    return hardened.payload


def _sections_for_file(
    text: str,
    max_content_chars: int,
    *,
    fallback_title: str,
) -> list[dict[str, str]]:
    markdown_sections = _markdown_sections(text)
    raw_sections = markdown_sections or [{"title": fallback_title, "body": text}]
    sections: list[dict[str, str]] = []
    for section in raw_sections:
        chunks = chunk_text(section["body"], max_content_chars)
        for index, chunk in enumerate(chunks, start=1):
            title = section["title"]
            if len(chunks) > 1:
                title = f"{title} ({index}/{len(chunks)})"
            sections.append({"title": title, "body": chunk})
    return sections


def _markdown_sections(text: str) -> list[dict[str, str]]:
    matches = list(re.finditer(r"(?m)^(#{1,3})\s+(.+?)\s*$", text))
    if not matches:
        return []
    sections: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append({"title": match.group(2).strip(), "body": body})
    return sections


def _iter_text_files(
    root: Path, include_extensions: set[str], exclude_dirs: set[str]
) -> list[Path]:
    files: list[Path] = []
    normalized_exclude = {item.lower() for item in exclude_dirs}
    normalized_extensions = {item.lower() for item in include_extensions}
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if any(part.lower() in normalized_exclude for part in file_path.parts):
            continue
        if file_path.suffix.lower() not in normalized_extensions:
            continue
        files.append(file_path)
    return sorted(files)


def _scope_for_file(scope: dict[str, Any], relative_path: str) -> dict[str, Any]:
    output = dict(scope)
    parts = relative_path.replace("\\", "/").split("/")
    if len(parts) > 1 and "library" not in output:
        output["library"] = parts[0]
    return output


def _source_ref_for_file(relative_path: str, prefix: str | None) -> str:
    normalized = relative_path.replace("\\", "/")
    return f"{prefix.rstrip('/')}/{normalized}" if prefix else f"file://{normalized}"


def _title_for_file(relative_path: str, metadata: dict[str, str], body: str) -> str:
    if metadata.get("name"):
        return _shorten_text(metadata["name"], 240)
    if metadata.get("title"):
        return _shorten_text(metadata["title"], 240)
    source_title = _title_from_source_body(relative_path, body)
    if source_title:
        return _shorten_text(source_title, 240)
    return _shorten_text(_title_from_relative_path(relative_path), 240)


def _summary_for_file(relative_path: str, metadata: dict[str, str], body: str) -> str:
    if description := metadata.get("description"):
        return _summary_for_text(description)
    if description := _description_from_source_body(relative_path, body):
        return _summary_for_text(description)
    return _summary_for_text(body)


def _title_from_source_body(relative_path: str, body: str) -> str | None:
    path = relative_path.replace("\\", "/").lower()
    if path.endswith(".json"):
        parsed = _json_object(body)
        if parsed:
            for key in ("displayName", "name", "title", "id"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    match = re.search(r"(?m)^#{1,2}\s+(.+?)\s*$", body)
    if match:
        title = match.group(1).strip()
        if title and normalize_name(title) not in {"body", "manifest", "document"}:
            return title
    return None


def _description_from_source_body(relative_path: str, body: str) -> str | None:
    if not relative_path.replace("\\", "/").lower().endswith(".json"):
        return None
    parsed = _json_object(body)
    if not parsed:
        return None
    value = parsed.get("description")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _json_object(body: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _title_from_relative_path(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/").strip("/")
    path = Path(normalized)
    name = path.name.lower()
    if name in {"body.md", "manifest.json", "workflow.json", "library.json", "readme.md"}:
        candidate = path.parent.name or path.stem
    else:
        candidate = path.stem
    return _humanize_slug(candidate) or path.name


def _humanize_slug(value: str) -> str:
    cleaned = re.sub(r"^(feedback|reference|project|memory|skill)_", "", value)
    tokens = [token for token in re.split(r"[\s_.-]+", cleaned) if token]
    acronyms = {
        "acl",
        "ado",
        "api",
        "ci",
        "e2e",
        "gdpr",
        "http",
        "lgpd",
        "mcp",
        "rpa",
        "sso",
        "tms",
    }
    return " ".join(
        token.upper() if token.lower() in acronyms else token.capitalize() for token in tokens
    )


def _shorten_text(value: str, max_length: int) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def _summary_for_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return "No textual content available."
    sentence = re.split(r"(?<=[.!?])\s+", normalized)[0]
    return sentence[:237].rstrip() + "..." if len(sentence) > 240 else sentence


def _relative_path(file_path: Path, root: Path) -> str:
    base = root.parent if root.is_file() else root
    return file_path.relative_to(base).as_posix()


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return f"{prefix}-{digest}"


async def _get_existing(client: IngestionServiceClient, source_ref: str | None) -> Any | None:
    if not source_ref:
        return None
    try:
        return await client.get_memory_by_source_ref(source_ref)
    except KeyError:
        return None


def _memory_id(memory: Any) -> str:
    if isinstance(memory, dict):
        return str(memory.get("id"))
    return str(memory.id)
