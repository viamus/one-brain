from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from onebrain_core.common.config import get_settings
from onebrain_infra.database import create_engine, create_session_factory
from onebrain_infra.models import Memory
from onebrain_ml.memory_classification_training import (
    TrainingRunReport,
    seed_training_example_sources,
    train_validate_memory_classifier,
    training_examples_from_file_corpus,
    training_examples_from_memories,
)
from sqlalchemy import select

DEFAULT_MODEL_PATH = "/var/lib/onebrain/ml/memory-classifier.json"


@dataclass(frozen=True)
class MemoryClassificationTrainingJobConfig:
    model_out: str
    limit: int
    min_confidence: float
    validation_ratio: float
    folds: int
    seed: int
    include_seed_examples: bool
    include_unreviewed_ml_predictions: bool
    training_docs: tuple[str, ...]
    training_docs_source_ref_prefixes: tuple[str, ...]
    exclude_dirs: tuple[str, ...]
    max_files: int | None
    max_examples_per_type: int | None
    balanced_priors: bool

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> MemoryClassificationTrainingJobConfig:
        return cls(
            model_out=str(options["model_out"]),
            limit=int(options["limit"]),
            min_confidence=float(options["min_confidence"]),
            validation_ratio=float(options["validation_ratio"]),
            folds=int(options["folds"]),
            seed=int(options["seed"]),
            include_seed_examples=bool(options["include_seed_examples"]),
            include_unreviewed_ml_predictions=bool(options["include_unreviewed_ml_predictions"]),
            training_docs=tuple(options.get("training_docs") or ()),
            training_docs_source_ref_prefixes=tuple(
                options.get("training_docs_source_ref_prefix") or ()
            ),
            exclude_dirs=tuple(options.get("exclude_dir") or ()),
            max_files=options.get("max_files"),
            max_examples_per_type=options.get("max_examples_per_type"),
            balanced_priors=bool(options["balanced_priors"]),
        )


class MemoryClassificationTrainingJob:
    async def run_once(
        self,
        config: MemoryClassificationTrainingJobConfig,
    ) -> TrainingRunReport:
        settings = get_settings()
        engine = create_engine(settings)
        try:
            session_factory = create_session_factory(engine)
            async with session_factory() as session:
                result = await session.execute(
                    select(Memory)
                    .where(Memory.status == "active")
                    .order_by(Memory.updated_at.desc())
                    .limit(config.limit)
                )
                memories = result.scalars().all()

            examples = []
            if config.include_seed_examples:
                examples.extend(seed_training_example_sources())
            examples.extend(
                training_examples_from_memories(
                    memories,
                    min_confidence=config.min_confidence,
                    include_unreviewed_ml_predictions=(config.include_unreviewed_ml_predictions),
                )
            )
            for index, docs_path in enumerate(config.training_docs):
                examples.extend(
                    training_examples_from_file_corpus(
                        docs_path,
                        source_ref_prefix=_source_ref_prefix_for_training_docs(
                            config.training_docs_source_ref_prefixes,
                            index,
                        ),
                        exclude_dirs=set(config.exclude_dirs) if config.exclude_dirs else None,
                        max_files=config.max_files,
                    )
                )
            if len(examples) < 2:
                raise ValueError("not enough training examples to train memory classifier")

            Path(config.model_out).parent.mkdir(parents=True, exist_ok=True)
            _, report = train_validate_memory_classifier(
                examples,
                validation_ratio=config.validation_ratio,
                seed=config.seed,
                folds=config.folds,
                model_out=config.model_out,
                max_examples_per_type=config.max_examples_per_type,
                balanced_priors=config.balanced_priors,
            )
            return report
        finally:
            await engine.dispose()


def add_memory_classification_training_arguments(parser) -> None:
    parser.add_argument(
        "--model-out",
        default=DEFAULT_MODEL_PATH,
        help="Path where the trained runtime classifier artifact will be written.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Maximum number of active memories to scan as training signal.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        help="Minimum memory confidence required for implicit training examples.",
    )
    parser.add_argument(
        "--validation-ratio",
        type=float,
        default=0.2,
        help="Holdout validation ratio used before the final runtime model is trained.",
    )
    parser.add_argument(
        "--folds",
        type=int,
        default=5,
        help="Number of cross-validation folds.",
    )
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument(
        "--training-docs",
        action="append",
        default=[],
        help="Repo/folder used only as training corpus. Files are not ingested into OneBrain.",
    )
    parser.add_argument(
        "--training-docs-source-ref-prefix",
        action="append",
        default=[],
        help=(
            "Optional source_ref prefix for examples extracted from --training-docs. "
            "Pass once to reuse it for all corpora, or once per --training-docs."
        ),
    )
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Directory name to exclude from --training-docs. Can be passed more than once.",
    )
    parser.add_argument("--max-examples-per-type", type=int, default=80)
    parser.add_argument(
        "--no-balanced-priors",
        action="store_false",
        dest="balanced_priors",
        default=True,
        help="Use learned class frequency priors instead of balanced class priors.",
    )
    parser.add_argument(
        "--no-seed-examples",
        action="store_false",
        dest="include_seed_examples",
        default=True,
        help="Do not include built-in seed examples in the training run.",
    )
    parser.add_argument(
        "--include-unreviewed-ml-predictions",
        action="store_true",
        default=False,
        help="Allow previous unreviewed ML classifications to become training examples.",
    )


def format_memory_classification_training_result(report: TrainingRunReport) -> list[str]:
    lines = [
        (
            "Memory classifier trained: "
            f"examples={report.total_examples} "
            f"train={report.training_examples} "
            f"validation={report.validation_examples} "
            f"validation_accuracy={report.validation.accuracy:.2%}"
        )
    ]
    if report.cross_validation:
        lines.append(
            "Cross-validation: "
            f"folds={report.cross_validation.folds} "
            f"average_accuracy={report.cross_validation.average_accuracy:.2%}"
        )
    if report.model_path:
        lines.append(f"Runtime artifact: {report.model_path}")
    return lines


def _source_ref_prefix_for_training_docs(prefixes: tuple[str, ...], index: int) -> str | None:
    if not prefixes:
        return None
    if len(prefixes) == 1:
        return prefixes[0]
    if index < len(prefixes):
        return prefixes[index]
    raise ValueError(
        "--training-docs-source-ref-prefix must be passed once or once per --training-docs"
    )
