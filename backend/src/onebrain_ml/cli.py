from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from onebrain_ml.memory_classification import (
    MemoryClassificationInput,
    classify_memory_type,
    clear_runtime_classifier_cache,
    load_memory_classifier,
)
from onebrain_ml.memory_classification_training import (
    load_labeled_examples,
    report_to_json,
    seed_training_example_sources,
    train_validate_memory_classifier,
    training_examples_from_file_corpus,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="onebrain-memory-classifier")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train = subparsers.add_parser("train", help="Train and validate a memory classifier.")
    train.add_argument(
        "--dataset",
        action="append",
        default=[],
        help="JSON or JSONL labeled dataset. Can be passed more than once.",
    )
    train.add_argument(
        "--training-docs",
        action="append",
        default=[],
        help="Repo/folder used only as training corpus. Files are not ingested into OneBrain.",
    )
    train.add_argument(
        "--training-docs-source-ref-prefix",
        action="append",
        default=[],
        help=(
            "Optional source_ref prefix for examples extracted from --training-docs. "
            "Pass once to reuse it for all corpora, or once per --training-docs."
        ),
    )
    train.add_argument("--model-out", required=True)
    train.add_argument("--validation-ratio", type=float, default=0.2)
    train.add_argument("--folds", type=int, default=5)
    train.add_argument("--seed", type=int, default=13)
    train.add_argument("--max-files", type=int, default=None)
    train.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Directory name to exclude from --training-docs. Can be passed more than once.",
    )
    train.add_argument("--max-examples-per-type", type=int, default=80)
    train.add_argument(
        "--no-balanced-priors",
        action="store_false",
        dest="balanced_priors",
        default=True,
    )
    train.add_argument("--no-seed-examples", action="store_true")
    train.add_argument("--include-predictions", action="store_true")
    train.set_defaults(func=_train)

    classify = subparsers.add_parser("classify", help="Classify one memory-like text.")
    classify.add_argument("--model")
    classify.add_argument("--content", required=True)
    classify.add_argument("--title")
    classify.add_argument("--relative-path", default="")
    classify.add_argument("--extension", default="")
    classify.set_defaults(func=_classify)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    args.func(args)


def _train(args: argparse.Namespace) -> None:
    examples = []
    if not args.no_seed_examples:
        examples.extend(seed_training_example_sources())
    for dataset in args.dataset:
        examples.extend(load_labeled_examples(dataset))
    for index, docs_path in enumerate(args.training_docs):
        examples.extend(
            training_examples_from_file_corpus(
                docs_path,
                source_ref_prefix=_source_ref_prefix_for_training_docs(
                    tuple(args.training_docs_source_ref_prefix),
                    index,
                ),
                exclude_dirs=set(args.exclude_dir) if args.exclude_dir else None,
                max_files=args.max_files,
            )
        )
    if len(examples) < 2:
        raise SystemExit("at least two training examples are required")

    _, report = train_validate_memory_classifier(
        examples,
        validation_ratio=args.validation_ratio,
        seed=args.seed,
        folds=args.folds,
        model_out=args.model_out,
        max_examples_per_type=args.max_examples_per_type,
        balanced_priors=args.balanced_priors,
    )
    print(report_to_json(report, include_predictions=args.include_predictions))


def _classify(args: argparse.Namespace) -> None:
    classifier = load_memory_classifier(args.model) if args.model else None
    item = MemoryClassificationInput(
        relative_path=args.relative_path,
        extension=args.extension,
        title=args.title,
        content=args.content,
    )
    if classifier:
        result = classifier.classify(item)
    else:
        clear_runtime_classifier_cache()
        result = classify_memory_type(item)
    print(json.dumps(result.as_metadata(), indent=2, sort_keys=True))


def _source_ref_prefix_for_training_docs(prefixes: tuple[str, ...], index: int) -> str | None:
    if not prefixes:
        return None
    if len(prefixes) == 1:
        return prefixes[0]
    if index < len(prefixes):
        return prefixes[index]
    raise SystemExit(
        "--training-docs-source-ref-prefix must be passed once or once per --training-docs"
    )
