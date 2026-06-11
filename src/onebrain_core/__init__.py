"""OneBrain memory service."""

from __future__ import annotations

import sys
from importlib import import_module

sys.modules.setdefault("onebrain_core.infrastructure", import_module("onebrain_infra"))

__all__ = ["__version__"]

__version__ = "0.1.0"
