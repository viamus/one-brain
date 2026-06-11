from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from onebrain.config import Settings, get_settings
from onebrain.db import create_engine
from onebrain.runtime import build_service
from onebrain.service import OneBrainService

_settings_override: Settings | None = None
_service_override: Any | None = None


@dataclass
class RuntimeBundle:
    engine: AsyncEngine
    service: OneBrainService


_bundles: dict[int | None, RuntimeBundle] = {}


def get_runtime_settings() -> Settings:
    return _settings_override or get_settings()


def get_runtime_service() -> Any:
    if _service_override is not None:
        return _service_override
    runtime_key = _current_loop_key()
    bundle = _bundles.get(runtime_key)
    if bundle is None:
        settings = get_runtime_settings()
        engine = create_engine(settings)
        bundle = RuntimeBundle(engine=engine, service=build_service(settings, engine))
        _bundles[runtime_key] = bundle
    return bundle.service


async def close_runtime() -> None:
    for bundle in list(_bundles.values()):
        await bundle.engine.dispose()
    _bundles.clear()


def set_runtime_overrides(
    *,
    settings: Settings | None = None,
    service: Any | None = None,
) -> None:
    global _settings_override, _service_override
    _settings_override = settings
    _service_override = service


def clear_runtime_overrides() -> None:
    set_runtime_overrides(settings=None, service=None)


def _current_loop_key() -> int | None:
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return None
