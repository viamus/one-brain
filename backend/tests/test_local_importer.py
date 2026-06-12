from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from onebrain.core.contracts.schemas import (
    IngestionAnalyzeRequest,
    IngestionCommitRequest,
    IngestionCommitResult,
    IngestionDocument,
    IngestionItem,
)
from onebrain.core.ingestion import analyze_memory_files
from onebrain.tools import local_importer
from onebrain.tools.local_importer import (
    CodexCliContextualizer,
    CodexCliOptions,
    KnowledgeContext,
    KnowledgeContextRequest,
    KnowledgeEntityContext,
    LocalImportOptions,
    ProgressReporter,
    _context_batch_prompt,
    _context_prompt,
    _knowledge_context_batch_schema,
    _knowledge_context_schema,
    _load_scope,
    _parse_knowledge_context,
    _parse_knowledge_context_batch,
    _resolve_docs_path,
    run_local_import,
)


class FakeApiClient:
    def __init__(self, local_path: Path) -> None:
        self.local_path = local_path
        self.analyze_request: IngestionAnalyzeRequest | None = None
        self.commit_request: IngestionCommitRequest | None = None
        self.commit_requests: list[IngestionCommitRequest] = []

    async def analyze(self, request: IngestionAnalyzeRequest):
        self.analyze_request = request
        local_request = request.model_copy(update={"path": str(self.local_path)})
        return analyze_memory_files(local_request)

    async def commit(self, request: IngestionCommitRequest) -> IngestionCommitResult:
        self.commit_request = request
        self.commit_requests.append(request)
        created_ids = (
            [] if request.dry_run else [f"memory-{item.id}" for item in request.plan.items]
        )
        return IngestionCommitResult(
            dry_run=request.dry_run,
            documents=len(request.plan.documents),
            items=len(request.plan.items),
            created=0 if request.dry_run else len(request.plan.items),
            created_ids=created_ids,
            memory_id_by_item_id={
                item.id: f"memory-{item.id}" for item in request.plan.items if not request.dry_run
            },
        )


class FakeContextualizer:
    name = "codex-cli"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def contextualize(
        self,
        *,
        root_path: Path,
        document: IngestionDocument,
        macro_item: IngestionItem,
        child_items: list[IngestionItem],
        redact_secrets: bool,
    ) -> KnowledgeContext:
        assert root_path
        assert macro_item.item_type == "document"
        assert child_items
        assert redact_secrets is True
        self.calls.append(document.relative_path)
        return KnowledgeContext(
            title="Release orchestration context",
            summary="Explains how release orchestration coordinates build and deployment gates.",
            purpose=(
                "Help agents understand release flow responsibilities before using source evidence."
            ),
            domain="release engineering",
            category="workflow guidance",
            key_topics=["Release Train", "Build Gates", "Deployment"],
            important_sections=["Build", "Deploy"],
            entities=[
                KnowledgeEntityContext(
                    name="Release Train",
                    entity_type="concept",
                    summary="Release coordination process described by the source evidence.",
                )
            ],
            tags=["release-flow"],
            confidence=0.91,
        )


class FakeBatchContextualizer:
    name = "codex-cli"
    batch_size = 10

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def contextualize_batch(
        self,
        *,
        root_path: Path,
        requests: list[KnowledgeContextRequest],
        redact_secrets: bool,
    ) -> dict[str, KnowledgeContext]:
        assert root_path
        assert redact_secrets is True
        self.calls.append([request.document.relative_path for request in requests])
        return {
            request.document.id: KnowledgeContext(
                title=f"Knowledge: {request.document.title}",
                summary=f"Learned knowledge from {request.document.title}.",
                purpose="Preserve learned knowledge from source evidence.",
                domain="engineering knowledge",
                category="technical knowledge",
                key_topics=[request.document.title],
                important_sections=[item.title for item in request.child_items],
                entities=[
                    KnowledgeEntityContext(
                        name=request.document.title,
                        entity_type="concept",
                        summary="Concept learned from source evidence.",
                    )
                ],
                tags=["batch"],
                confidence=0.9,
            )
            for request in requests
        }


class FakeSkillContextualizer:
    name = "heuristic"
    batch_size = 10

    async def contextualize_batch(
        self,
        *,
        root_path: Path,
        requests: list[KnowledgeContextRequest],
        redact_secrets: bool,
    ) -> dict[str, KnowledgeContext]:
        assert root_path
        assert redact_secrets is True
        return {
            request.document.id: KnowledgeContext(
                title="Angular developer skill",
                summary="Guides agents through Angular components, routing, testing, and services.",
                purpose="Help agents generate Angular code using official framework patterns.",
                domain="frontend engineering",
                category="agent skill",
                key_topics=["Angular", "Components", "Routing", "Testing"],
                important_sections=["When to use", "References"],
                entities=[
                    KnowledgeEntityContext(
                        name="Angular",
                        entity_type="framework",
                        summary="Frontend framework taught by this skill.",
                    )
                ],
                tags=["angular", "agent-skill"],
                confidence=0.9,
            )
            for request in requests
        }


class SlowParallelBatchContextualizer(FakeBatchContextualizer):
    batch_size = 1
    max_workers = 2

    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.max_active = 0

    async def contextualize_batch(
        self,
        *,
        root_path: Path,
        requests: list[KnowledgeContextRequest],
        redact_secrets: bool,
    ) -> dict[str, KnowledgeContext]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.01)
            return await super().contextualize_batch(
                root_path=root_path,
                requests=requests,
                redact_secrets=redact_secrets,
            )
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_local_import_enriches_ingestion_plan_before_api_commit(tmp_path) -> None:
    source = tmp_path / "catalog" / "release.md"
    source.parent.mkdir()
    source.write_text(
        "# Release Guide\n\nCoordinate release work.\n\n"
        "## Build\n\nRun checks.\n\n"
        "## Deploy\n\nPromote approved artifacts.\n",
        encoding="utf-8",
    )
    api_client = FakeApiClient(tmp_path)
    contextualizer = FakeContextualizer()

    result = await run_local_import(
        LocalImportOptions(
            path=tmp_path,
            api_path="/mnt/catalog",
            scope={"project": "one-brain"},
            source_ref_prefix="catalog://test",
            include_evidence_items=True,
        ),
        api_client=api_client,
        contextualizer=contextualizer,
    )

    assert api_client.analyze_request is not None
    assert api_client.analyze_request.path == "/mnt/catalog"
    assert api_client.commit_request is not None
    assert api_client.commit_request.plan.stats["contextualized_documents"] == 1
    assert contextualizer.calls == ["catalog/release.md"]
    assert result.commit is not None
    assert result.commit.created == len(result.plan.items)

    macro = next(item for item in result.plan.items if item.item_type == "document")
    children = [item for item in result.plan.items if item.item_type == "section"]

    assert macro.title == "Release orchestration context"
    assert macro.summary.startswith("Explains how release orchestration")
    assert "Purpose: Help agents understand release flow" in macro.payload.content
    assert "topic:release-train" in macro.payload.tags
    assert "release-flow" in macro.payload.tags
    assert macro.payload.metadata["contextualized"] is True
    assert macro.payload.metadata["domain"] == "release engineering"
    assert macro.payload.metadata["knowledge_category"] == "workflow guidance"
    assert "category:workflow-guidance" in macro.payload.tags
    assert "knowledge:imported" in macro.payload.tags
    assert any(entity.name == "Release Train" for entity in macro.payload.entities)

    assert children
    assert children[0].payload.content.startswith("Parent knowledge context:")
    assert children[0].payload.metadata["parent_knowledge_category"] == "workflow guidance"
    assert children[0].payload.metadata["parent_context_topics"] == [
        "Release Train",
        "Build Gates",
        "Deployment",
    ]


@pytest.mark.asyncio
async def test_local_import_uses_batch_contextualizer_for_multiple_docs(tmp_path) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First\n\nKnowledge one.\n\n## Detail\n\nAlpha.", encoding="utf-8")
    second.write_text("# Second\n\nKnowledge two.\n\n## Detail\n\nBeta.", encoding="utf-8")
    api_client = FakeApiClient(tmp_path)
    contextualizer = FakeBatchContextualizer()

    result = await run_local_import(
        LocalImportOptions(path=tmp_path, source_ref_prefix="catalog://batch"),
        api_client=api_client,
        contextualizer=contextualizer,
    )

    assert len(contextualizer.calls) == 1
    assert sorted(contextualizer.calls[0]) == ["first.md", "second.md"]
    assert result.plan.stats["contextualized_documents"] == 2
    assert result.plan.stats["fallback_contextualizations"] == 0


@pytest.mark.asyncio
async def test_local_import_omits_evidence_items_by_default(tmp_path) -> None:
    source = tmp_path / "guide.md"
    source.write_text("# Guide\n\nKnowledge.\n\n## Detail\n\nEvidence.", encoding="utf-8")

    result = await run_local_import(
        LocalImportOptions(path=tmp_path),
        api_client=FakeApiClient(tmp_path),
        contextualizer=FakeBatchContextualizer(),
    )

    assert {item.item_type for item in result.plan.items} == {"document"}
    assert result.plan.stats["evidence_items_included"] is False
    assert result.plan.stats["omitted_evidence_items"] > 0


@pytest.mark.asyncio
async def test_local_import_classifies_enriched_macro_memory_type(tmp_path) -> None:
    source = tmp_path / "skills" / "angular-developer" / "SKILL.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# Angular Developer\n\nUse this skill for Angular components and routing.\n\n"
        "## References\n\nTesting and service guidance.",
        encoding="utf-8",
    )

    result = await run_local_import(
        LocalImportOptions(path=tmp_path),
        api_client=FakeApiClient(tmp_path),
        contextualizer=FakeSkillContextualizer(),
    )

    macro = next(item for item in result.plan.items if item.item_type == "document")

    assert macro.memory_type == "skill"
    assert macro.payload.memory_type == "skill"
    assert "memory-type:skill" in macro.payload.tags
    assert macro.payload.metadata["memory_classification"]["memory_type"] == "skill"
    assert "memory_type_classified_as_skill" in macro.findings


@pytest.mark.asyncio
async def test_local_import_treats_skill_references_as_facts(tmp_path) -> None:
    source = tmp_path / "skills" / "seo" / "references" / "rate-limits.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# Rate Limits\n\nUse this reference for API quotas and retry timing.\n\n"
        "## Limits\n\nRespect provider rate limits.",
        encoding="utf-8",
    )

    result = await run_local_import(
        LocalImportOptions(path=tmp_path),
        api_client=FakeApiClient(tmp_path),
        contextualizer=FakeSkillContextualizer(),
    )

    macro = next(item for item in result.plan.items if item.item_type == "document")

    assert macro.memory_type == "fact"
    assert macro.payload.memory_type == "fact"
    assert "memory-type:fact" in macro.payload.tags
    assert macro.payload.metadata["memory_classification"]["selected_memory_type"] == "fact"


@pytest.mark.asyncio
async def test_local_import_runs_codex_batches_with_worker_parallelism(tmp_path) -> None:
    for name in ("first", "second", "third"):
        (tmp_path / f"{name}.md").write_text(
            f"# {name.title()}\n\nKnowledge for {name}.\n\n## Detail\n\nEvidence.",
            encoding="utf-8",
        )
    contextualizer = SlowParallelBatchContextualizer()

    result = await run_local_import(
        LocalImportOptions(path=tmp_path),
        api_client=FakeApiClient(tmp_path),
        contextualizer=contextualizer,
    )

    assert contextualizer.max_active == 2
    assert len(contextualizer.calls) == 3
    assert result.plan.stats["contextualized_documents"] == 3


@pytest.mark.asyncio
async def test_local_import_commits_documents_in_batches(tmp_path) -> None:
    for name in ("first", "second", "third"):
        (tmp_path / f"{name}.md").write_text(
            f"# {name.title()}\n\nKnowledge for {name}.\n\n## Detail\n\nEvidence.",
            encoding="utf-8",
        )
    api_client = FakeApiClient(tmp_path)

    result = await run_local_import(
        LocalImportOptions(
            path=tmp_path,
            source_ref_prefix="catalog://batch-commit",
            commit_batch_size=2,
        ),
        api_client=api_client,
        contextualizer=FakeBatchContextualizer(),
    )

    assert len(api_client.commit_requests) == 2
    assert [len(request.plan.documents) for request in api_client.commit_requests] == [2, 1]
    for request in api_client.commit_requests:
        document_ids = {document.id for document in request.plan.documents}
        assert {item.document_id for item in request.plan.items} == document_ids
    assert result.commit is not None
    assert result.commit.documents == 3
    assert result.commit.items == len(result.plan.items)
    assert result.commit.created == len(result.plan.items)
    assert len(result.commit.created_ids) == len(result.plan.items)


@pytest.mark.asyncio
async def test_local_import_reports_iterative_progress(tmp_path) -> None:
    source = tmp_path / "note.md"
    source.write_text("# Note\n\nUseful knowledge.\n\n## Detail\n\nEvidence.", encoding="utf-8")
    stream = io.StringIO()

    await run_local_import(
        LocalImportOptions(path=tmp_path),
        api_client=FakeApiClient(tmp_path),
        contextualizer=FakeBatchContextualizer(),
        progress=ProgressReporter(streams=[stream]),
    )

    progress = stream.getvalue()

    assert "analyzing docs" in progress
    assert "contextualizing batch" in progress
    assert "committing batch" in progress
    assert "committed import" in progress


@pytest.mark.asyncio
async def test_local_import_supports_dry_run_commit(tmp_path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("One useful operational paragraph.", encoding="utf-8")
    api_client = FakeApiClient(tmp_path)

    result = await run_local_import(
        LocalImportOptions(path=tmp_path, dry_run=True),
        api_client=api_client,
        contextualizer=FakeContextualizer(),
    )

    assert api_client.commit_request is not None
    assert api_client.commit_request.dry_run is True
    assert result.commit is not None
    assert result.commit.dry_run is True
    assert result.commit.created == 0


def test_parse_knowledge_context_accepts_fenced_json() -> None:
    context = _parse_knowledge_context(
        """```json
        {
          "title": "Mediator XML context",
          "summary": "Explains mediator XML mapping contracts.",
          "purpose": "Help agents understand why mediator XML exists.",
          "domain": "integration",
          "category": "contract knowledge",
          "key_topics": ["Mediator", "XML"],
          "important_sections": ["Mappings"],
          "entities": [
            {
              "name": "Mediator",
              "entity_type": "technology",
              "summary": "Integration mediator mentioned by the source evidence."
            }
          ],
          "tags": ["integration"],
          "confidence": 0.88
        }
        ```"""
    )

    assert context.title == "Mediator XML context"
    assert context.entities[0].name == "Mediator"
    assert context.key_topics == ["Mediator", "XML"]


def test_knowledge_prompt_treats_docs_as_source_evidence() -> None:
    document = IngestionDocument(
        id="document-1",
        relative_path="docs/rule.md",
        source_ref="catalog://docs/rule.md",
        title="Rule",
        summary="Initial summary",
        content_hash="hash",
        byte_length=42,
        item_count=1,
    )
    macro = IngestionItem(
        id="item-1",
        document_id=document.id,
        order_index=0,
        item_type="document",
        memory_type="context",
        title="Rule",
        summary="Initial summary",
        source_ref="catalog://docs/rule.md#document",
        payload={
            "memory_type": "context",
            "title": "Rule",
            "content": "Rule content",
            "source": {"source_type": "test", "source_ref": "catalog://docs/rule.md"},
        },
    )

    prompt = _context_prompt(
        document=document,
        macro_item=macro,
        child_items=[],
        file_text="Use this as source evidence.",
    )

    assert "You are not importing a file body" in prompt
    assert "<source_evidence>" in prompt
    assert "Synthesize what the material teaches" in prompt


def test_knowledge_context_schema_requires_category() -> None:
    schema = _knowledge_context_schema()

    assert "category" in schema["required"]
    assert schema["properties"]["category"]["maxLength"] == 120


def test_knowledge_context_batch_schema_requires_document_id_and_category() -> None:
    schema = _knowledge_context_batch_schema()
    item_schema = schema["properties"]["contexts"]["items"]

    assert "document_id" in item_schema["required"]
    assert "category" in item_schema["required"]


def test_parse_knowledge_context_batch_returns_context_by_document_id() -> None:
    contexts = _parse_knowledge_context_batch(
        """{
          "contexts": [
            {
              "document_id": "document-1",
              "title": "Knowledge one",
              "summary": "Summary one.",
              "purpose": "Purpose one.",
              "domain": "engineering",
              "category": "technical rule",
              "key_topics": ["Rule"],
              "important_sections": ["Evidence"],
              "entities": [],
              "tags": ["rule"],
              "confidence": 0.9
            }
          ]
        }"""
    )

    assert contexts["document-1"].title == "Knowledge one"
    assert contexts["document-1"].category == "technical rule"


def test_knowledge_batch_prompt_includes_all_document_ids(tmp_path) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("Alpha knowledge.", encoding="utf-8")
    second.write_text("Beta knowledge.", encoding="utf-8")
    requests = [
        KnowledgeContextRequest(
            document=IngestionDocument(
                id="document-1",
                relative_path="first.md",
                source_ref="catalog://first.md",
                title="First",
                summary="First summary",
                content_hash="hash-1",
                byte_length=10,
                item_count=1,
            ),
            macro_item=IngestionItem(
                id="item-1",
                document_id="document-1",
                order_index=0,
                item_type="document",
                memory_type="context",
                title="First",
                summary="First summary",
                source_ref="catalog://first.md#document",
                payload={
                    "memory_type": "context",
                    "title": "First",
                    "content": "First",
                    "source": {"source_type": "test", "source_ref": "catalog://first.md"},
                },
            ),
            child_items=[],
        ),
        KnowledgeContextRequest(
            document=IngestionDocument(
                id="document-2",
                relative_path="second.md",
                source_ref="catalog://second.md",
                title="Second",
                summary="Second summary",
                content_hash="hash-2",
                byte_length=10,
                item_count=1,
            ),
            macro_item=IngestionItem(
                id="item-2",
                document_id="document-2",
                order_index=0,
                item_type="document",
                memory_type="context",
                title="Second",
                summary="Second summary",
                source_ref="catalog://second.md#document",
                payload={
                    "memory_type": "context",
                    "title": "Second",
                    "content": "Second",
                    "source": {"source_type": "test", "source_ref": "catalog://second.md"},
                },
            ),
            child_items=[],
        ),
    ]

    prompt = _context_batch_prompt(
        root_path=tmp_path,
        requests=requests,
        redact_secrets=True,
        max_file_chars=100,
    )

    assert "multiple local docs" in prompt
    assert '"document_id": "document-1"' in prompt
    assert '"document_id": "document-2"' in prompt


def test_codex_cli_contextualizer_uses_top_level_approval_and_utf8(monkeypatch, tmp_path) -> None:
    calls = {}

    def fake_run(args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        output_path = Path(args[args.index("--output-last-message") + 1])
        output_path.write_text(
            """{
              "title": "Unicode context",
              "summary": "Handles UTF-8 prompt and response text.",
              "purpose": "Avoid Windows console encoding failures.",
              "domain": "developer tooling",
              "category": "tooling rule",
              "key_topics": ["UTF-8", "Codex CLI"],
              "important_sections": ["Encoding"],
              "entities": [],
              "tags": ["unicode"],
              "confidence": 0.9
            }""",
            encoding="utf-8",
        )

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr(local_importer.subprocess, "run", fake_run)
    contextualizer = CodexCliContextualizer(CodexCliOptions(command="codex", timeout_seconds=10))

    output = contextualizer._run_codex(
        "Texto com acentua\u00e7\u00e3o e s\u00edmbolo \uc801.", tmp_path
    )
    parsed = _parse_knowledge_context(output)

    args = calls["args"]
    assert args.index("--ask-for-approval") < args.index("exec")
    assert calls["kwargs"]["encoding"] == "utf-8"
    assert calls["kwargs"]["errors"] == "replace"
    assert parsed.title == "Unicode context"


def test_load_scope_from_json_file(tmp_path) -> None:
    scope_file = tmp_path / "scope.json"
    scope_file.write_text('{"organization":"abinbev","catalog":"private"}', encoding="utf-8")

    scope = _load_scope("{}", str(scope_file))

    assert scope == {"organization": "abinbev", "catalog": "private"}


def test_load_scope_rejects_inline_and_file(tmp_path) -> None:
    scope_file = tmp_path / "scope.json"
    scope_file.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="either --scope-json or --scope-json-file"):
        _load_scope('{"organization":"abinbev"}', str(scope_file))


def test_resolve_docs_path_prefers_explicit_docs_parameter() -> None:
    assert _resolve_docs_path("docs", None) == Path("docs")


def test_resolve_docs_path_accepts_legacy_positional_parameter() -> None:
    assert _resolve_docs_path(None, "legacy-docs") == Path("legacy-docs")


def test_resolve_docs_path_rejects_missing_path() -> None:
    with pytest.raises(ValueError, match="--docs is required"):
        _resolve_docs_path(None, None)


def test_resolve_docs_path_rejects_docs_and_positional_path() -> None:
    with pytest.raises(ValueError, match="either --docs or the positional docs path"):
        _resolve_docs_path("docs", "legacy-docs")
