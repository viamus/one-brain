from __future__ import annotations

import json

from onebrain_ml.cli import main as memory_classifier_main
from onebrain_ml.memory_classification import (
    RUNTIME_MODEL_PATH_ENV,
    MemoryClassificationInput,
    TrainingExample,
    classify_memory_type,
    clear_runtime_classifier_cache,
    load_memory_classifier,
)
from onebrain_ml.memory_classification_training import (
    TrainingExampleSource,
    balance_training_examples,
    cross_validate_memory_classifier,
    seed_training_example_sources,
    split_training_validation,
    train_validate_memory_classifier,
    training_examples_from_file_corpus,
    training_examples_from_memories,
)


def test_memory_classifier_learns_decision_language() -> None:
    result = classify_memory_type(
        MemoryClassificationInput(
            relative_path="architecture-choice.md",
            title="Storage choice",
            content=(
                "Decision: we accepted PostgreSQL as the canonical memory store. "
                "Consequences include migrations, backups, and transaction boundaries."
            ),
        )
    )

    assert result.memory_type == "decision"
    assert result.confidence > 0.3
    assert result.method == "ml"
    assert result.reasons


def test_memory_classifier_recognizes_portuguese_pitfall_language() -> None:
    result = classify_memory_type(
        MemoryClassificationInput(
            relative_path="notes/vector-size.md",
            content=(
                "Armadilha: nao assumir que a tabela pgvector aceita outro tamanho "
                "de vetor sem recriar a coluna."
            ),
        )
    )

    assert result.memory_type == "pitfall"
    assert result.confidence > 0.3


def test_training_examples_from_memories_avoid_self_training_loops() -> None:
    memories = [
        {
            "memory_type": "rule",
            "status": "active",
            "title": "Manual rule",
            "content": "Must keep production API keys configured.",
            "confidence": 0.9,
            "source_ref": "memory://rule",
            "metadata": {},
        },
        {
            "memory_type": "decision",
            "status": "active",
            "title": "ML decision",
            "content": "Decision: use PostgreSQL.",
            "confidence": 0.9,
            "source_ref": "memory://ml-decision",
            "metadata": {"memory_classification": {"method": "ml"}},
        },
        {
            "memory_type": "note",
            "status": "active",
            "title": "Corrected type",
            "content": "Pitfall: do not change vector dimensions without rebuilding.",
            "confidence": 0.4,
            "source_ref": "memory://corrected",
            "metadata": {"memory_type_correction": {"corrected_type": "pitfall"}},
        },
        {
            "memory_type": "workflow",
            "status": "active",
            "title": "Accepted ML workflow",
            "content": "Checklist: test, deploy, verify health, notify.",
            "confidence": 0.9,
            "source_ref": "memory://accepted",
            "metadata": {"memory_classification": {"method": "ml", "accepted": True}},
        },
    ]

    examples = training_examples_from_memories(memories)

    labels = [item.example.memory_type for item in examples]
    assert labels == ["rule", "pitfall", "workflow"]
    assert "memory://ml-decision" not in {item.source_ref for item in examples}
    assert {item.reason for item in examples} == {
        "manual_or_heuristic_memory_type",
        "corrected_memory_type",
        "accepted_ml_classification",
    }


def test_training_examples_from_orm_memory_prefers_metadata_() -> None:
    class MemoryLike:
        memory_type = "rule"
        status = "active"
        title = "ORM memory"
        content = "Must prefer metadata_ over SQLAlchemy declarative metadata."
        confidence = 0.9
        source_ref = "memory://orm"
        metadata = object()
        metadata_ = {"relative_path": "rules/runtime.md"}

    examples = training_examples_from_memories([MemoryLike()])

    assert len(examples) == 1
    assert examples[0].example.relative_path == "rules/runtime.md"


def test_training_examples_from_file_corpus_uses_only_strong_labels(tmp_path) -> None:
    repo = tmp_path / "agent-rules-books"
    (repo / "clean-code").mkdir(parents=True)
    (repo / "clean-code" / "AGENTS.md").write_text(
        "# Clean Code rules\n\nThis rule set tells agents to keep functions small.",
        encoding="utf-8",
    )
    (repo / "skills" / "reviewer").mkdir(parents=True)
    (repo / "skills" / "reviewer" / "SKILL.md").write_text(
        "# Reviewer\n\nUse this skill when reviewing pull requests.",
        encoding="utf-8",
    )
    (repo / "random").mkdir()
    (repo / "random" / "notes.md").write_text(
        "A loose note with no strong training label.",
        encoding="utf-8",
    )

    examples = training_examples_from_file_corpus(
        repo,
        source_ref_prefix="github://ciembor/agent-rules-books",
    )

    labels_by_ref = {item.source_ref: item.example.memory_type for item in examples}
    assert labels_by_ref["github://ciembor/agent-rules-books/clean-code/AGENTS.md"] == "skill"
    assert labels_by_ref["github://ciembor/agent-rules-books/skills/reviewer/SKILL.md"] == "skill"
    assert not any(item.source_ref.endswith("random/notes.md") for item in examples)
    assert {item.source_kind for item in examples} == {"file-corpus"}


def test_training_examples_from_file_corpus_excludes_generated_dirs(tmp_path) -> None:
    repo = tmp_path / "github-private-catalog"
    (repo / "skills" / "reviewer").mkdir(parents=True)
    (repo / "skills" / "reviewer" / "SKILL.md").write_text(
        "# Reviewer\n\nUse this skill when reviewing pull requests.",
        encoding="utf-8",
    )
    (repo / "workflows" / "release").mkdir(parents=True)
    (repo / "workflows" / "release" / "workflow.json").write_text(
        '{"name":"Release","description":"Checklist workflow for releases."}',
        encoding="utf-8",
    )
    (repo / "build-check-release").mkdir()
    (repo / "build-check-release" / "app.deps.json").write_text(
        '{"runtimeTarget":{"name":"netcoreapp"}}',
        encoding="utf-8",
    )

    examples = training_examples_from_file_corpus(
        repo,
        source_ref_prefix="catalog://github-private-catalog",
        exclude_dirs={"build-check-release"},
    )

    labels_by_ref = {item.source_ref: item.example.memory_type for item in examples}
    assert labels_by_ref["catalog://github-private-catalog/skills/reviewer/SKILL.md"] == "skill"
    assert (
        labels_by_ref["catalog://github-private-catalog/workflows/release/workflow.json"]
        == "workflow"
    )
    assert not any("build-check-release" in str(item.source_ref) for item in examples)


def test_balance_training_examples_caps_dominant_classes() -> None:
    examples = seed_training_example_sources()
    context_examples = [
        TrainingExampleSource(
            example=TrainingExample(
                memory_type="context",
                text=f"Context example {index}",
                title=f"Context {index}",
            ),
            source_ref=f"test://context/{index}",
            source_kind="file-corpus",
        )
        for index in range(20)
    ]

    balanced = balance_training_examples(
        [*examples, *context_examples],
        max_examples_per_type=3,
        seed=7,
    )

    counts: dict[str, int] = {}
    for item in balanced:
        counts[item.example.memory_type] = counts.get(item.example.memory_type, 0) + 1
    assert max(counts.values()) <= 3


def test_training_pipeline_splits_cross_validates_and_writes_runtime_artifact(tmp_path) -> None:
    examples = seed_training_example_sources()
    model_path = tmp_path / "memory-classifier.json"

    split = split_training_validation(examples, validation_ratio=0.2, seed=7)
    assert split.training
    assert split.validation

    classifier, report = train_validate_memory_classifier(
        examples,
        validation_ratio=0.2,
        seed=7,
        folds=3,
        model_out=model_path,
    )
    loaded = load_memory_classifier(model_path)
    result = loaded.classify(
        MemoryClassificationInput(
            title="Architecture decision",
            content="Decision: keep Python and defer .NET migration.",
        )
    )

    assert model_path.exists()
    assert report.training_examples == len(split.training)
    assert report.validation_examples == len(split.validation)
    assert report.cross_validation is not None
    assert report.cross_validation.folds == 3
    assert (
        result.memory_type
        == classifier.classify(
            MemoryClassificationInput(
                title="Architecture decision",
                content="Decision: keep Python and defer .NET migration.",
            )
        ).memory_type
    )


def test_cross_validation_reports_fold_metrics() -> None:
    report = cross_validate_memory_classifier(seed_training_example_sources(), folds=4, seed=11)

    assert report.folds == 4
    assert 0.0 <= report.average_accuracy <= 1.0
    assert all(fold.total > 0 for fold in report.fold_reports)


def test_runtime_classifier_can_load_trained_artifact(monkeypatch, tmp_path) -> None:
    model_path = tmp_path / "runtime-classifier.json"
    train_validate_memory_classifier(
        seed_training_example_sources(),
        validation_ratio=0.2,
        seed=13,
        folds=2,
        model_out=model_path,
    )

    monkeypatch.setenv(RUNTIME_MODEL_PATH_ENV, str(model_path))
    clear_runtime_classifier_cache()
    try:
        result = classify_memory_type(
            MemoryClassificationInput(
                title="Known pitfall",
                content="Pitfall: avoid changing vector size without recreating pgvector storage.",
            )
        )
    finally:
        clear_runtime_classifier_cache()

    assert result.memory_type == "pitfall"


def test_memory_classifier_cli_trains_from_jsonl(tmp_path, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    model_path = tmp_path / "classifier.json"
    rows = [
        {
            "memory_type": "decision",
            "title": "Runtime choice",
            "content": "Decision: keep Python for OneBrain experiments.",
        },
        {
            "memory_type": "pitfall",
            "title": "Vector size risk",
            "content": "Pitfall: do not change vector size without rebuilding pgvector storage.",
        },
    ]
    dataset_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows),
        encoding="utf-8",
    )

    memory_classifier_main(
        [
            "train",
            "--dataset",
            str(dataset_path),
            "--model-out",
            str(model_path),
            "--folds",
            "2",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert model_path.exists()
    assert output["total_examples"] >= len(rows)
    assert output["cross_validation"]["folds"] == 2
