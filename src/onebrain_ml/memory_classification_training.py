from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from onebrain_ml.memory_classification import (
    MEMORY_TYPES,
    MemoryClassificationInput,
    MemoryClassificationResult,
    NaiveBayesMemoryClassifier,
    TrainingExample,
    default_training_examples,
    save_memory_classifier,
)

TRAINING_TEXT_EXTENSIONS = {
    "",
    ".md",
    ".mdx",
    ".txt",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
}
TRAINING_EXCLUDE_DIRS = {
    ".git",
    ".github",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "bin",
    "dist",
    "node_modules",
    "obj",
}


@dataclass(frozen=True)
class TrainingExampleSource:
    example: TrainingExample
    source_ref: str | None = None
    source_kind: str = "dataset"
    reason: str = "labeled_example"


@dataclass(frozen=True)
class EvaluationPrediction:
    expected: str
    predicted: str
    confidence: float
    source_ref: str | None = None
    title: str | None = None
    runner_up: str | None = None
    runner_up_confidence: float | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def correct(self) -> bool:
        return self.expected == self.predicted

    def as_dict(self) -> dict[str, object]:
        return {
            "expected": self.expected,
            "predicted": self.predicted,
            "correct": self.correct,
            "confidence": round(self.confidence, 4),
            "source_ref": self.source_ref,
            "title": self.title,
            "runner_up": self.runner_up,
            "runner_up_confidence": (
                round(self.runner_up_confidence, 4)
                if self.runner_up_confidence is not None
                else None
            ),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class EvaluationReport:
    total: int
    correct: int
    accuracy: float
    by_type: dict[str, dict[str, float]]
    confusion_matrix: dict[str, dict[str, int]]
    predictions: list[EvaluationPrediction] = field(default_factory=list)

    def as_dict(self, *, include_predictions: bool = False) -> dict[str, object]:
        output: dict[str, object] = {
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
            "by_type": self.by_type,
            "confusion_matrix": self.confusion_matrix,
        }
        if include_predictions:
            output["predictions"] = [prediction.as_dict() for prediction in self.predictions]
        return output


@dataclass(frozen=True)
class SplitDataset:
    training: list[TrainingExampleSource]
    validation: list[TrainingExampleSource]


@dataclass(frozen=True)
class CrossValidationReport:
    folds: int
    average_accuracy: float
    fold_reports: list[EvaluationReport]

    def as_dict(self, *, include_predictions: bool = False) -> dict[str, object]:
        return {
            "folds": self.folds,
            "average_accuracy": round(self.average_accuracy, 4),
            "fold_reports": [
                report.as_dict(include_predictions=include_predictions)
                for report in self.fold_reports
            ],
        }


@dataclass(frozen=True)
class TrainingRunReport:
    total_examples: int
    training_examples: int
    validation_examples: int
    model_path: str | None
    validation: EvaluationReport
    cross_validation: CrossValidationReport | None = None

    def as_dict(self, *, include_predictions: bool = False) -> dict[str, object]:
        return {
            "total_examples": self.total_examples,
            "training_examples": self.training_examples,
            "validation_examples": self.validation_examples,
            "model_path": self.model_path,
            "validation": self.validation.as_dict(include_predictions=include_predictions),
            "cross_validation": (
                self.cross_validation.as_dict(include_predictions=include_predictions)
                if self.cross_validation
                else None
            ),
        }


@dataclass(frozen=True)
class ParsedTrainingFile:
    metadata: dict[str, str]
    body: str
    has_frontmatter: bool


def load_labeled_examples(path: str | Path) -> list[TrainingExampleSource]:
    dataset_path = Path(path)
    if dataset_path.is_dir():
        examples: list[TrainingExampleSource] = []
        for child in sorted(dataset_path.iterdir()):
            if child.suffix.lower() in {".json", ".jsonl"}:
                examples.extend(load_labeled_examples(child))
        return examples
    if dataset_path.suffix.lower() == ".jsonl":
        return _load_jsonl_examples(dataset_path)
    if dataset_path.suffix.lower() == ".json":
        return _load_json_examples(dataset_path)
    raise ValueError(f"unsupported training dataset format: {dataset_path}")


def training_examples_from_file_corpus(
    path: str | Path,
    *,
    source_ref_prefix: str | None = None,
    include_extensions: set[str] | None = None,
    exclude_dirs: set[str] | None = None,
    max_files: int | None = None,
    max_chars: int = 24_000,
) -> list[TrainingExampleSource]:
    """Build labeled training examples from a repo/folder without ingesting memories."""

    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"training corpus path does not exist: {root}")

    files = (
        [root] if root.is_file() else _iter_training_files(root, include_extensions, exclude_dirs)
    )
    examples: list[TrainingExampleSource] = []
    for file_path in files:
        if max_files is not None and len(examples) >= max_files:
            break
        try:
            text = file_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            continue

        relative_path = _relative_path(file_path, root)
        parsed = _parse_frontmatter(text)
        label, reason = _strong_label_for_training_file(
            relative_path,
            parsed.metadata,
            file_path.suffix.lower(),
            parsed.body,
        )
        if label is None:
            continue

        title = _title_for_training_file(relative_path, parsed.metadata, parsed.body)
        examples.append(
            TrainingExampleSource(
                example=TrainingExample(
                    memory_type=label,
                    text=_training_file_text(parsed.body, max_chars),
                    relative_path=relative_path,
                    extension=file_path.suffix.lower(),
                    title=title,
                    metadata={
                        key: value
                        for key, value in parsed.metadata.items()
                        if isinstance(value, str)
                    },
                ),
                source_ref=_source_ref_for_training_file(relative_path, source_ref_prefix),
                source_kind="file-corpus",
                reason=reason,
            )
        )
    return examples


def training_examples_from_memories(
    memories: Iterable[Mapping[str, Any] | object],
    *,
    min_confidence: float = 0.7,
    include_unreviewed_ml_predictions: bool = False,
) -> list[TrainingExampleSource]:
    examples: list[TrainingExampleSource] = []
    for memory in memories:
        payload = _memory_mapping(memory)
        if payload.get("status", "active") != "active":
            continue
        content = str(payload.get("content") or "").strip()
        if not content:
            continue

        metadata = dict(payload.get("metadata_") or payload.get("metadata") or {})
        label, reason = _training_label_from_memory(
            payload,
            metadata,
            min_confidence=min_confidence,
            include_unreviewed_ml_predictions=include_unreviewed_ml_predictions,
        )
        if label is None:
            continue

        source_ref = _string_or_none(payload.get("source_ref"))
        relative_path = _relative_path_from_memory(payload, metadata)
        examples.append(
            TrainingExampleSource(
                example=TrainingExample(
                    memory_type=label,
                    text=content,
                    relative_path=relative_path,
                    extension=_extension_from_path(relative_path),
                    title=_string_or_none(payload.get("title")),
                    metadata={
                        key: str(value)
                        for key, value in metadata.items()
                        if isinstance(value, str | int | float | bool)
                    },
                ),
                source_ref=source_ref,
                source_kind="onebrain-memory",
                reason=reason,
            )
        )
    return examples


def split_training_validation(
    examples: Sequence[TrainingExampleSource],
    *,
    validation_ratio: float = 0.2,
    seed: int = 13,
) -> SplitDataset:
    if not 0.0 < validation_ratio < 1.0:
        raise ValueError("validation_ratio must be between 0 and 1")
    if not examples:
        return SplitDataset(training=[], validation=[])

    rng = random.Random(seed)  # noqa: S311 - deterministic dataset split, not security.
    buckets: dict[str, list[TrainingExampleSource]] = defaultdict(list)
    for item in examples:
        buckets[item.example.memory_type].append(item)

    training: list[TrainingExampleSource] = []
    validation: list[TrainingExampleSource] = []
    for bucket in buckets.values():
        shuffled = list(bucket)
        rng.shuffle(shuffled)
        validation_count = (
            0 if len(shuffled) == 1 else max(1, round(len(shuffled) * validation_ratio))
        )
        validation.extend(shuffled[:validation_count])
        training.extend(shuffled[validation_count:])

    if not validation and len(training) > 1:
        validation.append(training.pop())
    return SplitDataset(training=training, validation=validation)


def balance_training_examples(
    examples: Sequence[TrainingExampleSource],
    *,
    max_examples_per_type: int | None,
    seed: int = 13,
) -> list[TrainingExampleSource]:
    if max_examples_per_type is None:
        return list(examples)
    if max_examples_per_type < 1:
        raise ValueError("max_examples_per_type must be greater than or equal to 1")

    rng = random.Random(seed)  # noqa: S311 - deterministic balancing, not security.
    buckets: dict[str, list[TrainingExampleSource]] = defaultdict(list)
    for item in examples:
        buckets[item.example.memory_type].append(item)

    balanced: list[TrainingExampleSource] = []
    for bucket in buckets.values():
        ordered = list(bucket)
        seed_examples = [item for item in ordered if item.source_kind == "seed"]
        other_examples = [item for item in ordered if item.source_kind != "seed"]
        rng.shuffle(other_examples)
        selected = [*seed_examples, *other_examples]
        balanced.extend(selected[:max_examples_per_type])
    return sorted(
        balanced,
        key=lambda item: (
            item.example.memory_type,
            item.source_kind,
            item.source_ref or "",
            item.example.title or "",
        ),
    )


def train_memory_classifier(
    examples: Sequence[TrainingExampleSource | TrainingExample],
    *,
    balanced_priors: bool = False,
) -> NaiveBayesMemoryClassifier:
    return NaiveBayesMemoryClassifier(
        [_training_example(item) for item in examples],
        balanced_priors=balanced_priors,
    )


def train_validate_memory_classifier(
    examples: Sequence[TrainingExampleSource],
    *,
    validation_ratio: float = 0.2,
    seed: int = 13,
    folds: int = 5,
    model_out: str | Path | None = None,
    max_examples_per_type: int | None = None,
    balanced_priors: bool = True,
) -> tuple[NaiveBayesMemoryClassifier, TrainingRunReport]:
    examples = balance_training_examples(
        examples,
        max_examples_per_type=max_examples_per_type,
        seed=seed,
    )
    split = split_training_validation(examples, validation_ratio=validation_ratio, seed=seed)
    classifier = train_memory_classifier(split.training, balanced_priors=balanced_priors)
    validation_report = evaluate_memory_classifier(classifier, split.validation)
    cross_validation = (
        cross_validate_memory_classifier(
            examples,
            folds=folds,
            seed=seed,
            balanced_priors=balanced_priors,
        )
        if folds >= 2 and len(examples) >= 2
        else None
    )

    runtime_classifier = train_memory_classifier(examples, balanced_priors=balanced_priors)
    model_path = str(model_out) if model_out else None
    if model_out:
        save_memory_classifier(runtime_classifier, model_out)
    return runtime_classifier, TrainingRunReport(
        total_examples=len(examples),
        training_examples=len(split.training),
        validation_examples=len(split.validation),
        model_path=model_path,
        validation=validation_report,
        cross_validation=cross_validation,
    )


def evaluate_memory_classifier(
    classifier: NaiveBayesMemoryClassifier,
    examples: Sequence[TrainingExampleSource | TrainingExample],
) -> EvaluationReport:
    predictions: list[EvaluationPrediction] = []
    by_type_counts: dict[str, Counter[str]] = defaultdict(Counter)
    confusion: dict[str, Counter[str]] = defaultdict(Counter)

    for item in examples:
        example = _training_example(item)
        result = classifier.classify(_input_for_example(example))
        predictions.append(_prediction_for(item, result))
        by_type_counts[example.memory_type]["total"] += 1
        confusion[example.memory_type][result.memory_type] += 1
        if result.memory_type == example.memory_type:
            by_type_counts[example.memory_type]["correct"] += 1

    total = len(predictions)
    correct = sum(1 for prediction in predictions if prediction.correct)
    by_type = {
        memory_type: {
            "total": float(counts["total"]),
            "correct": float(counts["correct"]),
            "accuracy": round(
                counts["correct"] / counts["total"] if counts["total"] else 0.0,
                4,
            ),
        }
        for memory_type, counts in sorted(by_type_counts.items())
    }
    return EvaluationReport(
        total=total,
        correct=correct,
        accuracy=correct / total if total else 0.0,
        by_type=by_type,
        confusion_matrix={
            expected: dict(sorted(predicted.items()))
            for expected, predicted in sorted(confusion.items())
        },
        predictions=predictions,
    )


def cross_validate_memory_classifier(
    examples: Sequence[TrainingExampleSource],
    *,
    folds: int = 5,
    seed: int = 13,
    balanced_priors: bool = True,
) -> CrossValidationReport:
    if folds < 2:
        raise ValueError("folds must be greater than or equal to 2")
    if len(examples) < 2:
        raise ValueError("at least two examples are required for cross-validation")

    fold_count = min(folds, len(examples))
    buckets: dict[str, list[TrainingExampleSource]] = defaultdict(list)
    rng = random.Random(seed)  # noqa: S311 - deterministic cross-validation, not security.
    for item in examples:
        buckets[item.example.memory_type].append(item)

    split_folds: list[list[TrainingExampleSource]] = [[] for _ in range(fold_count)]
    for bucket in buckets.values():
        shuffled = list(bucket)
        rng.shuffle(shuffled)
        for index, item in enumerate(shuffled):
            split_folds[index % fold_count].append(item)

    reports: list[EvaluationReport] = []
    for index, validation in enumerate(split_folds):
        if not validation:
            continue
        training = [
            item
            for fold_index, fold in enumerate(split_folds)
            if fold_index != index
            for item in fold
        ]
        if not training:
            continue
        reports.append(
            evaluate_memory_classifier(
                train_memory_classifier(training, balanced_priors=balanced_priors),
                validation,
            )
        )

    average_accuracy = sum(report.accuracy for report in reports) / len(reports) if reports else 0.0
    return CrossValidationReport(
        folds=len(reports),
        average_accuracy=average_accuracy,
        fold_reports=reports,
    )


def seed_training_example_sources() -> list[TrainingExampleSource]:
    return [
        TrainingExampleSource(
            example=example,
            source_kind="seed",
            reason="seed_example",
        )
        for example in default_training_examples()
    ]


def report_to_json(report: TrainingRunReport, *, include_predictions: bool = False) -> str:
    return json.dumps(
        report.as_dict(include_predictions=include_predictions),
        indent=2,
        sort_keys=True,
    )


def _load_jsonl_examples(path: Path) -> list[TrainingExampleSource]:
    examples: list[TrainingExampleSource] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        examples.append(_example_from_payload(payload, source_ref=f"{path}:{line_number}"))
    return examples


def _load_json_examples(path: Path) -> list[TrainingExampleSource]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("examples") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("JSON training dataset must be a list or an object with examples")
    return [
        _example_from_payload(row, source_ref=f"{path}:{index}")
        for index, row in enumerate(rows, start=1)
    ]


def _example_from_payload(payload: Mapping[str, Any], *, source_ref: str) -> TrainingExampleSource:
    memory_type = str(payload.get("memory_type") or "").strip()
    if memory_type not in MEMORY_TYPES:
        raise ValueError(f"unsupported memory_type in training dataset: {memory_type}")
    content = str(payload.get("content") or payload.get("text") or "").strip()
    if not content:
        raise ValueError("training example content is required")
    relative_path = str(payload.get("relative_path") or "").strip()
    return TrainingExampleSource(
        example=TrainingExample(
            memory_type=memory_type,
            text=content,
            relative_path=relative_path,
            extension=str(payload.get("extension") or _extension_from_path(relative_path)),
            title=_string_or_none(payload.get("title")),
            metadata=dict(payload.get("metadata") or {}),
        ),
        source_ref=_string_or_none(payload.get("source_ref")) or source_ref,
        source_kind="dataset",
        reason="labeled_dataset",
    )


def _iter_training_files(
    root: Path,
    include_extensions: set[str] | None,
    exclude_dirs: set[str] | None,
) -> list[Path]:
    extensions = {item.lower() for item in (include_extensions or TRAINING_TEXT_EXTENSIONS)}
    excluded = {item.lower() for item in (exclude_dirs or TRAINING_EXCLUDE_DIRS)}
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


def _parse_frontmatter(text: str) -> ParsedTrainingFile:
    match = re.match(r"(?s)^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$", text)
    if not match:
        return ParsedTrainingFile(metadata={}, body=text, has_frontmatter=False)

    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        item = re.match(r"\s*([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$", line)
        if item:
            metadata[item.group(1).lower()] = item.group(2).strip().strip("\"'")
    return ParsedTrainingFile(metadata=metadata, body=match.group(2), has_frontmatter=True)


def _strong_label_for_training_file(
    relative_path: str,
    metadata: Mapping[str, str],
    extension: str,
    content: str,
) -> tuple[str | None, str]:
    declared = _declared_training_type(metadata)
    if declared:
        return declared, "frontmatter_training_type"

    path = relative_path.lower().replace("\\", "/")
    content_head = content[:1600].lower()
    if (
        path == "changelog.md"
        or path.startswith("docs/compatibility/")
        or path
        in {
            "docs/adding_the_book.md",
            "docs/compatibility.md",
            "docs/criticism.md",
            "docs/usage.md",
        }
    ):
        return None, "auxiliary_training_doc"
    if path.endswith("/skill.md") or path == "skill.md" or "/skills/" in path:
        return "skill", "skill_path"
    if re.search(r"(^|/)(adr|adrs|decisions?|architecture-decisions?)(/|[-_.])", path):
        return "decision", "decision_path"
    if re.search(r"(^|/)(pitfalls?|anti-patterns?|antipatterns?|gotchas?|risks?)(/|[-_.])", path):
        return "pitfall", "pitfall_path"
    if re.search(r"(^|/)(runbooks?|troubleshooting|incident|recovery)(/|[-_.])", path):
        return "runbook", "runbook_path"
    if re.search(r"(^|/)(workflows?|playbooks?|checklists?|procedures?)(/|[-_.])", path):
        return "workflow", "workflow_path"
    if re.search(r"(^|/)(preferences?|user-preferences?)(/|[-_.])", path):
        return "preference", "preference_path"
    if re.search(r"(^|/)(rules?|policies|standards?|conventions?|guardrails?)(/|[-_.])", path):
        return "rule", "rule_path"
    if re.search(r"(^|/)(facts?|references?|schemas?|configs?|api)(/|[-_.])", path):
        return "fact", "fact_path"

    if path.endswith("readme.md") or re.search(r"(^|/)(overview|context|snapshot)(/|[-_.])", path):
        return "context", "context_path"
    if path.endswith(".agents.md") or path.endswith("agents.md"):
        return "skill", "agent_rules_file"
    if _looks_like_book_rule_file(path):
        return "rule", "book_rule_file"
    if "rules / skills" in content_head or (
        "rule set" in content_head and not path.startswith("docs/")
    ):
        return "rule", "rule_set_content"
    if extension in {".json", ".yaml", ".yml"}:
        return "fact", "structured_reference_extension"
    return None, "ambiguous_training_file"


def _looks_like_book_rule_file(path: str) -> bool:
    parts = path.split("/")
    if len(parts) != 2 or not path.endswith(".md"):
        return False
    folder, file_name = parts
    if folder.startswith("_") or folder in {"docs", "examples"}:
        return False
    base_name = file_name.removesuffix(".md")
    for suffix in (".mini", ".nano", ".full"):
        base_name = base_name.removesuffix(suffix)
    return base_name == folder


def _declared_training_type(metadata: Mapping[str, str]) -> str | None:
    value = (
        metadata.get("memory_type")
        or metadata.get("type")
        or metadata.get("category")
        or metadata.get("classification")
    )
    if not value:
        return None
    normalized = value.lower().strip().replace(" ", "-").replace("_", "-")
    mapping = {
        "adr": "decision",
        "anti-pattern": "pitfall",
        "antipattern": "pitfall",
        "checklist": "workflow",
        "decision": "decision",
        "fact": "fact",
        "feedback": "rule",
        "gotcha": "pitfall",
        "note": "note",
        "pitfall": "pitfall",
        "playbook": "workflow",
        "policy": "rule",
        "preference": "preference",
        "procedure": "workflow",
        "reference": "fact",
        "rule": "rule",
        "runbook": "runbook",
        "skill": "skill",
        "skill.spec": "skill",
        "standard": "rule",
        "workflow": "workflow",
    }
    return mapping.get(normalized)


def _title_for_training_file(
    relative_path: str,
    metadata: Mapping[str, str],
    content: str,
) -> str | None:
    if title := metadata.get("title") or metadata.get("name"):
        return title[:240]
    heading = re.search(r"(?m)^#\s+(.+?)\s*$", content)
    if heading:
        return heading.group(1).strip()[:240]
    return Path(relative_path).stem.replace("-", " ").replace("_", " ").strip().title()[:240]


def _training_file_text(content: str, max_chars: int) -> str:
    text = content.strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip()


def _relative_path(file_path: Path, root: Path) -> str:
    base = root.parent if root.is_file() else root
    return file_path.relative_to(base).as_posix()


def _source_ref_for_training_file(relative_path: str, source_ref_prefix: str | None) -> str:
    normalized = relative_path.replace("\\", "/")
    if source_ref_prefix:
        return f"{source_ref_prefix.rstrip('/')}/{normalized}"
    return f"file-corpus://{normalized}"


def _training_label_from_memory(
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    min_confidence: float,
    include_unreviewed_ml_predictions: bool,
) -> tuple[str | None, str]:
    training = metadata.get("classification_training")
    if isinstance(training, Mapping):
        if training.get("use") is False:
            return None, "classification_training_disabled"
        if label := _valid_memory_type(training.get("memory_type") or training.get("label")):
            return label, "explicit_training_label"

    correction = metadata.get("memory_type_correction")
    if isinstance(correction, Mapping):
        if label := _valid_memory_type(
            correction.get("corrected_type") or correction.get("memory_type")
        ):
            return label, "corrected_memory_type"

    memory_type = _valid_memory_type(payload.get("memory_type"))
    if memory_type is None:
        return None, "unsupported_memory_type"
    confidence = float(payload.get("confidence") or 0.0)
    if confidence < min_confidence:
        return None, "low_confidence_memory"

    classification = metadata.get("memory_classification")
    if isinstance(classification, Mapping) and classification.get("method") == "ml":
        if classification.get("accepted") is True:
            return memory_type, "accepted_ml_classification"
        if include_unreviewed_ml_predictions:
            return memory_type, "unreviewed_ml_classification"
        return None, "skip_unreviewed_ml_classification"

    return memory_type, "manual_or_heuristic_memory_type"


def _memory_mapping(memory: Mapping[str, Any] | object) -> Mapping[str, Any]:
    if isinstance(memory, Mapping):
        return memory
    if hasattr(memory, "model_dump"):
        return memory.model_dump(mode="json")
    return {
        key: getattr(memory, key)
        for key in (
            "memory_type",
            "status",
            "title",
            "content",
            "confidence",
            "source_ref",
            "metadata_",
        )
        if hasattr(memory, key)
    }


def _training_example(item: TrainingExampleSource | TrainingExample) -> TrainingExample:
    return item.example if isinstance(item, TrainingExampleSource) else item


def _input_for_example(example: TrainingExample) -> MemoryClassificationInput:
    return MemoryClassificationInput(
        relative_path=example.relative_path,
        metadata=example.metadata,
        extension=example.extension,
        title=example.title,
        content=example.text,
    )


def _prediction_for(
    item: TrainingExampleSource | TrainingExample,
    result: MemoryClassificationResult,
) -> EvaluationPrediction:
    example = _training_example(item)
    return EvaluationPrediction(
        expected=example.memory_type,
        predicted=result.memory_type,
        confidence=result.confidence,
        source_ref=item.source_ref if isinstance(item, TrainingExampleSource) else None,
        title=example.title,
        runner_up=result.runner_up,
        runner_up_confidence=result.runner_up_confidence,
        reasons=result.reasons,
    )


def _relative_path_from_memory(
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    if relative_path := _string_or_none(metadata.get("relative_path")):
        return relative_path
    if source_ref := _string_or_none(payload.get("source_ref")):
        return source_ref.split("#", 1)[0]
    return ""


def _extension_from_path(path: str) -> str:
    return Path(path).suffix.lower()


def _valid_memory_type(value: Any) -> str | None:
    memory_type = str(value or "").strip()
    return memory_type if memory_type in MEMORY_TYPES else None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
