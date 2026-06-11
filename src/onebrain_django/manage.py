from __future__ import annotations

import os
import sys


def run() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onebrain_django.settings")

    if len(sys.argv) == 1:
        import uvicorn

        host = os.environ.get("ONEBRAIN_DJANGO_HOST", "127.0.0.1")
        port = int(os.environ.get("ONEBRAIN_DJANGO_PORT", "8088"))
        uvicorn.run("onebrain_django.asgi:application", host=host, port=port)
        return

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
