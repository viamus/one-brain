from __future__ import annotations

from pathlib import Path

import pytest

from onebrain_core.contracts.schemas import (
    IngestionAnalyzeRequest,
    IngestionCommitRequest,
    IngestionCommitResult,
    IngestionDocument,
    IngestionItem,
)
from onebrain_core.ingestion import analyze_memory_files, local_importer
from onebrain_core.ingestion.local_importer import (
    CodexCliContextualizer,
    CodexCliOptions,
    FileContext,
    FileEntityContext,
    LocalImportOptions,
    _load_scope,
    _parse_file_context,
    run_local_import,
)


class FakeApiClient:
    def __init__(self, local_path: Path) -> None:
        self.local_path = local_path
        self.analyze_request: IngestionAnalyzeRequest | None = None
        self.commit_request: IngestionCommitRequest | None = None

    async def analyze(self, request: IngestionAnalyzeRequest):
        self.analyze_request = request
        local_request = request.model_copy(update={"path": str(self.local_path)})
        return analyze_memory_files(local_request)

    async def commit(self, request: IngestionCommitRequest) -> IngestionCommitResult:
        self.commit_request = request
        return IngestionCommitResult(
            dry_run=request.dry_run,
            documents=len(request.plan.documents),
            items=len(request.plan.items),
            created=0 if request.dry_run else len(request.plan.items),
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
    ) -> FileContext:
        assert root_path
        assert macro_item.item_type == "document"
        assert child_items
        assert redact_secrets is True
        self.calls.append(document.relative_path)
        return FileContext(
            title="Release orchestration context",
            summary="Explains how release orchestration coordinates build and deployment gates.",
            purpose=(
                "Help agents understand release flow responsibilities before using file details."
            ),
            domain="release engineering",
            key_topics=["Release Train", "Build Gates", "Deployment"],
            important_sections=["Build", "Deploy"],
            entities=[
                FileEntityContext(
                    name="Release Train",
                    entity_type="concept",
                    summary="Release coordination process described by the file.",
                )
            ],
            tags=["release-flow"],
            confidence=0.91,
        )


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
    assert any(entity.name == "Release Train" for entity in macro.payload.entities)

    assert children
    assert children[0].payload.content.startswith("Parent file context:")
    assert children[0].payload.metadata["parent_context_topics"] == [
        "Release Train",
        "Build Gates",
        "Deployment",
    ]


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


def test_parse_file_context_accepts_fenced_json() -> None:
    context = _parse_file_context(
        """```json
        {
          "title": "Mediator XML context",
          "summary": "Explains mediator XML mapping contracts.",
          "purpose": "Help agents understand why mediator XML exists.",
          "domain": "integration",
          "key_topics": ["Mediator", "XML"],
          "important_sections": ["Mappings"],
          "entities": [
            {
              "name": "Mediator",
              "entity_type": "technology",
              "summary": "Integration mediator mentioned by the file."
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
    parsed = _parse_file_context(output)

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
