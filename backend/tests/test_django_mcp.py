from __future__ import annotations

from onebrain.platform.asgi import build_application
from starlette.routing import Mount


def test_django_asgi_mounts_mcp_and_django_apps() -> None:
    app = build_application()

    paths = [getattr(route, "path", None) for route in app.routes]

    assert "/mcp" in paths
    assert any(isinstance(route, Mount) for route in app.routes)
