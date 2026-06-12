from __future__ import annotations

from django.apps import AppConfig


class OneBrainWebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    label = "onebrain_web"
    name = "onebrain.interfaces.web"
    verbose_name = "OneBrain Web"
