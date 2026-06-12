from __future__ import annotations

from django.apps import AppConfig


class OneBrainWorkersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    label = "onebrain_workers"
    name = "onebrain.workers"
    verbose_name = "OneBrain Workers"
