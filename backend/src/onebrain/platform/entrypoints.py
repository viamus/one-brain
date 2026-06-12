from __future__ import annotations

import os
import sys


def run_api() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onebrain.platform.settings")
    os.environ.setdefault("ONEBRAIN_DJANGO_URLCONF", "onebrain.interfaces.api.service_urls")
    _run_uvicorn("onebrain.platform.django_asgi:application", default_port=8088)


def run_web() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onebrain.platform.settings")
    os.environ.setdefault("ONEBRAIN_DJANGO_URLCONF", "onebrain.interfaces.web.service_urls")
    _run_uvicorn("onebrain.platform.django_asgi:application", default_port=8089)


def run_mcp_http() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onebrain.platform.settings")
    _run_uvicorn("onebrain.interfaces.mcp.asgi:application", default_port=8090)


def run_jobs() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onebrain.platform.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


def _run_uvicorn(app: str, *, default_port: int) -> None:
    import uvicorn

    host = os.environ.get("ONEBRAIN_DJANGO_HOST", "127.0.0.1")
    port = int(os.environ.get("ONEBRAIN_DJANGO_PORT", str(default_port)))
    uvicorn.run(app, host=host, port=port)
