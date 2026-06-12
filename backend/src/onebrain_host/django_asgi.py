from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

from onebrain_host.disconnects import DisconnectTolerantAsgiApp

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "onebrain_host.settings")

application = DisconnectTolerantAsgiApp(get_asgi_application())
