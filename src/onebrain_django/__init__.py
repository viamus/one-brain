"""Compatibility namespace for the former Django monolith package."""

from __future__ import annotations

import sys
from importlib import import_module

_ALIASES = {
    "onebrain_django.api": "onebrain_api",
    "onebrain_django.api.management": "onebrain_jobs.management",
    "onebrain_django.api.management.commands": "onebrain_jobs.management.commands",
    "onebrain_django.jobs": "onebrain_jobs",
    "onebrain_django.mcp": "onebrain_mcp",
    "onebrain_django.web": "onebrain_web",
}

for _legacy_name, _canonical_name in _ALIASES.items():
    sys.modules.setdefault(_legacy_name, import_module(_canonical_name))
