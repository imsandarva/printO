"""Follow one CUPS job until it leaves the queue. Nothing polls while nothing is printing."""

import asyncio
import logging
import time

from printo.config import Settings
from printo.printing.cups import PrinterPort
from printo.printing.outcome import interpret
from printo.printing.settle import settle
from printo.services.events import Events
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.print")


class PrintWatch:
    def __init__(self, settings: Settings, jobs: JobStore, cups: PrinterPort, events: Events) -> None:
        self.settings = settings
        self.jobs = jobs
        self.cups = cups
        self.events = events
        self._tasks: set[asyncio.Task[None]] = set()

    def follow(self, job_id: str) -> None:
        task = asyncio.create_task(self._follow(job_id), name=f"printo-watch-{job_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _follow(self, job_id: str) -> None:
        started = time.monotonic()
        try:
            await self._until_settled(job_id, started)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("lost track of %s", job_id)

    async def _until_settled(self, job_id: str, started: float) -> None:
        while True:
            await asyncio.sleep(self.settings.print_poll_seconds)
            job = self.jobs.get(job_id)
            if job is None or job.status != "printing" or not job.cups_job_id:
                return
            outcome = await asyncio.to_thread(self.cups.classify, job.cups_job_id)
            decision = interpret(
                outcome, time.monotonic() - started,
                self.settings.print_give_up_seconds, self.settings.print_missing_grace_seconds,
            )
            if decision is None:
                continue
            if decision == "failed" and outcome == "active":
                await asyncio.to_thread(self.cups.cancel, job.cups_job_id)
            settle(self.jobs, self.events, job_id, decision, outcome)
            return
