"""Start and stop the shop service. The process comes up at boot; the screen does not."""

import asyncio
import logging

from printo.config import Settings
from printo.logging_setup import setup_logging
from printo.services.recovery import recover
from printo.wiring import Context, build_context

log = logging.getLogger("printo")


def boot(settings: Settings) -> Context:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "logs").mkdir(parents=True, exist_ok=True)
    setup_logging(settings)
    return build_context(settings)


async def start(ctx: Context) -> None:
    ctx.files.ensure()
    ctx.files.drop_partials()
    ctx.events.bind(asyncio.get_running_loop())
    ctx.converter.start()
    ctx.runner.start()
    recover(ctx)
    status = ctx.cups.status()
    log.info("%s — %s", status.summary, ctx.settings.data_dir)


async def stop(ctx: Context) -> None:
    await ctx.runner.stop()
    await ctx.converter.stop()
    ctx.db.close()


def report(ctx: Context) -> None:
    print(ctx.cups.status().summary)
    print(f"printO will keep files in {ctx.settings.data_dir}.")
