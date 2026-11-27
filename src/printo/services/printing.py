"""Stage a durable print run; the runner is the only code that talks to CUPS."""

import asyncio
import shutil

from printo.config import Settings
from printo.domain.fit import parse_fit
from printo.domain.job import Job
from printo.domain.pages import selection
from printo.domain.rotate import parse_rotations
from printo.domain.status import DONE, FAILED, READY, STOPPED, WAITING, can_print
from printo.errors import UserError
from printo.messages import already_printing, compose_failed, in_trash, not_found, not_ready, ready, waiting_to_print
from printo.printing.compose import compose
from printo.printing.cups import PrinterPort, refuse_reason
from printo.printing.runner import PrintRunner
from printo.printing.split import split_pages
from printo.services.events import Events
from printo.storage.files import Files
from printo.storage.jobs import JobStore


class PrintService:
    def __init__(self, settings: Settings, jobs: JobStore, files: Files, cups: PrinterPort, events: Events, runner: PrintRunner) -> None:
        self.settings = settings
        self.jobs = jobs
        self.files = files
        self.cups = cups
        self.events = events
        self.runner = runner

    async def print_job(self, job_id: str, pages: str, copies: int, fit: int = 100, rotations: dict | None = None) -> Job:
        job = await asyncio.to_thread(self._stage, job_id, pages, copies, fit, rotations)
        self.events.publish_job(job)
        self.runner.wake()
        return job

    async def stop_job(self, job_id: str) -> Job:
        return await self.runner.request_stop(job_id)

    async def continue_job(self, job_id: str) -> Job:
        job = await asyncio.to_thread(self._continue, job_id)
        self.events.publish_job(job)
        self.runner.wake()
        return job

    async def reprint_last_page(self, job_id: str) -> Job:
        job = await asyncio.to_thread(self._reprint_last, job_id)
        self.events.publish_job(job)
        self.runner.wake()
        return job

    async def discard_run(self, job_id: str) -> Job:
        job = await asyncio.to_thread(self._discard, job_id)
        self.events.publish_job(job)
        return job

    def _stage(self, job_id: str, pages: str, copies: int, fit: int, rotations: dict | None) -> Job:
        amount = parse_fit(fit)
        job = self._ready(job_id)
        turned = parse_rotations(rotations, job.page_count or 0)
        indexes = selection(pages, job.page_count or 0, copies, self.settings.max_copies, self.settings.max_sheets)
        reason = refuse_reason(self.cups.status())
        if reason:
            raise UserError(reason, 409)
        locked = self._lock(job, pages, copies, len(indexes) * copies)
        try:
            self._write(locked, indexes, copies, amount, turned)
        except UserError:
            self._fail(locked.id)
            raise
        except Exception:
            self._fail(locked.id)
            raise UserError(compose_failed()) from None
        return locked

    def _ready(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise UserError(not_found(), 404)
        if job.trashed_at:
            raise UserError(in_trash(), 409)
        if job.status in {WAITING, "printing", "stopping"}:
            raise UserError(already_printing(), 409)
        if not can_print(job) or not self.files.document(job.id).is_file():
            raise UserError(not_ready(), 409)
        return job

    def _lock(self, job: Job, pages: str, copies: int, total: int) -> Job:
        expect = {FAILED} if job.status == FAILED else {READY, DONE}
        locked = self.jobs.transition(
            job.id, expect=expect, status=WAITING, failure_stage=None, pages_spec=(pages or "all").strip() or "all",
            copies=copies, cups_job_id=None, print_total=total, print_done=0, print_reprint_last=False, delete_after=None, message=waiting_to_print(), page_count=job.page_count,
        )
        if locked is None:
            raise UserError(already_printing(), 409)
        return locked

    def _write(self, job: Job, indexes: list[int], copies: int, fit: int, rotations: dict[int, int]) -> None:
        destination = self.files.to_print(job.id)
        compose(self.files.document(job.id), destination, indexes, copies, fit, rotations=rotations)
        split_pages(destination, self.files.print_pages(job.id), indexes)

    def _fail(self, job_id: str) -> None:
        failed = self.jobs.transition(
            job_id, expect={WAITING}, status=FAILED, failure_stage="print", message=compose_failed(),
            delete_after=None,
        )
        if failed is not None:
            self.events.publish_job(failed)

    def _continue(self, job_id: str) -> Job:
        job = self._stopped(job_id)
        if not self.files.print_pages(job.id).is_dir():
            raise UserError(compose_failed(), 409)
        saved = self.jobs.transition(job.id, expect={STOPPED}, status=WAITING, message=waiting_to_print(), cups_job_id=None)
        if saved is None:
            raise UserError("This print changed. Please try again.", 409)
        return saved

    def _reprint_last(self, job_id: str) -> Job:
        job = self._stopped(job_id)
        if job.print_done < 1:
            raise UserError("There isn't a finished page to print again.", 409)
        saved = self.jobs.transition(job.id, expect={STOPPED}, status=WAITING, message=waiting_to_print(), cups_job_id=None, print_done=job.print_done - 1, print_reprint_last=True)
        if saved is None:
            raise UserError("This print changed. Please try again.", 409)
        return saved

    def _discard(self, job_id: str) -> Job:
        job = self._stopped(job_id)
        saved = self.jobs.transition(job.id, expect={STOPPED}, status=READY, failure_stage=None, message=ready(), pages_spec=None, copies=None, cups_job_id=None, print_total=None, print_done=0, print_reprint_last=False)
        if saved is None:
            raise UserError("This print changed. Please try again.", 409)
        shutil.rmtree(self.files.print_pages(job.id), ignore_errors=True)
        self.files.to_print(job.id).unlink(missing_ok=True)
        return saved

    def _stopped(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise UserError(not_found(), 404)
        if job.trashed_at:
            raise UserError(in_trash(), 409)
        if job.status != STOPPED or not job.print_total:
            raise UserError(not_ready(), 409)
        return job
