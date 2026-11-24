"""Keep the page up until the person is done.

Typing off, or asking the window to close, both ask the page to finish and leave.
The process must not be killed mid-step: that is what makes Ubuntu offer to send
a crash report. A phone that still has the page open must not pin it in place.
"""

from types import FrameType

import uvicorn

from printo.console import Console, ignore_stop_signals
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
    ctx: Context | None = None

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        # Do not record the signal. Uvicorn would raise it again on the way out,
        # and the process would die instead of finishing.
        ask(self)


def serve(ctx: Context) -> None:
    server = _Server(_config(ctx))
    server.ctx = ctx
    # The server owns the signals, so a close still runs its own shutdown.
    Console().start(lambda: ask(server), signals=False)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        ignore_stop_signals()
    if server.started:
        print("The shop is closed.", flush=True)


def ask(server: "_Server") -> None:
    if server.ctx is not None:
        server.ctx.events.close()
    server.should_exit = True


def _config(ctx: Context) -> uvicorn.Config:
    return uvicorn.Config(
        create_app(ctx), host=ctx.settings.host, port=ctx.settings.port, access_log=False,
        log_config=_QUIET, timeout_graceful_shutdown=_STOP_SECONDS,
    )
