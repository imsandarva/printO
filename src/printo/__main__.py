"""Start printO. This only wires the pieces and runs them."""

import uvicorn

from printo.config import load_settings
from printo.http.app import create_app
from printo.runtime import boot, report
from printo.wiring import Context

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


def main(argv: list[str] | None = None) -> None:
    settings = load_settings(argv)
    ctx = boot(settings)
    if settings.check_only:
        try:
            report(ctx)
        finally:
            ctx.db.close()
        return
    serve(ctx)


def serve(ctx: Context) -> None:
    uvicorn.run(create_app(ctx), host=ctx.settings.host, port=ctx.settings.port, access_log=False, log_config=_QUIET)


if __name__ == "__main__":
    main()
