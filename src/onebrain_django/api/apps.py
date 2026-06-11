from __future__ import annotations

from django.apps import AppConfig


class OneBrainApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "onebrain_django.api"
    verbose_name = "OneBrain API"
