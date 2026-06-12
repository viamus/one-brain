from __future__ import annotations

from django.apps import AppConfig


class OneBrainApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    label = "onebrain_api"
    name = "onebrain.interfaces.api"
    verbose_name = "OneBrain API"
