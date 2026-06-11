from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from onebrain_core.application.memory_hardening import redact_secret_text
from onebrain_core.common.path_mapping import resolve_mapped_path
from onebrain_core.common.text import normalize_name
from onebrain_core.contracts.schemas import (
    EntityInput,
    IngestionAnalyzeRequest,
    IngestionCommitRequest,
    IngestionCommitResult,
    IngestionDocument,
    IngestionItem,
    IngestionPlan,
    MemoryCreate,
)

DEFAULT_API_URL = "http://127.0.0.1:8088/api/v1"
DEFAULT_PATH_MAPPINGS = r"C:\DoxieOS=/mnt/doxie"


class FileEntityContext(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    entity_type: str = Field(default="concept", min_length=1, max_length=64)
    summary: str = Field(default="", max_length=360)


class FileContext(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=700)
    purpose: str = Field(min_length=1, max_length=900)
    domain: str = Field(default="", max_length=120)
    key_topics: list[str] = Field(default_factory=list, max_length=12)
    important_sections: list[str] = Field(default_factory=list, max_length=12)
    entities: list[FileEntityContext] = Field(default_factory=list, max_length=12)
    tags: list[str] = Field(default_factory=list, max_length=12)
    confidence: float = Field(default=0.84, ge=0.0, le=1.0)


class Contextualizer(Protocol):
    async def contextualize(
        self,
        *,
        root_path: Path,
        document: IngestionDocument,
        macro_item: IngestionItem,
        child_items: list[IngestionItem],
        redact_secrets: bool,
    ) -> FileContext: ...


@dataclass(frozen=True)
class LocalImportOptions:
    path: Path
    api_path: str | None = None
    api_url: str = DEFAULT_API_URL
    api_key: str | None = None
    path_mappings: str = DEFAULT_PATH_MAPPINGS
    scope: dict[str, Any] = field(default_factory=dict)
    source_type: str = "local-context-import"
    source_ref_prefix: str | None = None
    include_extensions: list[str] | None = None
    exclude_dirs: list[str] | None = None
    include_examples: bool = True
    redact_secrets: bool = True
    max_files: int | None = None
    max_content_chars: int = 24_000
    dry_run: bool = False
    analyze_only: bool = False


@dataclass(frozen=True)
class CodexCliOptions:
    command: str = "codex"
    model: str | None = None
    timeout_seconds: int = 180
    max_file_chars: int = 16_000
    enabled: bool = True


@dataclass(frozen=True)
class LocalImportResult:
    api_path: str
    local_path: str
    dry_run: bool
    analyzed_documents: int
    contextualized_documents: int
    commit: IngestionCommitResult | None
    plan: IngestionPlan
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "api_path": self.api_path,
            "local_path": self.local_path,
            "dry_run": self.dry_run,
            "analyzed_documents": self.analyzed_documents,
            "contextualized_documents": self.contextualized_documents,
            "commit": self.commit.model_dump(mode="json") if self.commit else None,
            "plan": self.plan.model_dump(mode="json"),
            "warnings": self.warnings,
        }


class OneBrainIngestionApiClient:
    def __init__(
        self,
        *,
        api_url: str = DEFAULT_API_URL,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def analyze(self, request: IngestionAnalyzeRequest) -> IngestionPlan:
        payload = await self._post("ingestion/analyze", request.model_dump(mode="json"))
        return IngestionPlan.model_validate(payload)

    async def commit(self, request: IngestionCommitRequest) -> IngestionCommitResult:
        payload = await self._post("ingestion/commit", request.model_dump(mode="json"))
        return IngestionCommitResult.model_validate(payload)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(f"{self._api_url}/{path}", headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(_response_error(response))
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError(f"unexpected API response from {path}: expected JSON object")
        return body


class HeuristicContextualizer:
    async def contextualize(
        self,
        *,
        root_path: Path,
        document: IngestionDocument,
        macro_item: IngestionItem,
        child_items: list[IngestionItem],
        redact_secrets: bool,
    ) -> FileContext:
        del root_path, redact_secrets
        section_titles = [item.title for item in child_items[:8]]
        topics = _unique_compact(
            [
                *re.findall(r"[A-Z][A-Za-z0-9_.-]{2,}", macro_item.summary),
                *[Path(document.relative_path).stem],
            ],
            limit=8,
        )
        return FileContext(
            title=macro_item.title,
            summary=macro_item.summary,
            purpose=f"Context memory for {document.relative_path}.",
            domain="local import",
            key_topics=topics,
            important_sections=section_titles,
            entities=[
                FileEntityContext(
                    name=topic,
                    entity_type="concept",
                    summary=f"Topic inferred from {document.relative_path}.",
                )
                for topic in topics[:6]
            ],
            tags=["contextualized", "local-import"],
            confidence=0.64,
        )


class CodexCliContextualizer:
    def __init__(self, options: CodexCliOptions | None = None) -> None:
        self._options = options or CodexCliOptions()

    async def contextualize(
        self,
        *,
        root_path: Path,
        document: IngestionDocument,
        macro_item: IngestionItem,
        child_items: list[IngestionItem],
        redact_secrets: bool,
    ) -> FileContext:
        file_path = _local_file_path(root_path, document.relative_path)
        text = _read_text(file_path)
        if redact_secrets:
            text, _ = redact_secret_text(text)
        prompt = _context_prompt(
            document=document,
            macro_item=macro_item,
            child_items=child_items,
            file_text=_truncate(text, self._options.max_file_chars),
        )
        cwd = await asyncio.to_thread(_codex_cwd, root_path)
        output = await asyncio.to_thread(self._run_codex, prompt, cwd)
        return _parse_file_context(output)

    def _run_codex(self, prompt: str, cwd: Path) -> str:
        command = _codex_command(self._options.command)
        with tempfile.TemporaryDirectory(prefix="onebrain-codex-") as temp_dir:
            schema_path = Path(temp_dir) / "file-context.schema.json"
            output_path = Path(temp_dir) / "context.json"
            schema_path.write_text(json.dumps(_file_context_schema()), encoding="utf-8")
            args = [
                *command,
                "--ask-for-approval",
                "never",
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-C",
                str(cwd),
            ]
            if self._options.model:
                args.extend(["--model", self._options.model])
            args.append("-")

            completed = subprocess.run(  # noqa: S603
                args,
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self._options.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                message = (completed.stderr or completed.stdout or "").strip()
                raise RuntimeError(f"codex CLI failed with exit {completed.returncode}: {message}")
            if output_path.exists():
                return output_path.read_text(encoding="utf-8")
            return completed.stdout


async def run_local_import(
    options: LocalImportOptions,
    *,
    api_client: OneBrainIngestionApiClient | None = None,
    contextualizer: Contextualizer | None = None,
) -> LocalImportResult:
    local_path = options.path.expanduser().resolve()
    api_path = options.api_path or resolve_mapped_path(str(local_path), options.path_mappings)
    client = api_client or OneBrainIngestionApiClient(
        api_url=options.api_url,
        api_key=options.api_key,
    )
    analyze_request = IngestionAnalyzeRequest(
        path=api_path,
        scope=options.scope,
        source_type=options.source_type,
        source_ref_prefix=options.source_ref_prefix,
        include_extensions=options.include_extensions,
        exclude_dirs=options.exclude_dirs,
        include_examples=options.include_examples,
        redact_secrets=options.redact_secrets,
        max_files=options.max_files,
        max_content_chars=options.max_content_chars,
    )
    plan = await client.analyze(analyze_request)
    selected_contextualizer = contextualizer or HeuristicContextualizer()
    enriched, contextualized, warnings = await enrich_plan_with_context(
        plan,
        root_path=local_path,
        contextualizer=selected_contextualizer,
        contextualizer_name=_contextualizer_name(selected_contextualizer),
        redact_secrets=options.redact_secrets,
    )
    commit_result = None
    if not options.analyze_only:
        commit_result = await client.commit(
            IngestionCommitRequest(plan=enriched, dry_run=options.dry_run)
        )
    return LocalImportResult(
        api_path=api_path,
        local_path=str(local_path),
        dry_run=options.dry_run,
        analyzed_documents=len(plan.documents),
        contextualized_documents=contextualized,
        commit=commit_result,
        plan=enriched,
        warnings=warnings,
    )


async def enrich_plan_with_context(
    plan: IngestionPlan,
    *,
    root_path: Path,
    contextualizer: Contextualizer,
    contextualizer_name: str = "codex-cli",
    redact_secrets: bool,
) -> tuple[IngestionPlan, int, list[str]]:
    items_by_document: dict[str, list[IngestionItem]] = {}
    for item in plan.items:
        items_by_document.setdefault(item.document_id, []).append(item)

    enriched_items: list[IngestionItem] = []
    contexts: dict[str, tuple[FileContext, str]] = {}
    warnings: list[str] = []
    fallback_contextualizations = 0

    for document in plan.documents:
        document_items = items_by_document.get(document.id, [])
        macro = next((item for item in document_items if item.item_type == "document"), None)
        children = [item for item in document_items if item.item_type != "document"]
        if macro is None:
            warnings.append(f"{document.relative_path}: macro item not found")
            continue
        try:
            context = await contextualizer.contextualize(
                root_path=root_path,
                document=document,
                macro_item=macro,
                child_items=children,
                redact_secrets=redact_secrets,
            )
            contexts[document.id] = (context, contextualizer_name)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{document.relative_path}: contextualization failed: {str(exc)[:500]}")
            fallback_contextualizations += 1
            context = await HeuristicContextualizer().contextualize(
                root_path=root_path,
                document=document,
                macro_item=macro,
                child_items=children,
                redact_secrets=redact_secrets,
            )
            contexts[document.id] = (context, "heuristic")

    for item in plan.items:
        context_entry = contexts.get(item.document_id)
        if context_entry is None:
            enriched_items.append(item)
            continue
        context, item_contextualizer_name = context_entry
        if item.item_type == "document":
            enriched_items.append(_enriched_macro_item(item, context, item_contextualizer_name))
        else:
            enriched_items.append(_enriched_child_item(item, context, item_contextualizer_name))

    enriched_plan = plan.model_copy(
        update={
            "items": enriched_items,
            "warnings": [*plan.warnings, *warnings],
            "stats": {
                **plan.stats,
                "contextualized_documents": len(contexts),
                "contextualizer": contextualizer_name,
                "fallback_contextualizations": fallback_contextualizations,
            },
        }
    )
    return enriched_plan, len(contexts), warnings


def _enriched_macro_item(
    item: IngestionItem, context: FileContext, contextualizer_name: str
) -> IngestionItem:
    payload = item.payload.model_copy(deep=True)
    payload.title = context.title
    payload.content = _macro_content(payload.content, context, contextualizer_name)
    payload.tags = _merge_tags(
        payload.tags,
        [
            "ingestion:contextualized",
            f"contextualizer:{_tag_slug(contextualizer_name)}",
            *_context_tags(context, contextualizer_name),
        ],
    )
    payload.entities = _merge_entities(payload.entities, context, contextualizer_name)
    payload.confidence = max(payload.confidence, context.confidence)
    payload.metadata = {
        **payload.metadata,
        "summary": context.summary,
        "purpose": context.purpose,
        "domain": context.domain,
        "key_topics": context.key_topics,
        "important_sections": context.important_sections,
        "contextualizer": contextualizer_name,
        "contextualized": True,
        "ingestion_version": "contextual-v2",
    }
    payload = MemoryCreate.model_validate(payload.model_dump(mode="json"))
    return item.model_copy(
        update={
            "title": context.title,
            "summary": context.summary,
            "payload": payload,
            "findings": [
                *item.findings,
                f"{_tag_slug(contextualizer_name).replace('-', '_')}_contextualized",
            ],
            "metadata": {
                **item.metadata,
                "contextualizer": contextualizer_name,
                "contextualized": True,
            },
        }
    )


def _enriched_child_item(
    item: IngestionItem, context: FileContext, contextualizer_name: str
) -> IngestionItem:
    payload = item.payload.model_copy(deep=True)
    payload.content = _child_content(payload.content, context)
    payload.tags = _merge_tags(
        payload.tags,
        ["context-linked", f"contextualizer:{_tag_slug(contextualizer_name)}"],
    )
    payload.metadata = {
        **payload.metadata,
        "parent_context_summary": context.summary,
        "parent_context_purpose": context.purpose,
        "parent_context_topics": context.key_topics,
        "contextualizer": contextualizer_name,
        "ingestion_version": "contextual-v2",
    }
    payload = MemoryCreate.model_validate(payload.model_dump(mode="json"))
    return item.model_copy(
        update={
            "payload": payload,
            "findings": [
                *item.findings,
                f"linked_to_{_tag_slug(contextualizer_name).replace('-', '_')}_context",
            ],
        }
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onebrain-local-import",
        description=(
            "Import local files through the OneBrain API after Codex CLI contextualization."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Deprecated positional docs path. Prefer --docs.",
    )
    parser.add_argument(
        "--docs",
        help="Local docs file or folder path to read, contextualize with Codex CLI, and import.",
    )
    parser.add_argument("--api-url", default=os.getenv("ONEBRAIN_API_URL", DEFAULT_API_URL))
    parser.add_argument(
        "--api-key",
        default=os.getenv("ONEBRAIN_API_KEY") or os.getenv("ONEBRAIN_MCP_CLIENT_KEY"),
    )
    parser.add_argument("--api-path", help="Path as seen by the API container/service.")
    parser.add_argument(
        "--path-mappings",
        default=os.getenv("ONEBRAIN_LOCAL_IMPORT_PATH_MAPPINGS")
        or os.getenv("ONEBRAIN_MCP_PATH_MAPPINGS")
        or DEFAULT_PATH_MAPPINGS,
        help="Host=API path mappings separated by semicolons.",
    )
    parser.add_argument(
        "--scope-json",
        default=os.getenv("ONEBRAIN_IMPORT_SCOPE_JSON") or "{}",
        help="JSON object to store in memory scope. Defaults to ONEBRAIN_IMPORT_SCOPE_JSON.",
    )
    parser.add_argument(
        "--scope-json-file",
        help="Path to a UTF-8 JSON file containing the memory scope object.",
    )
    parser.add_argument("--source-type", default="local-context-import")
    parser.add_argument("--source-ref-prefix")
    parser.add_argument("--include-extension", action="append", dest="include_extensions")
    parser.add_argument("--exclude-dir", action="append", dest="exclude_dirs")
    parser.add_argument("--exclude-examples", action="store_true")
    parser.add_argument("--no-redact-secrets", action="store_true")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--max-content-chars", type=int, default=24_000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--skip-codex", action="store_true")
    parser.add_argument("--codex-command", default=os.getenv("ONEBRAIN_CODEX_COMMAND", "codex"))
    parser.add_argument("--codex-model", default=os.getenv("ONEBRAIN_CODEX_MODEL"))
    parser.add_argument("--codex-timeout-seconds", type=int, default=180)
    parser.add_argument("--codex-max-file-chars", type=int, default=16_000)
    parser.add_argument("--output", help="Optional path to write the full import result JSON.")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        docs_path = _resolve_docs_path(args.docs, args.path)
        scope = _load_scope(args.scope_json, args.scope_json_file)
        contextualizer: Contextualizer
        if args.skip_codex:
            contextualizer = HeuristicContextualizer()
        else:
            contextualizer = CodexCliContextualizer(
                CodexCliOptions(
                    command=args.codex_command,
                    model=args.codex_model,
                    timeout_seconds=args.codex_timeout_seconds,
                    max_file_chars=args.codex_max_file_chars,
                )
            )
        result = await run_local_import(
            LocalImportOptions(
                path=docs_path,
                api_path=args.api_path,
                api_url=args.api_url,
                api_key=args.api_key,
                path_mappings=args.path_mappings,
                scope=scope,
                source_type=args.source_type,
                source_ref_prefix=args.source_ref_prefix,
                include_extensions=args.include_extensions,
                exclude_dirs=args.exclude_dirs,
                include_examples=not args.exclude_examples,
                redact_secrets=not args.no_redact_secrets,
                max_files=args.max_files,
                max_content_chars=args.max_content_chars,
                dry_run=args.dry_run,
                analyze_only=args.analyze_only,
            ),
            contextualizer=contextualizer,
        )
    except Exception as exc:  # noqa: BLE001
        parser.exit(1, f"onebrain-local-import: error: {exc}\n")

    output = result.as_dict()
    rendered = json.dumps(output, indent=2, ensure_ascii=False)
    if args.output:
        await asyncio.to_thread(Path(args.output).write_text, rendered, encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(rendered)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


def _response_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"{response.status_code} {response.text[:500]}"
    detail = payload.get("detail") if isinstance(payload, dict) else payload
    return f"{response.status_code} {detail}"


def _context_prompt(
    *,
    document: IngestionDocument,
    macro_item: IngestionItem,
    child_items: list[IngestionItem],
    file_text: str,
) -> str:
    sections = [
        {
            "title": item.title,
            "summary": item.summary,
            "memory_type": item.memory_type,
            "source_ref": item.source_ref,
        }
        for item in child_items[:16]
    ]
    return (
        "You are preparing a OneBrain memory import. Analyze the local source file and return "
        "a concise semantic context profile for the file. Focus on what the file means, what "
        "workflow/domain it supports, and which concepts should become graph/search entities. "
        "Do not copy secrets, tokens, or long source text. Return only JSON that matches the "
        "provided schema.\n\n"
        f"Relative path: {document.relative_path}\n"
        f"Source ref: {document.source_ref}\n"
        f"Initial title: {macro_item.title}\n"
        f"Initial summary: {macro_item.summary}\n"
        f"Detected sections JSON: {json.dumps(sections, ensure_ascii=False)}\n\n"
        "<file>\n"
        f"{file_text}\n"
        "</file>\n"
    )


def _file_context_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "summary",
            "purpose",
            "domain",
            "key_topics",
            "important_sections",
            "entities",
            "tags",
            "confidence",
        ],
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 160},
            "summary": {"type": "string", "minLength": 1, "maxLength": 700},
            "purpose": {"type": "string", "minLength": 1, "maxLength": 900},
            "domain": {"type": "string", "maxLength": 120},
            "key_topics": {
                "type": "array",
                "maxItems": 12,
                "items": {"type": "string", "minLength": 1, "maxLength": 80},
            },
            "important_sections": {
                "type": "array",
                "maxItems": 12,
                "items": {"type": "string", "minLength": 1, "maxLength": 120},
            },
            "entities": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "entity_type", "summary"],
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 120},
                        "entity_type": {"type": "string", "minLength": 1, "maxLength": 64},
                        "summary": {"type": "string", "maxLength": 360},
                    },
                },
            },
            "tags": {
                "type": "array",
                "maxItems": 12,
                "items": {"type": "string", "minLength": 1, "maxLength": 64},
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
    }


def _parse_file_context(output: str) -> FileContext:
    parsed = _parse_json_object(output)
    try:
        return FileContext.model_validate(parsed)
    except ValidationError as exc:
        raise RuntimeError(f"codex context did not match schema: {exc}") from exc


def _parse_json_object(output: str) -> dict[str, Any]:
    text = output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise RuntimeError("codex context response must be a JSON object")
    return payload


def _macro_content(existing: str, context: FileContext, contextualizer_name: str) -> str:
    topics = ", ".join(context.key_topics) if context.key_topics else "none"
    sections = ", ".join(context.important_sections) if context.important_sections else "none"
    lines = [
        f"# {context.title}",
        "",
        f"Summary: {context.summary}",
        f"Purpose: {context.purpose}",
        f"Domain: {context.domain or 'unspecified'}",
        f"Key topics: {topics}",
        f"Important sections: {sections}",
        "",
        f"{_contextualization_label(contextualizer_name)} contextualization:",
        _entity_lines(context),
        "",
        "Original ingestion context:",
        existing.strip(),
    ]
    return "\n".join(line for line in lines if line is not None).strip()


def _contextualization_label(contextualizer_name: str) -> str:
    if contextualizer_name == "codex-cli":
        return "Codex"
    if contextualizer_name == "heuristic":
        return "Heuristic"
    return contextualizer_name.replace("-", " ").title()


def _child_content(existing: str, context: FileContext) -> str:
    return (
        f"Parent file context: {context.summary}\n"
        f"Parent purpose: {context.purpose}\n\n"
        f"{existing.strip()}"
    ).strip()


def _entity_lines(context: FileContext) -> str:
    if not context.entities:
        return "- No explicit entities identified."
    return "\n".join(
        f"- {entity.name} ({entity.entity_type}): {entity.summary}".rstrip()
        for entity in context.entities
    )


def _merge_entities(
    existing: list[EntityInput],
    context: FileContext,
    contextualizer_name: str,
) -> list[EntityInput]:
    entities = list(existing)
    seen = {(entity.name.casefold(), entity.entity_type.casefold()) for entity in entities}
    for entity in context.entities:
        key = (entity.name.casefold(), entity.entity_type.casefold())
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            EntityInput(
                name=entity.name,
                entity_type=entity.entity_type,
                role="mentioned",
                summary=entity.summary or None,
                metadata={"source": f"{_tag_slug(contextualizer_name)}-contextualizer"},
            )
        )
    return entities


def _merge_tags(left: list[str], right: list[str]) -> list[str]:
    return sorted({tag for tag in [*left, *right] if tag})


def _context_tags(context: FileContext, contextualizer_name: str) -> list[str]:
    tags = ["llm:codex"] if contextualizer_name == "codex-cli" else []
    if context.domain:
        tags.append(f"domain:{_tag_slug(context.domain)}")
    tags.extend(f"topic:{_tag_slug(topic)}" for topic in context.key_topics[:5])
    tags.extend(_tag_slug(tag) for tag in context.tags)
    return [tag for tag in tags if tag]


def _tag_slug(value: str) -> str:
    return normalize_name(value).replace(" ", "-")


def _contextualizer_name(contextualizer: Contextualizer) -> str:
    explicit = getattr(contextualizer, "name", None)
    if explicit:
        return str(explicit)
    if isinstance(contextualizer, CodexCliContextualizer):
        return "codex-cli"
    if isinstance(contextualizer, HeuristicContextualizer):
        return "heuristic"
    return "custom"


def _local_file_path(root_path: Path, relative_path: str) -> Path:
    if root_path.is_file():
        return root_path
    return root_path / relative_path


def _codex_cwd(root_path: Path) -> Path:
    return root_path if root_path.is_dir() else root_path.parent


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n\n[TRUNCATED]"


def _unique_compact(values: list[str], *, limit: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = re.sub(r"\s+", " ", value).strip()
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        output.append(normalized[:80])
        if len(output) >= limit:
            break
    return output


def _codex_command(command: str) -> list[str]:
    parts = shlex.split(command, posix=os.name != "nt")
    if len(parts) != 1:
        return parts
    executable = parts[0]
    if os.name == "nt" and executable.lower() == "codex":
        resolved = shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex")
        return [resolved or executable]
    resolved = shutil.which(executable)
    return [resolved or executable]


def _load_scope(scope_json: str, scope_json_file: str | None) -> dict[str, Any]:
    if scope_json_file:
        if scope_json and scope_json != "{}":
            raise ValueError("use either --scope-json or --scope-json-file, not both")
        scope_json = Path(scope_json_file).read_text(encoding="utf-8")
    return _parse_scope(scope_json or "{}")


def _resolve_docs_path(docs_path: str | None, positional_path: str | None) -> Path:
    if docs_path and positional_path:
        raise ValueError("use either --docs or the positional docs path, not both")
    selected_path = docs_path or positional_path
    if not selected_path:
        raise ValueError("--docs is required")
    return Path(selected_path)


def _parse_scope(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"scope JSON is invalid: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("scope JSON must be an object")
    return parsed
