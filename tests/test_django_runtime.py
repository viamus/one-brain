from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from onebrain.config import Settings
from onebrain_django import runtime


@dataclass
class FakeEngine:
    disposed: bool = False

    async def dispose(self) -> None:
        self.disposed = True


def test_runtime_service_is_scoped_to_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    created_engines: list[FakeEngine] = []

    def fake_create_engine(_settings: Settings) -> FakeEngine:
        engine = FakeEngine()
        created_engines.append(engine)
        return engine

    def fake_build_service(_settings: Settings, engine: FakeEngine) -> dict[str, Any]:
        return {"engine": engine}

    monkeypatch.setattr(runtime, "create_engine", fake_create_engine)
    monkeypatch.setattr(runtime, "build_service", fake_build_service)
    runtime.set_runtime_overrides(settings=Settings(api_keys=""))

    async def service_for_current_loop() -> Any:
        return runtime.get_runtime_service()

    first = asyncio.run(service_for_current_loop())
    second = asyncio.run(service_for_current_loop())

    assert first is not second
    assert len(created_engines) == 2
    asyncio.run(runtime.close_runtime())
    assert all(engine.disposed for engine in created_engines)
    runtime.clear_runtime_overrides()
