from __future__ import annotations

from django.apps import AppConfig


class OneBrainMcpConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    label = "onebrain_mcp"
    name = "onebrain.interfaces.mcp"
    verbose_name = "OneBrain MCP"
