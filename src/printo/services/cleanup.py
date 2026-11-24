"""Forget old files. Printed ones go first. Nothing is removed while it is still arriving or printing."""

import asyncio
import logging
from datetime import timedelta

from printo.clock import Clock, stamp
from printo.config import Settings
from printo.services.events import Events
from printo.storage.files import Files
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.cleanup")


class Cleanup:
    def __init__(self, settings: Settings, jobs: JobStore, files: Files, events: Events, clock: Clock) -> None:
        self.settings = settings
        self.jobs = jobs
        self.files = files
        self.events = events
        self.clock = clock
        self._wake: asyncio.Event | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._wake = asyncio.Event()
        self._task = asyncio.create_task(self._loop(), name="printo-cleanup")

    async def stop(self) -> None:
        if self._wake is not None:
            self._wake.set()
        if self._task is not None:
            await self._task
            self._task = None

    def sweep(self) -> None:
        moment = stamp(self.clock.now())
        for job in self.jobs.due(moment):
            taken = self.jobs.take_expired(job.id, moment)
            if taken is None:
                continue
            self.files.remove_job(taken.id)
            self.events.publish_removed(taken.id)
            log.info("removed old file %s", taken.original_name)
        cutoff = self.clock.now() - timedelta(seconds=self.settings.partial_max_age_seconds)
        self.files.drop_old_partials(cutoff)

    async def _loop(self) -> None:
        while self._wake is not None and not self._wake.is_set():
            try:
                await asyncio.to_thread(self.sweep)
            except Exception:
                log.exception("cleanup failed")
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.settings.cleanup_interval_seconds)
            except TimeoutError:
                continue
