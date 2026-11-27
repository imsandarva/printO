"""Trash keeps a file off the counter without throwing it away. Deleting it there is the only way it goes."""

import asyncio
import logging

from printo.convert.worker import Converter
from printo.domain.job import Job
from printo.domain.status import PRINTING, RECEIVED, STOPPING, WAITING
from printo.errors import UserError
from printo.messages import not_found, removed, removed_but_printer, still_kept, trashed, trashed_but_printer, try_again
from printo.printing.runner import PrintRunner
from printo.services.events import Events
from printo.storage.files import Files
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.trash")


class Trash:
    def __init__(self, jobs: JobStore, files: Files, runner: PrintRunner, events: Events, converter: Converter) -> None:
        self.jobs = jobs
        self.files = files
        self.runner = runner
        self.events = events
        self.converter = converter

    async def move(self, job_id: str) -> tuple[str, Job]:
        job = await asyncio.to_thread(self._held, job_id)
        warning = await self._stop(job)
        return await asyncio.to_thread(self._move, job_id, warning)

    async def restore(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._restore, job_id)

    async def forget(self, job_id: str) -> str:
        job = await asyncio.to_thread(self._held, job_id)
        warning = await self._stop(job)
        return await asyncio.to_thread(self._forget, job_id, warning)

    def _move(self, job_id: str, warning: bool) -> tuple[str, Job]:
        job = self._held(job_id)
        if job.trashed_at is None:
            saved = self.jobs.place_in_trash(job.id) or self.jobs.get(job.id)
            if saved is None or not saved.trashed_at:
                raise UserError(try_again(), 409)
            job = saved
            self.events.publish_job(job)
            log.info("trashed %s", job.original_name)
        return (trashed_but_printer() if warning else trashed()), job

    def _restore(self, job_id: str) -> Job:
        job = self._held(job_id)
        if not job.trashed_at:
            raise UserError(not_found(), 404)
        saved = self.jobs.restore(job.id)
        if saved is None:
            raise UserError(try_again(), 409)
        if saved.status == RECEIVED:
            self.converter.enqueue(saved.id)
        self.events.publish_job(saved)
        log.info("restored %s", saved.original_name)
        return saved

    def _forget(self, job_id: str, warning: bool) -> str:
        job = self._held(job_id)
        if not job.trashed_at:
            raise UserError(still_kept(), 409)
        if not self.jobs.delete(job.id):
            raise UserError(not_found(), 404)
        self.files.remove_job(job.id)
        self.events.publish_removed(job.id)
        log.info("deleted %s", job.original_name)
        return removed_but_printer() if warning else removed()

    def _held(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise UserError(not_found(), 404)
        return job

    async def _stop(self, job: Job) -> bool:
        """Use the same page boundary as Stop, even when a file is being removed."""
        if job.status not in {WAITING, PRINTING, STOPPING}:
            return False
        # A page already in CUPS is allowed to finish; no delete action cuts a sheet in half.
        warning = job.status in {PRINTING, STOPPING} and bool(job.cups_job_id)
        await self.runner.request_stop(job.id)
        return warning
