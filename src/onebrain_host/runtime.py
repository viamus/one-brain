from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from onebrain_core.application.runtime import build_service
from onebrain_core.application.service import OneBrainService
from onebrain_core.common.config import Settings, get_settings
from onebrain_infra.database import create_engine

_settings_override: Settings | None = None
_service_override: Any | None = None


@dataclass
class RuntimeBundle:
    engine: AsyncEngine
    service: OneBrainService


_loop_bundles: dict[asyncio.AbstractEventLoop, RuntimeBundle] = {}
_sync_bundle: RuntimeBundle | None = None


def get_runtime_settings() -> Settings:
    return _settings_override or get_settings()


def get_runtime_service() -> Any:
    global _sync_bundle
    if _service_override is not None:
        return _service_override
    loop = _current_loop()
    if loop is None:
        bundle = _sync_bundle
    else:
        bundle = _loop_bundles.get(loop)
    if bundle is None:
        settings = get_runtime_settings()
        engine = create_engine(settings)
        bundle = RuntimeBundle(engine=engine, service=build_service(settings, engine))
        if loop is None:
            _sync_bundle = bundle
        else:
            _loop_bundles[loop] = bundle
    return bundle.service


async def close_runtime() -> None:
    global _sync_bundle
    bundles = list(_loop_bundles.values())
    if _sync_bundle is not None:
        bundles.append(_sync_bundle)
    for bundle in bundles:
        await bundle.engine.dispose()
    _loop_bundles.clear()
    _sync_bundle = None


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


def _current_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
