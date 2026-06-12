from __future__ import annotations

import asyncio

from django.core.management.base import BaseCommand, CommandError

from onebrain.ml.memory_classification_training import report_to_json
from onebrain.workers.memory_classification import (
    MemoryClassificationTrainingJob,
    MemoryClassificationTrainingJobConfig,
    add_memory_classification_training_arguments,
    format_memory_classification_training_result,
)


class Command(BaseCommand):
    help = "Train the OneBrain memory type classifier from accepted OneBrain memories."

    def add_arguments(self, parser) -> None:
        add_memory_classification_training_arguments(parser)
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the full training report as JSON.",
        )
        parser.add_argument(
            "--include-predictions",
            action="store_true",
            help="Include validation predictions in the JSON report.",
        )

    def handle(self, *args, **options) -> None:
        try:
            config = MemoryClassificationTrainingJobConfig.from_options(options)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        try:
            report = asyncio.run(MemoryClassificationTrainingJob().run_once(config))
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        if options["json"]:
            self.stdout.write(
                report_to_json(report, include_predictions=options["include_predictions"])
            )
            return

        for line in format_memory_classification_training_result(report):
            self.stdout.write(line)
