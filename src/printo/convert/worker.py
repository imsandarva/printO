"""Prepare one file at a time. LibreOffice and a small laptop cannot afford two at once, and idle costs nothing."""

import asyncio
import logging
import queue

from printo.config import Settings
from printo.convert.office import Office
from printo.convert.prepare import prepare
from printo.domain.job import Job
from printo.domain.status import CONVERTING, FAILED, READY, RECEIVED, STAGE_CONVERT, can_retry
from printo.errors import UserError
from printo.messages import convert_failed, in_trash, not_found, no_retry, preparing, ready, try_again
from printo.services.events import Events
from printo.storage.files import Files
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.convert")


class Converter:
    def __init__(self, settings: Settings, jobs: JobStore, files: Files, events: Events, office: Office) -> None:
        self.settings = settings
        self.jobs = jobs
        self.files = files
        self.events = events
        self.office = office
        self._queue: queue.SimpleQueue[str | None] = queue.SimpleQueue()
        self._task: asyncio.Task[None] | None = None

    def enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="printo-convert")

    async def stop(self) -> None:
        self.office.stop()
        self._queue.put(None)
        if self._task is not None:
            await self._task
            self._task = None

    def retry(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None or not self.files.source_exists(job):
            raise UserError(not_found(), 404)
        if job.trashed_at:
            raise UserError(in_trash(), 409)
        if not can_retry(job):
            raise UserError(no_retry(), 409)
        updated = self.jobs.transition(
            job.id, expect={FAILED}, status=RECEIVED, failure_stage=None, page_count=None,
            message=preparing(), delete_after=None,
        )
        if updated is None:
            raise UserError(try_again(), 409)
        self.enqueue(updated.id)
        self.events.publish_job(updated)
        return updated

    async def _loop(self) -> None:
        while True:
            job_id = await asyncio.to_thread(self._queue.get)
            if job_id is None:
                return
            try:
                await asyncio.to_thread(self._prepare_one, job_id)
            except Exception:
                log.exception("prepare loop")

    def _prepare_one(self, job_id: str) -> None:
        # A file already in Trash should not spend a turn in LibreOffice.
        current = self.jobs.get(job_id)
        if current is None or current.trashed_at:
            return
        job = self.jobs.transition(job_id, expect={RECEIVED}, status=CONVERTING, message=preparing(), failure_stage=None)
        if job is None:
            return
        self.events.publish_job(job)
        try:
            prepared = prepare(
                self.files.source(job.id, job.source_ext), self.files.document(job.id),
                job.kind, self.settings, self.office, self.files.profile,
            )
        except UserError as exc:
            self._fail(job.id, exc.message)
            return
        except Exception:
            log.exception("could not prepare %s", job.original_name)
            self._fail(job.id, convert_failed())
            return
        done = self.jobs.transition(
            job.id, expect={CONVERTING}, status=READY, page_count=prepared.page_count,
            message=ready(), failure_stage=None, delete_after=None,
        )
        if done is not None:
            log.info("ready %s (%s pages)", done.original_name, done.page_count)
            self.events.publish_job(done)

    def _fail(self, job_id: str, message: str) -> None:
        failed = self.jobs.transition(
            job_id, expect={CONVERTING}, status=FAILED, failure_stage=STAGE_CONVERT, message=message,
            delete_after=None,
        )
        if failed is not None:
            log.info("prepare failed %s", failed.original_name)
            self.events.publish_job(failed)
