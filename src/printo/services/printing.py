"""Print a ready file, or take one off the list. CUPS is only contacted after the row says printing."""

import asyncio
import logging

from printo.config import Settings
from printo.convert.pdf_doc import page_count
from printo.domain.job import Job
from printo.domain.pages import selection
from printo.domain.status import DONE, FAILED, PRINTING, READY, STAGE_PRINT, can_print
from printo.errors import UserError
from printo.messages import already_printing, compose_failed, not_found, not_ready, printing, removed, removed_but_printer
from printo.printing.compose import compose
from printo.printing.cups import PrinterPort, refuse_reason
from printo.printing.watch import PrintWatch
from printo.services.events import Events
from printo.storage.files import Files
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.print")


class PrintService:
    def __init__(self, settings: Settings, jobs: JobStore, files: Files, cups: PrinterPort, events: Events, watch: PrintWatch) -> None:
        self.settings = settings
        self.jobs = jobs
        self.files = files
        self.cups = cups
        self.events = events
        self.watch = watch

    async def print_job(self, job_id: str, pages: str, copies: int) -> Job:
        job = await asyncio.to_thread(self._submit, job_id, pages, copies)
        if job.status == PRINTING and job.cups_job_id:
            self.watch.follow(job.id)
        self.events.publish_job(job)
        return job

    async def cancel_job(self, job_id: str) -> str:
        return await asyncio.to_thread(self._cancel, job_id)

    def _submit(self, job_id: str, pages: str, copies: int) -> Job:
        job = self._ready(job_id)
        indexes = selection(pages, job.page_count or 0, copies, self.settings.max_copies, self.settings.max_sheets)
        self._require_printer()
        locked = self._lock(job, pages, copies)
        try:
            self._write(locked, indexes, copies)
            cups_id = self.cups.submit(self.files.to_print(locked.id), f"printo {locked.original_name}")
        except UserError as exc:
            self._fail(locked.id, exc.message)
            raise
        except Exception:
            log.exception("print failed for %s", locked.original_name)
            self._fail(locked.id, compose_failed())
            raise UserError(compose_failed()) from None
        saved = self.jobs.transition(locked.id, expect={PRINTING}, status=PRINTING, cups_job_id=cups_id, message=printing())
        if saved is None:
            # lp already accepted it, and the row disappeared. Cancel so it cannot print unseen.
            log.error("printer accepted %s but %s vanished", cups_id, locked.original_name)
            self.cups.cancel(cups_id)
            raise UserError(not_found(), 404)
        log.info("sent %s as %s", saved.original_name, cups_id)
        return saved

    def _ready(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise UserError(not_found(), 404)
        if job.status == PRINTING:
            raise UserError(already_printing(), 409)
        if not can_print(job) or not self.files.document(job.id).is_file():
            raise UserError(not_ready(), 409)
        return job

    def _require_printer(self) -> None:
        reason = refuse_reason(self.cups.status())
        if reason:
            raise UserError(reason, 409)

    def _lock(self, job: Job, pages: str, copies: int) -> Job:
        expect = {FAILED} if job.status == FAILED else {READY, DONE}
        locked = self.jobs.transition(
            job.id, expect=expect, status=PRINTING, failure_stage=None, pages_spec=(pages or "all").strip() or "all",
            copies=copies, cups_job_id=None, delete_after=None, message=printing(), page_count=job.page_count,
        )
        if locked is None:
            raise UserError(already_printing(), 409)
        return locked

    def _write(self, job: Job, indexes: list[int], copies: int) -> None:
        dest = self.files.to_print(job.id)
        compose(self.files.document(job.id), dest, indexes, copies)
        if page_count(dest) != len(indexes) * copies:
            raise UserError(compose_failed())

    def _fail(self, job_id: str, message: str) -> None:
        failed = self.jobs.transition(
            job_id, expect={PRINTING}, status=FAILED, failure_stage=STAGE_PRINT, message=message,
            delete_after=None,
        )
        if failed is not None:
            self.events.publish_job(failed)

    def _cancel(self, job_id: str) -> str:
        job = self.jobs.get(job_id)
        if job is None:
            raise UserError(not_found(), 404)
        warning = bool(job.status == PRINTING and job.cups_job_id and not self.cups.cancel(job.cups_job_id))
        if not self.jobs.delete(job.id):
            raise UserError(not_found(), 404)
        self.files.remove_job(job.id)
        self.events.publish_removed(job.id)
        log.info("removed %s", job.original_name)
        return removed_but_printer() if warning else removed()
