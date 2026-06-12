from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from onebrain.core.contracts.schemas import MemoryCreate
from onebrain.ml.memory_classification import (
    MemoryClassificationInput,
    MemoryClassificationResult,
    classify_memory_type,
)

ALLOWED_TEXT_EXTENSIONS = {
    "",
    ".config",
    ".cs",
    ".css",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".npmrc",
    ".props",
    ".py",
    ".robot",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "bin",
    "dist",
    "node_modules",
    "obj",
}

SECRET_PATTERNS = [
    re.compile(
        r"(?im)(\b(?:password|passwd|pwd|secret|client_secret|api[_-]?key|access[_-]?token|"
        r"refresh[_-]?token|auth[_-]?token|pat|private[_-]?key)\b\s*[:=]\s*)([^\s'\";,}]+)"
    ),
    re.compile(r"(?im)(Authorization\s*[:=]\s*Bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?im)(_authToken\s*=\s*)[^\r\n]+"),
    re.compile(r"(?im)(//[^/\s]+/[^\s:]+:)([^@\s]+)(@)"),
]


@dataclass
class HardeningResult:
    payload: dict[str, Any]
    findings: list[str] = field(default_factory=list)
    redactions: int = 0


@dataclass
class FileMemoryCandidate:
    payload: dict[str, Any]
    source_ref: str
    relative_path: str
    memory_type: str
    byte_length: int
    findings: list[str] = field(default_factory=list)
    redactions: int = 0
    classification: dict[str, object] = field(default_factory=dict)


def harden_memory_payload(
    memory: dict[str, Any],
    *,
    default_scope: dict[str, Any] | None = None,
    source_type: str = "manual",
    source_ref: str | None = None,
    redact_secrets: bool = True,
) -> HardeningResult:
    """Normalize, redact, validate, and return a MemoryCreate-compatible payload."""

    findings: list[str] = []
    payload = dict(memory)

    if not payload.get("memory_type"):
        payload["memory_type"] = "note"
        findings.append("memory_type_defaulted")

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
    if source_ref and not source.get("source_ref"):
        source["source_ref"] = source_ref
        findings.append("source_ref_defaulted")
    payload["source"] = source

    if "tags" not in payload or payload["tags"] is None:
        payload["tags"] = []

    if "confidence" not in payload or payload["confidence"] is None:
        payload["confidence"] = 0.75
        findings.append("confidence_defaulted")

    if title := payload.get("title"):
        shortened = _shorten(str(title), 240)
        if shortened != title:
            findings.append("title_truncated")
        payload["title"] = shortened

    redactions = 0
    if redact_secrets:
        content, redactions = redact_secret_text(str(payload.get("content") or ""))
        payload["content"] = content
        if redactions:
            findings.append("secret_redacted")
    else:
        payload["content"] = str(payload.get("content") or "")

    validated = MemoryCreate.model_validate(payload)
    return HardeningResult(
        payload=validated.model_dump(mode="json"),
        findings=findings,
        redactions=redactions,
    )


def build_file_memory_candidates(
    path: str | Path,
    *,
    scope: dict[str, Any] | None = None,
    source_type: str = "file-import",
    source_ref_prefix: str | None = None,
    include_extensions: set[str] | None = None,
    exclude_dirs: set[str] | None = None,
    include_examples: bool = True,
    redact_secrets: bool = True,
    max_content_chars: int = 24_000,
    max_files: int | None = None,
) -> list[FileMemoryCandidate]:
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"path does not exist: {root}")

    files = [root] if root.is_file() else _iter_text_files(root, include_extensions, exclude_dirs)
    candidates: list[FileMemoryCandidate] = []
    for file_path in files:
        if max_files is not None and len(candidates) >= max_files:
            break
        if not include_examples and _has_path_part(file_path, "examples"):
            continue
        try:
            text = file_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            continue

        relative = _relative_path(file_path, root)
        parsed = parse_frontmatter(text)
        title = _title_for_file(relative, parsed.metadata)
        ext = file_path.suffix.lower()
        classification = classify_file_memory_result(
            relative,
            parsed.metadata,
            ext,
            title=title,
            content=parsed.body,
        )
        memory_type = classification.memory_type
        base_source_ref = _source_ref_for_file(relative, source_ref_prefix)
        chunks = chunk_text(parsed.body.strip(), max_content_chars)

        for index, chunk in enumerate(chunks, start=1):
            source_ref = base_source_ref
            chunk_title = title
            if len(chunks) > 1:
                source_ref = f"{base_source_ref}#chunk-{index}-of-{len(chunks)}"
                chunk_title = _shorten(f"{title} ({index}/{len(chunks)})", 240)

            content = _content_for_file(relative, parsed, chunk, ext)
            tags = _tags_for_file(relative, parsed.metadata, ext)
            payload = {
                "memory_type": memory_type,
                "title": chunk_title,
                "content": content,
                "scope": _scope_for_file(scope, relative),
                "tags": tags,
                "confidence": 0.86,
                "source": {"source_type": source_type, "source_ref": source_ref},
                "metadata": {
                    "import_kind": "text-file",
                    "relative_path": relative,
                    "file_name": file_path.name,
                    "file_extension": ext,
                    "file_bytes": file_path.stat().st_size,
                    "had_frontmatter": parsed.has_frontmatter,
                    "frontmatter_type": parsed.metadata.get("type"),
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                    "memory_classification": classification.as_metadata(),
                },
            }
            hardened = harden_memory_payload(
                payload,
                default_scope=None,
                source_type=source_type,
                source_ref=source_ref,
                redact_secrets=redact_secrets,
            )
            candidates.append(
                FileMemoryCandidate(
                    payload=hardened.payload,
                    source_ref=source_ref,
                    relative_path=relative,
                    memory_type=memory_type,
                    byte_length=file_path.stat().st_size,
                    findings=[
                        *hardened.findings,
                        f"memory_type_classified:{classification.method}",
                    ],
                    redactions=hardened.redactions,
                    classification=classification.as_metadata(),
                )
            )
    return candidates


@dataclass
class ParsedFrontmatter:
    metadata: dict[str, str]
    body: str
    has_frontmatter: bool


def parse_frontmatter(text: str) -> ParsedFrontmatter:
    match = re.match(r"(?s)^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$", text)
    if not match:
        return ParsedFrontmatter(metadata={}, body=text, has_frontmatter=False)

    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        item = re.match(r"\s*([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$", line)
        if item:
            metadata[item.group(1).lower()] = item.group(2).strip().strip("\"'")
    return ParsedFrontmatter(metadata=metadata, body=match.group(2), has_frontmatter=True)


def redact_secret_text(text: str) -> tuple[str, int]:
    redactions = 0
    output = text
    for pattern in SECRET_PATTERNS:
        output, count = pattern.subn(_redaction_replacement, output)
        redactions += count
    return output, redactions


def classify_file_memory(
    relative_path: str,
    metadata: dict[str, str],
    extension: str,
    *,
    title: str | None = None,
    content: str = "",
) -> str:
    return classify_file_memory_result(
        relative_path,
        metadata,
        extension,
        title=title,
        content=content,
    ).memory_type


def classify_file_memory_result(
    relative_path: str,
    metadata: dict[str, str],
    extension: str,
    *,
    title: str | None = None,
    content: str = "",
) -> MemoryClassificationResult:
    declared = metadata.get("type", "").lower()
    path = relative_path.lower().replace("/", "\\")
    if declared in {"skill", "skill.spec"} or re.search(r"(^|\\)skills?\\|\\skill\.md$", path):
        return _heuristic_classification("skill", "frontmatter_or_skill_path")
    if declared == "decision" or re.search(r"decisions?\.ya?ml$|adr", path):
        return _heuristic_classification("decision", "frontmatter_or_decision_path")
    if declared == "workflow" or re.search(r"\\(playbooks|checklists|spec-templates)\\", path):
        return _heuristic_classification("workflow", "frontmatter_or_workflow_path")
    if declared == "feedback":
        return _heuristic_classification("rule", "frontmatter_feedback")
    if declared == "preference":
        return _heuristic_classification("preference", "frontmatter_preference")
    if declared == "pitfall" or re.search(r"anti-pattern|antipattern|pitfall|avoid|no_", path):
        return _heuristic_classification("pitfall", "frontmatter_or_pitfall_path")
    if declared == "reference":
        return _heuristic_classification("fact", "frontmatter_reference")
    if re.search(r"(^|\\)project_|context|overview|portfolio|snapshot|library\.json$", path):
        return _heuristic_classification("context", "context_path")
    if extension in {
        ".config",
        ".cs",
        ".css",
        ".json",
        ".js",
        ".mjs",
        ".npmrc",
        ".props",
        ".py",
        ".robot",
        ".ts",
        ".tsx",
        ".yaml",
        ".yml",
    }:
        return _heuristic_classification("fact", "code_or_config_extension")

    result = classify_memory_type(
        MemoryClassificationInput(
            relative_path=relative_path,
            metadata=metadata,
            extension=extension,
            title=title,
            content=content,
        )
    )
    if result.memory_type != "note" and result.confidence >= 0.36:
        return result
    return MemoryClassificationResult(
        memory_type="note",
        confidence=max(result.confidence, 0.2),
        method="heuristic",
        reasons=["default_note", *result.reasons[:3]],
        runner_up=result.memory_type if result.memory_type != "note" else result.runner_up,
        runner_up_confidence=(
            result.confidence if result.memory_type != "note" else result.runner_up_confidence
        ),
    )


def _heuristic_classification(memory_type: str, reason: str) -> MemoryClassificationResult:
    return MemoryClassificationResult(
        memory_type=memory_type,
        confidence=1.0,
        method="heuristic",
        reasons=[reason],
    )


def chunk_text(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        split_at = remaining.rfind("\n## ", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = remaining.rfind("\n\n", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = max_chars
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _iter_text_files(
    root: Path,
    include_extensions: set[str] | None,
    exclude_dirs: set[str] | None,
) -> list[Path]:
    extensions = {item.lower() for item in (include_extensions or ALLOWED_TEXT_EXTENSIONS)}
    excluded = {item.lower() for item in (exclude_dirs or DEFAULT_EXCLUDE_DIRS)}
    files: list[Path] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if any(part.lower() in excluded for part in file_path.parts):
            continue
        if file_path.suffix.lower() not in extensions:
            continue
        files.append(file_path)
    return sorted(files)


def _redaction_replacement(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 3:
        return f"{match.group(1)}[REDACTED]{match.group(3)}"
    return f"{match.group(1)}[REDACTED]"


def _shorten(value: str, max_length: int) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def _relative_path(file_path: Path, root: Path) -> str:
    base = root.parent if root.is_file() else root
    return file_path.relative_to(base).as_posix()


def _title_for_file(relative_path: str, metadata: dict[str, str]) -> str:
    if name := metadata.get("name"):
        return _shorten(name, 240)
    if title := metadata.get("title"):
        return _shorten(title, 240)
    stem = Path(relative_path).stem
    return _shorten(f"Imported memory: {stem}", 240)


def _content_for_file(
    relative_path: str,
    parsed: ParsedFrontmatter,
    body: str,
    extension: str,
) -> str:
    description = parsed.metadata.get("description")
    if parsed.has_frontmatter:
        parts = [f"Source: {relative_path}"]
        if description:
            parts.append(f"Summary: {description}")
        parts.append(body.strip())
        return "\n\n".join(parts)

    fence = extension.lstrip(".") or "text"
    return f"Source file: {relative_path}\n\n```{fence}\n{body.strip()}\n```"


def _tags_for_file(relative_path: str, metadata: dict[str, str], extension: str) -> list[str]:
    parts = relative_path.replace("\\", "/").split("/")
    tags = ["imported", "file-memory"]
    if parts:
        tags.append(f"library:{parts[0].lower()}")
    if declared_type := metadata.get("type"):
        tags.append(f"source-type:{declared_type.lower()}")
    tags.append(f"ext:{extension.lstrip('.') or 'none'}")
    if "examples" in {part.lower() for part in parts}:
        tags.append("example")
    if "sources" in {part.lower() for part in parts}:
        tags.append("source-pack")
    return sorted(set(tags))


def _scope_for_file(scope: dict[str, Any] | None, relative_path: str) -> dict[str, Any]:
    output = dict(scope or {})
    parts = relative_path.replace("\\", "/").split("/")
    if parts and "library" not in output:
        output["library"] = parts[0]
    return output


def _source_ref_for_file(relative_path: str, source_ref_prefix: str | None) -> str:
    normalized = relative_path.replace("\\", "/")
    if source_ref_prefix:
        return f"{source_ref_prefix.rstrip('/')}/{normalized}"
    return f"file://{normalized}"


def _has_path_part(path: Path, part: str) -> bool:
    return part.lower() in {item.lower() for item in path.parts}
