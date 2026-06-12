from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

from onebrain.platform.disconnects import DisconnectTolerantAsgiApp

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onebrain.platform.settings")

application = DisconnectTolerantAsgiApp(get_asgi_application())
