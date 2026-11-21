"""Keep the page up, and always let Ctrl+C close it.

A phone that still has the page open must not pin this process in place.
The first Ctrl+C closes those connections and stops. A second one stops immediately.
"""

import os
from types import FrameType

import uvicorn

from printo.http.app import create_app
from printo.wiring import Context

_STOP_SECONDS = 2
_QUIET = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(message)s"}},
    "handlers": {"stderr": {"class": "logging.StreamHandler", "formatter": "plain", "stream": "ext://sys.stderr"}},
    "loggers": {
        "uvicorn": {"handlers": ["stderr"], "level": "WARNING"},
        "uvicorn.error": {"handlers": ["stderr"], "level": "WARNING"},
        "uvicorn.access": {"handlers": ["stderr"], "level": "WARNING"},
    },
}


class _Server(uvicorn.Server):
    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        if self.should_exit:
            os._exit(128 + sig)
        super().handle_exit(sig, frame)


def serve(ctx: Context) -> None:
    try:
        _Server(_config(ctx)).run()
    except KeyboardInterrupt:
        return


def _config(ctx: Context) -> uvicorn.Config:
    return uvicorn.Config(
        create_app(ctx), host=ctx.settings.host, port=ctx.settings.port, access_log=False,
        log_config=_QUIET, timeout_graceful_shutdown=_STOP_SECONDS,
    )
