from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from django.core.exceptions import RequestAborted

logger = logging.getLogger(__name__)

AsgiReceive = Callable[[], Awaitable[dict[str, Any]]]
AsgiSend = Callable[[dict[str, Any]], Awaitable[None]]
AsgiApp = Callable[[dict[str, Any], AsgiReceive, AsgiSend], Awaitable[None]]


class DisconnectTolerantAsgiApp:
    def __init__(self, app: AsgiApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: AsgiReceive,
        send: AsgiSend,
    ) -> None:
        try:
            await self._app(scope, receive, send)
        except RequestAborted:
            logger.debug(
                "request aborted by client",
                extra={"path": scope.get("path"), "type": scope.get("type")},
            )
