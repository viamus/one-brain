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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TextIO, TypeVar

import httpx
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
from onebrain_ml.memory_classification import MemoryClassificationInput, classify_memory_type
from pydantic import BaseModel, Field, ValidationError

DEFAULT_API_URL = "http://127.0.0.1:8088/api/v1"
DEFAULT_PATH_MAPPINGS = r"C:\DoxieOS=/mnt/doxie"
DEFAULT_API_TIMEOUT_SECONDS = 300.0
DEFAULT_COMMIT_BATCH_SIZE = 25
T = TypeVar("T")

MACRO_CLASSIFICATION_MIN_CONFIDENCE_BY_TYPE = {
    "context": 0.0,
    "decision": 0.7,
    "fact": 0.62,
    "note": 0.95,
    "pitfall": 0.72,
    "preference": 0.9,
    "rule": 0.58,
    "runbook": 0.68,
    "skill": 0.5,
    "workflow": 0.58,
}


class KnowledgeEntityContext(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    entity_type: str = Field(default="concept", min_length=1, max_length=64)
    summary: str = Field(default="", max_length=360)


class KnowledgeContext(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=700)
    purpose: str = Field(min_length=1, max_length=900)
    domain: str = Field(default="", max_length=120)
    category: str = Field(default="", max_length=120)
    key_topics: list[str] = Field(default_factory=list, max_length=12)
    important_sections: list[str] = Field(default_factory=list, max_length=12)
    entities: list[KnowledgeEntityContext] = Field(default_factory=list, max_length=12)
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
    ) -> KnowledgeContext: ...


@dataclass(frozen=True)
class KnowledgeContextRequest:
    document: IngestionDocument
    macro_item: IngestionItem
    child_items: list[IngestionItem]


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
    commit_batch_size: int = DEFAULT_COMMIT_BATCH_SIZE
    api_timeout_seconds: float = DEFAULT_API_TIMEOUT_SECONDS
    include_evidence_items: bool = False


@dataclass(frozen=True)
class CodexCliOptions:
    command: str = "codex"
    model: str | None = None
    timeout_seconds: int = 180
    max_file_chars: int = 16_000
    batch_size: int = 8
    max_workers: int = 2
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


class ProgressReporter:
    def __init__(
        self,
        *,
        enabled: bool = True,
        streams: list[TextIO] | None = None,
    ) -> None:
        self._enabled = enabled
        self._streams = streams or [sys.stderr]
        self._started = time.monotonic()

    def event(self, message: str, **fields: Any) -> None:
        if not self._enabled:
            return
        elapsed = time.monotonic() - self._started
        details = " ".join(
            f"{key}={self._format_value(value)}"
            for key, value in fields.items()
            if value is not None
        )
        line = f"[onebrain-import +{elapsed:7.1f}s] {message}"
        if details:
            line = f"{line} {details}"
        for stream in self._streams:
            print(line, file=stream, flush=True)

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, Path):
            return str(value)
        text = str(value)
        if any(character.isspace() for character in text):
            return json.dumps(text, ensure_ascii=False)
        return text


class OneBrainIngestionApiClient:
    def __init__(
        self,
        *,
        api_url: str = DEFAULT_API_URL,
        api_key: str | None = None,
        timeout_seconds: float = DEFAULT_API_TIMEOUT_SECONDS,
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
    ) -> KnowledgeContext:
        del root_path, redact_secrets
        section_titles = [item.title for item in child_items[:8]]
        topics = _unique_compact(
            [
                *re.findall(r"[A-Z][A-Za-z0-9_.-]{2,}", macro_item.summary),
                *[Path(document.relative_path).stem],
            ],
            limit=8,
        )
        return KnowledgeContext(
            title=macro_item.title,
            summary=macro_item.summary,
            purpose="Preserve reusable knowledge learned from source documentation.",
            domain=_heuristic_domain(topics),
            category=_heuristic_category(document, topics),
            key_topics=topics,
            important_sections=section_titles,
            entities=[
                KnowledgeEntityContext(
                    name=topic,
                    entity_type="concept",
                    summary="Knowledge topic inferred from source evidence.",
                )
                for topic in topics[:6]
            ],
            tags=["knowledge-import", "contextualized"],
            confidence=0.64,
        )

    async def contextualize_batch(
        self,
        *,
        root_path: Path,
        requests: list[KnowledgeContextRequest],
        redact_secrets: bool,
    ) -> dict[str, KnowledgeContext]:
        contexts: dict[str, KnowledgeContext] = {}
        for request in requests:
            contexts[request.document.id] = await self.contextualize(
                root_path=root_path,
                document=request.document,
                macro_item=request.macro_item,
                child_items=request.child_items,
                redact_secrets=redact_secrets,
            )
        return contexts


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
    ) -> KnowledgeContext:
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
        return _parse_knowledge_context(output)

    async def contextualize_batch(
        self,
        *,
        root_path: Path,
        requests: list[KnowledgeContextRequest],
        redact_secrets: bool,
    ) -> dict[str, KnowledgeContext]:
        if len(requests) == 1:
            request = requests[0]
            return {
                request.document.id: await self.contextualize(
                    root_path=root_path,
                    document=request.document,
                    macro_item=request.macro_item,
                    child_items=request.child_items,
                    redact_secrets=redact_secrets,
                )
            }
        prompt = _context_batch_prompt(
            root_path=root_path,
            requests=requests,
            redact_secrets=redact_secrets,
            max_file_chars=self._options.max_file_chars,
        )
        cwd = await asyncio.to_thread(_codex_cwd, root_path)
        output = await asyncio.to_thread(
            self._run_codex,
            prompt,
            cwd,
            _knowledge_context_batch_schema(),
            "knowledge-context-batch.schema.json",
        )
        return _parse_knowledge_context_batch(output)

    @property
    def batch_size(self) -> int:
        return max(1, self._options.batch_size)

    @property
    def max_workers(self) -> int:
        return max(1, self._options.max_workers)

    def _run_codex(
        self,
        prompt: str,
        cwd: Path,
        schema: dict[str, Any] | None = None,
        schema_name: str = "knowledge-context.schema.json",
    ) -> str:
        command = _codex_command(self._options.command)
        with tempfile.TemporaryDirectory(prefix="onebrain-codex-") as temp_dir:
            schema_path = Path(temp_dir) / schema_name
            output_path = Path(temp_dir) / "context.json"
            schema_path.write_text(
                json.dumps(schema or _knowledge_context_schema()), encoding="utf-8"
            )
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
    progress: ProgressReporter | None = None,
) -> LocalImportResult:
    local_path = options.path.expanduser().resolve()
    api_path = options.api_path or resolve_mapped_path(str(local_path), options.path_mappings)
    if progress:
        progress.event(
            "resolved import paths",
            local_path=local_path,
            api_path=api_path,
        )
    client = api_client or OneBrainIngestionApiClient(
        api_url=options.api_url,
        api_key=options.api_key,
        timeout_seconds=options.api_timeout_seconds,
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
    if progress:
        progress.event("analyzing docs", source_type=options.source_type)
    plan = await client.analyze(analyze_request)
    if progress:
        progress.event(
            "analyzed docs",
            documents=len(plan.documents),
            items=len(plan.items),
            warnings=len(plan.warnings),
        )
    selected_contextualizer = contextualizer or HeuristicContextualizer()
    if progress:
        progress.event(
            "contextualizing knowledge",
            contextualizer=_contextualizer_name(selected_contextualizer),
            documents=len(plan.documents),
            batch_size=_contextualizer_batch_size(selected_contextualizer),
            workers=_contextualizer_worker_count(selected_contextualizer),
        )
    enriched, contextualized, warnings = await enrich_plan_with_context(
        plan,
        root_path=local_path,
        contextualizer=selected_contextualizer,
        contextualizer_name=_contextualizer_name(selected_contextualizer),
        redact_secrets=options.redact_secrets,
        progress=progress,
    )
    import_plan = _plan_for_knowledge_import(
        enriched,
        include_evidence_items=options.include_evidence_items,
    )
    if progress:
        progress.event(
            "contextualized knowledge",
            contextualized=contextualized,
            warnings=len(warnings),
            fallback=enriched.stats.get("fallback_contextualizations", 0),
            import_items=len(import_plan.items),
            omitted_evidence=import_plan.stats.get("omitted_evidence_items", 0),
        )
    commit_result = None
    if not options.analyze_only:
        commit_result = await commit_plan_in_batches(
            client,
            import_plan,
            dry_run=options.dry_run,
            batch_size=options.commit_batch_size,
            progress=progress,
        )
        if progress:
            progress.event(
                "committed import",
                documents=commit_result.documents,
                items=commit_result.items,
                created=commit_result.created,
                skipped=commit_result.skipped_existing,
                failed=commit_result.failed,
            )
    elif progress:
        progress.event("skipped commit", reason="analyze_only")
    return LocalImportResult(
        api_path=api_path,
        local_path=str(local_path),
        dry_run=options.dry_run,
        analyzed_documents=len(plan.documents),
        contextualized_documents=contextualized,
        commit=commit_result,
        plan=import_plan,
        warnings=warnings,
    )


async def commit_plan_in_batches(
    client: OneBrainIngestionApiClient,
    plan: IngestionPlan,
    *,
    dry_run: bool,
    batch_size: int,
    progress: ProgressReporter | None = None,
) -> IngestionCommitResult:
    document_batches = _batches(plan.documents, batch_size)
    if len(document_batches) <= 1:
        if progress:
            progress.event(
                "committing batch",
                batch="1/1",
                documents=len(plan.documents),
                items=len(plan.items),
                dry_run=dry_run,
            )
        result = await client.commit(IngestionCommitRequest(plan=plan, dry_run=dry_run))
        if progress:
            progress.event(
                "committed batch",
                batch="1/1",
                created=result.created,
                skipped=result.skipped_existing,
                failed=result.failed,
            )
        return result

    merged = IngestionCommitResult(dry_run=dry_run)
    for index, document_batch in enumerate(document_batches, start=1):
        batch_plan = _plan_for_documents(
            plan,
            document_ids={document.id for document in document_batch},
        )
        batch_label = f"{index}/{len(document_batches)}"
        if progress:
            progress.event(
                "committing batch",
                batch=batch_label,
                documents=len(batch_plan.documents),
                items=len(batch_plan.items),
                dry_run=dry_run,
            )
        batch_result = await client.commit(IngestionCommitRequest(plan=batch_plan, dry_run=dry_run))
        if progress:
            progress.event(
                "committed batch",
                batch=batch_label,
                created=batch_result.created,
                skipped=batch_result.skipped_existing,
                failed=batch_result.failed,
            )
        merged = _merge_commit_results(merged, batch_result)
    return merged


def _plan_for_documents(plan: IngestionPlan, *, document_ids: set[str]) -> IngestionPlan:
    documents = [document for document in plan.documents if document.id in document_ids]
    items = [item for item in plan.items if item.document_id in document_ids]
    stats = {
        **plan.stats,
        "commit_batch_documents": len(documents),
        "commit_batch_items": len(items),
    }
    return plan.model_copy(update={"documents": documents, "items": items, "stats": stats})


def _plan_for_knowledge_import(
    plan: IngestionPlan,
    *,
    include_evidence_items: bool,
) -> IngestionPlan:
    if include_evidence_items:
        return plan.model_copy(
            update={
                "stats": {
                    **plan.stats,
                    "evidence_items_included": True,
                    "omitted_evidence_items": 0,
                    "import_items": len(plan.items),
                }
            }
        )

    items = [item for item in plan.items if item.item_type == "document"]
    item_count_by_document: dict[str, int] = {}
    for item in items:
        item_count_by_document[item.document_id] = (
            item_count_by_document.get(item.document_id, 0) + 1
        )
    documents = [
        document.model_copy(update={"item_count": item_count_by_document.get(document.id, 0)})
        for document in plan.documents
    ]
    omitted = len(plan.items) - len(items)
    stats = {
        **plan.stats,
        "evidence_items_included": False,
        "omitted_evidence_items": omitted,
        "import_items": len(items),
    }
    return plan.model_copy(update={"documents": documents, "items": items, "stats": stats})


def _merge_commit_results(
    left: IngestionCommitResult,
    right: IngestionCommitResult,
) -> IngestionCommitResult:
    return IngestionCommitResult(
        dry_run=left.dry_run,
        documents=left.documents + right.documents,
        items=left.items + right.items,
        created=left.created + right.created,
        skipped_existing=left.skipped_existing + right.skipped_existing,
        failed=left.failed + right.failed,
        created_ids=[*left.created_ids, *right.created_ids],
        memory_id_by_item_id={
            **left.memory_id_by_item_id,
            **right.memory_id_by_item_id,
        },
        errors=[*left.errors, *right.errors],
    )


async def enrich_plan_with_context(
    plan: IngestionPlan,
    *,
    root_path: Path,
    contextualizer: Contextualizer,
    contextualizer_name: str = "codex-cli",
    redact_secrets: bool,
    progress: ProgressReporter | None = None,
) -> tuple[IngestionPlan, int, list[str]]:
    items_by_document: dict[str, list[IngestionItem]] = {}
    for item in plan.items:
        items_by_document.setdefault(item.document_id, []).append(item)

    enriched_items: list[IngestionItem] = []
    contexts: dict[str, tuple[KnowledgeContext, str]] = {}
    warnings: list[str] = []
    fallback_contextualizations = 0
    context_requests: list[KnowledgeContextRequest] = []

    for document in plan.documents:
        document_items = items_by_document.get(document.id, [])
        macro = next((item for item in document_items if item.item_type == "document"), None)
        children = [item for item in document_items if item.item_type != "document"]
        if macro is None:
            warnings.append(f"{document.relative_path}: macro item not found")
            continue
        context_requests.append(
            KnowledgeContextRequest(
                document=document,
                macro_item=macro,
                child_items=children,
            )
        )

    contextualize_batch = getattr(contextualizer, "contextualize_batch", None)
    if callable(contextualize_batch):
        request_batches = _batches(context_requests, _contextualizer_batch_size(contextualizer))
        worker_count = min(
            _contextualizer_worker_count(contextualizer),
            len(request_batches) or 1,
        )
        semaphore = asyncio.Semaphore(worker_count)

        async def contextualize_request_batch(
            index: int,
            request_batch: list[KnowledgeContextRequest],
        ) -> tuple[dict[str, tuple[KnowledgeContext, str]], list[str], int]:
            batch_context_entries: dict[str, tuple[KnowledgeContext, str]] = {}
            batch_warnings: list[str] = []
            batch_fallback_contextualizations = 0
            batch_label = f"{index}/{len(request_batches)}"
            try:
                async with semaphore:
                    if progress:
                        progress.event(
                            "contextualizing batch",
                            batch=batch_label,
                            documents=len(request_batch),
                            first=(
                                request_batch[0].document.relative_path if request_batch else None
                            ),
                            workers=worker_count,
                        )
                    batch_contexts = await contextualize_batch(
                        root_path=root_path,
                        requests=request_batch,
                        redact_secrets=redact_secrets,
                    )
            except Exception as exc:  # noqa: BLE001
                batch_path_label = ", ".join(
                    request.document.relative_path for request in request_batch[:3]
                )
                batch_warnings.append(
                    f"{batch_path_label}: batch contextualization failed: {str(exc)[:500]}"
                )
                batch_contexts = {}
                if progress:
                    progress.event(
                        "contextualization batch failed",
                        batch=batch_label,
                        error=str(exc)[:180],
                    )

            for request in request_batch:
                context = batch_contexts.get(request.document.id)
                if context is not None:
                    batch_context_entries[request.document.id] = (
                        context,
                        contextualizer_name,
                    )
                    continue
                batch_fallback_contextualizations += 1
                batch_warnings.append(
                    f"{request.document.relative_path}: using heuristic fallback context"
                )
                fallback = await HeuristicContextualizer().contextualize(
                    root_path=root_path,
                    document=request.document,
                    macro_item=request.macro_item,
                    child_items=request.child_items,
                    redact_secrets=redact_secrets,
                )
                batch_context_entries[request.document.id] = (fallback, "heuristic")
            if progress:
                progress.event(
                    "contextualized batch",
                    batch=batch_label,
                    contextualized=sum(
                        1 for request in request_batch if request.document.id in batch_contexts
                    ),
                    fallback=sum(
                        1 for request in request_batch if request.document.id not in batch_contexts
                    ),
                )
            return (
                batch_context_entries,
                batch_warnings,
                batch_fallback_contextualizations,
            )

        batch_results = await asyncio.gather(
            *[
                contextualize_request_batch(index, request_batch)
                for index, request_batch in enumerate(request_batches, start=1)
            ]
        )
        for batch_context_entries, batch_warnings, batch_fallback_count in batch_results:
            contexts.update(batch_context_entries)
            warnings.extend(batch_warnings)
            fallback_contextualizations += batch_fallback_count
    else:
        for index, request in enumerate(context_requests, start=1):
            if progress:
                progress.event(
                    "contextualizing document",
                    document=f"{index}/{len(context_requests)}",
                    path=request.document.relative_path,
                )
            try:
                context = await contextualizer.contextualize(
                    root_path=root_path,
                    document=request.document,
                    macro_item=request.macro_item,
                    child_items=request.child_items,
                    redact_secrets=redact_secrets,
                )
                contexts[request.document.id] = (context, contextualizer_name)
            except Exception as exc:  # noqa: BLE001
                warnings.append(
                    f"{request.document.relative_path}: contextualization failed: {str(exc)[:500]}"
                )
                fallback_contextualizations += 1
                fallback = await HeuristicContextualizer().contextualize(
                    root_path=root_path,
                    document=request.document,
                    macro_item=request.macro_item,
                    child_items=request.child_items,
                    redact_secrets=redact_secrets,
                )
                contexts[request.document.id] = (fallback, "heuristic")
                if progress:
                    progress.event(
                        "contextualization fallback",
                        document=f"{index}/{len(context_requests)}",
                        path=request.document.relative_path,
                        error=str(exc)[:180],
                    )

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
    item: IngestionItem, context: KnowledgeContext, contextualizer_name: str
) -> IngestionItem:
    payload = item.payload.model_copy(deep=True)
    payload.title = context.title
    payload.content = _macro_content(payload.content, context, contextualizer_name)
    classification = classify_memory_type(
        MemoryClassificationInput(
            relative_path=_item_relative_path(item, payload),
            extension=_item_file_extension(item, payload),
            title=context.title,
            content=payload.content,
        )
    )
    memory_type, classification_applied = _selected_macro_memory_type(
        item,
        payload,
        classification.memory_type,
        classification.confidence,
    )
    payload.memory_type = memory_type
    payload.tags = _merge_tags(
        payload.tags,
        [
            "knowledge:imported",
            "ingestion:contextualized",
            f"memory-type:{memory_type}",
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
        "knowledge_category": context.category,
        "key_topics": context.key_topics,
        "supporting_evidence": context.important_sections,
        "contextualizer": contextualizer_name,
        "contextualized": True,
        "ingestion_version": "knowledge-v3",
        "memory_classification": {
            **classification.as_metadata(),
            "applied": classification_applied,
            "selected_memory_type": memory_type,
        },
    }
    payload = MemoryCreate.model_validate(payload.model_dump(mode="json"))
    return item.model_copy(
        update={
            "memory_type": memory_type,
            "title": context.title,
            "summary": context.summary,
            "payload": payload,
            "findings": [
                *item.findings,
                f"{_tag_slug(contextualizer_name).replace('-', '_')}_contextualized",
                f"memory_type_classified_as_{memory_type}",
            ],
            "metadata": {
                **item.metadata,
                "contextualizer": contextualizer_name,
                "contextualized": True,
                "memory_classification": {
                    **classification.as_metadata(),
                    "applied": classification_applied,
                    "selected_memory_type": memory_type,
                },
            },
        }
    )


def _enriched_child_item(
    item: IngestionItem, context: KnowledgeContext, contextualizer_name: str
) -> IngestionItem:
    payload = item.payload.model_copy(deep=True)
    payload.content = _child_content(payload.content, context)
    payload.tags = _merge_tags(
        payload.tags,
        [
            "knowledge:evidence",
            "context-linked",
            f"contextualizer:{_tag_slug(contextualizer_name)}",
        ],
    )
    payload.metadata = {
        **payload.metadata,
        "parent_context_summary": context.summary,
        "parent_context_purpose": context.purpose,
        "parent_knowledge_category": context.category,
        "parent_context_topics": context.key_topics,
        "contextualizer": contextualizer_name,
        "ingestion_version": "knowledge-v3",
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


def _item_relative_path(item: IngestionItem, payload: MemoryCreate) -> str:
    value = payload.metadata.get("relative_path") or item.metadata.get("relative_path")
    return str(value or "")


def _item_file_extension(item: IngestionItem, payload: MemoryCreate) -> str:
    value = payload.metadata.get("file_extension") or item.metadata.get("file_extension")
    if value:
        return str(value)
    relative_path = _item_relative_path(item, payload)
    return Path(relative_path).suffix


def _selected_macro_memory_type(
    item: IngestionItem,
    payload: MemoryCreate,
    predicted_type: str,
    confidence: float,
) -> tuple[str, bool]:
    relative_path = _item_relative_path(item, payload).replace("\\", "/").lower()
    if relative_path.endswith("/skill.md") or relative_path.endswith("/agents.md"):
        return "skill", True
    if relative_path.endswith("/claude.md") and "skill" in payload.content.lower():
        return "skill", True
    if "/references/" in relative_path or "/reference/" in relative_path:
        return "fact", True
    if "/workflows/" in relative_path or "/workflow/" in relative_path:
        return "workflow", True
    if any(
        marker in relative_path
        for marker in (
            "/installation",
            "/install",
            "/quickstart",
            "/troubleshooting",
            "/runbook",
        )
    ):
        return "runbook", True

    min_confidence = MACRO_CLASSIFICATION_MIN_CONFIDENCE_BY_TYPE.get(predicted_type, 0.68)
    if confidence >= min_confidence:
        return predicted_type, True

    existing_type = item.memory_type or payload.memory_type or "context"
    return existing_type, False


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onebrain-local-import",
        description=(
            "Import learned knowledge from local docs through the OneBrain API after "
            "Codex CLI contextualization."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Deprecated positional docs path. Prefer --docs.",
    )
    parser.add_argument(
        "--docs",
        help="Local docs file or folder path to learn from, categorize, and import as knowledge.",
    )
    parser.add_argument("--api-url", default=os.getenv("ONEBRAIN_API_URL", DEFAULT_API_URL))
    parser.add_argument(
        "--api-timeout-seconds",
        type=float,
        default=float(os.getenv("ONEBRAIN_API_TIMEOUT_SECONDS", str(DEFAULT_API_TIMEOUT_SECONDS))),
        help="Timeout for each OneBrain API request.",
    )
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
    parser.add_argument(
        "--include-evidence-items",
        action="store_true",
        help=(
            "Also import section/evidence memories. By default only knowledge contexts "
            "are committed."
        ),
    )
    parser.add_argument(
        "--commit-batch-size",
        type=int,
        default=int(os.getenv("ONEBRAIN_COMMIT_BATCH_SIZE", str(DEFAULT_COMMIT_BATCH_SIZE))),
        help="Number of source docs per ingestion commit request.",
    )
    parser.add_argument("--skip-codex", action="store_true")
    parser.add_argument("--codex-command", default=os.getenv("ONEBRAIN_CODEX_COMMAND", "codex"))
    parser.add_argument("--codex-model", default=os.getenv("ONEBRAIN_CODEX_MODEL"))
    parser.add_argument("--codex-timeout-seconds", type=int, default=180)
    parser.add_argument("--codex-max-file-chars", type=int, default=16_000)
    parser.add_argument(
        "--codex-batch-size",
        type=int,
        default=int(os.getenv("ONEBRAIN_CODEX_BATCH_SIZE", "8")),
        help="Number of source docs to learn from per Codex CLI call.",
    )
    parser.add_argument(
        "--codex-workers",
        type=int,
        default=int(os.getenv("ONEBRAIN_CODEX_WORKERS", "2")),
        help="Number of concurrent Codex exec workers for contextualization batches.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress logs on stderr.",
    )
    parser.add_argument(
        "--progress-log",
        default=os.getenv("ONEBRAIN_IMPORT_PROGRESS_LOG"),
        help="Optional file path to append progress logs.",
    )
    parser.add_argument("--output", help="Optional path to write the full import result JSON.")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    progress_file: TextIO | None = None
    try:
        progress_streams = [sys.stderr]
        if args.progress_log:
            progress_file = await asyncio.to_thread(
                Path(args.progress_log).open,
                "a",
                encoding="utf-8",
            )
            progress_streams.append(progress_file)
        progress = ProgressReporter(
            enabled=not args.no_progress,
            streams=progress_streams,
        )
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
                    batch_size=args.codex_batch_size,
                    max_workers=args.codex_workers,
                )
            )
        result = await run_local_import(
            LocalImportOptions(
                path=docs_path,
                api_path=args.api_path,
                api_url=args.api_url,
                api_key=args.api_key,
                api_timeout_seconds=args.api_timeout_seconds,
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
                commit_batch_size=args.commit_batch_size,
                include_evidence_items=args.include_evidence_items,
            ),
            contextualizer=contextualizer,
            progress=progress,
        )

        output = result.as_dict()
        rendered = json.dumps(output, indent=2, ensure_ascii=False)
        if args.output:
            await asyncio.to_thread(Path(args.output).write_text, rendered, encoding="utf-8")
            progress.event("wrote output", output=args.output)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(rendered)
    except Exception as exc:  # noqa: BLE001
        parser.exit(1, f"onebrain-local-import: error: {exc}\n")
    finally:
        if progress_file is not None:
            progress_file.close()
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
        "You are preparing a OneBrain knowledge import. You are not importing a file body; "
        "you are learning durable operational knowledge from source evidence. Treat the path "
        "and source ref strictly as provenance, not as the memory topic. Synthesize what the "
        "material teaches, categorize it, and name the real workflow, rule, concept, tool, "
        "pattern, pitfall, or decision it represents. Bring relevant technical knowledge only "
        "when it is directly supported by the evidence. Do not invent unrelated claims. Do not "
        "copy secrets, tokens, or long source text. Return only JSON that matches the provided "
        "schema.\n\n"
        f"Provenance relative path: {document.relative_path}\n"
        f"Provenance source ref: {document.source_ref}\n"
        f"Initial extracted title: {macro_item.title}\n"
        f"Initial extracted summary: {macro_item.summary}\n"
        f"Detected sections JSON: {json.dumps(sections, ensure_ascii=False)}\n\n"
        "<source_evidence>\n"
        f"{file_text}\n"
        "</source_evidence>\n"
    )


def _context_batch_prompt(
    *,
    root_path: Path,
    requests: list[KnowledgeContextRequest],
    redact_secrets: bool,
    max_file_chars: int,
) -> str:
    documents: list[dict[str, Any]] = []
    for request in requests:
        text = _read_text(_local_file_path(root_path, request.document.relative_path))
        if redact_secrets:
            text, _ = redact_secret_text(text)
        documents.append(
            {
                "document_id": request.document.id,
                "provenance_relative_path": request.document.relative_path,
                "provenance_source_ref": request.document.source_ref,
                "initial_title": request.macro_item.title,
                "initial_summary": request.macro_item.summary,
                "detected_sections": [
                    {
                        "title": item.title,
                        "summary": item.summary,
                        "memory_type": item.memory_type,
                        "source_ref": item.source_ref,
                    }
                    for item in request.child_items[:16]
                ],
                "source_evidence": _truncate(text, max_file_chars),
            }
        )
    return (
        "You are preparing a OneBrain knowledge import for multiple local docs. You are not "
        "importing file bodies; you are learning durable operational knowledge from source "
        "evidence. For every input document_id, synthesize one knowledge profile. Treat paths "
        "and source refs strictly as provenance, not memory topics. Categorize the knowledge, "
        "name the real workflow, rule, concept, tool, pattern, pitfall, or decision represented, "
        "and include graph/search entities. Bring relevant technical knowledge only when it is "
        "directly supported by the evidence. Do not invent unrelated claims. Do not copy secrets, "
        "tokens, or long source text. Return only JSON that matches the provided schema.\n\n"
        f"Source docs JSON: {json.dumps(documents, ensure_ascii=False)}\n"
    )


def _knowledge_context_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "summary",
            "purpose",
            "domain",
            "category",
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
            "category": {"type": "string", "maxLength": 120},
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


def _knowledge_context_batch_schema() -> dict[str, Any]:
    item_schema = _knowledge_context_schema()
    item_properties = {
        "document_id": {"type": "string", "minLength": 1, "maxLength": 120},
        **item_schema["properties"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["contexts"],
        "properties": {
            "contexts": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["document_id", *item_schema["required"]],
                    "properties": item_properties,
                },
            }
        },
    }


def _parse_knowledge_context(output: str) -> KnowledgeContext:
    parsed = _parse_json_object(output)
    try:
        return KnowledgeContext.model_validate(parsed)
    except ValidationError as exc:
        raise RuntimeError(f"codex context did not match schema: {exc}") from exc


def _parse_knowledge_context_batch(output: str) -> dict[str, KnowledgeContext]:
    parsed = _parse_json_object(output)
    contexts = parsed.get("contexts")
    if not isinstance(contexts, list):
        raise RuntimeError("codex batch context response must include a contexts array")
    output_by_document: dict[str, KnowledgeContext] = {}
    for raw_context in contexts:
        if not isinstance(raw_context, dict):
            raise RuntimeError("codex batch context items must be JSON objects")
        document_id = raw_context.get("document_id")
        if not isinstance(document_id, str) or not document_id.strip():
            raise RuntimeError("codex batch context item missing document_id")
        context_payload = {key: value for key, value in raw_context.items() if key != "document_id"}
        try:
            output_by_document[document_id] = KnowledgeContext.model_validate(context_payload)
        except ValidationError as exc:
            raise RuntimeError(f"codex batch context did not match schema: {exc}") from exc
    return output_by_document


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


def _macro_content(existing: str, context: KnowledgeContext, contextualizer_name: str) -> str:
    topics = ", ".join(context.key_topics) if context.key_topics else "none"
    sections = ", ".join(context.important_sections) if context.important_sections else "none"
    lines = [
        f"# {context.title}",
        "",
        f"Summary: {context.summary}",
        f"Purpose: {context.purpose}",
        f"Domain: {context.domain or 'unspecified'}",
        f"Category: {context.category or 'uncategorized'}",
        f"Key topics: {topics}",
        f"Supporting evidence: {sections}",
        "",
        f"{_contextualization_label(contextualizer_name)} learned knowledge:",
        _entity_lines(context),
        "",
        "Source evidence summary:",
        existing.strip(),
    ]
    return "\n".join(line for line in lines if line is not None).strip()


def _contextualization_label(contextualizer_name: str) -> str:
    if contextualizer_name == "codex-cli":
        return "Codex"
    if contextualizer_name == "heuristic":
        return "Heuristic"
    return contextualizer_name.replace("-", " ").title()


def _child_content(existing: str, context: KnowledgeContext) -> str:
    return (
        f"Parent knowledge context: {context.summary}\n"
        f"Knowledge purpose: {context.purpose}\n"
        f"Knowledge category: {context.category or 'uncategorized'}\n\n"
        f"{existing.strip()}"
    ).strip()


def _entity_lines(context: KnowledgeContext) -> str:
    if not context.entities:
        return "- No explicit entities identified."
    return "\n".join(
        f"- {entity.name} ({entity.entity_type}): {entity.summary}".rstrip()
        for entity in context.entities
    )


def _merge_entities(
    existing: list[EntityInput],
    context: KnowledgeContext,
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


def _context_tags(context: KnowledgeContext, contextualizer_name: str) -> list[str]:
    tags = ["llm:codex"] if contextualizer_name == "codex-cli" else []
    if context.domain:
        tags.append(f"domain:{_tag_slug(context.domain)}")
    if context.category:
        tags.append(f"category:{_tag_slug(context.category)}")
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


def _heuristic_domain(topics: list[str]) -> str:
    topic_text = " ".join(topics).casefold()
    if "robot" in topic_text or "browser" in topic_text:
        return "Robot Framework Browser E2E testing"
    if "api" in topic_text or "http" in topic_text:
        return "API engineering"
    if "django" in topic_text:
        return "Django application engineering"
    if "mcp" in topic_text:
        return "MCP integration"
    return "knowledge management"


def _heuristic_category(document: IngestionDocument, topics: list[str]) -> str:
    text = f"{document.title} {document.summary} {' '.join(topics)}".casefold()
    if any(term in text for term in ["pitfall", "error", "fail", "timeout", "dryrun"]):
        return "engineering pitfall"
    if any(term in text for term in ["rule", "separator", "contract", "schema"]):
        return "implementation rule"
    if any(term in text for term in ["workflow", "process", "orchestration"]):
        return "workflow guidance"
    if any(term in text for term in ["pattern", "architecture", "design"]):
        return "engineering pattern"
    return "technical knowledge"


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


def _batches(values: list[T], size: int) -> list[list[T]]:
    safe_size = max(1, size)
    return [values[index : index + safe_size] for index in range(0, len(values), safe_size)]


def _contextualizer_batch_size(contextualizer: Contextualizer) -> int:
    value = getattr(contextualizer, "batch_size", 1)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _contextualizer_worker_count(contextualizer: Contextualizer) -> int:
    value = getattr(contextualizer, "max_workers", 1)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


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
