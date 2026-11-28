"""Feed CUPS one confirmed page at a time, with a durable stop point between pages."""

import asyncio
import logging
import time

from printo.config import Settings
from printo.domain.pages import parse_pages
from printo.domain.status import DONE, PRINTING, STOPPED, STOPPING, WAITING
from printo.errors import UserError
from printo.messages import compose_failed, in_trash, not_found, paused_for_printer, printing_page, rejected, stopped_at, stopping, waiting_to_print
from printo.printing.cups import PrinterPort, refuse_reason
from printo.services.events import Events
from printo.storage.files import Files
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.print")


class PrintRunner:
    def __init__(self, settings: Settings, jobs: JobStore, files: Files, cups: PrinterPort, events: Events) -> None:
        self.settings = settings
        self.jobs = jobs
        self.files = files
        self.cups = cups
        self.events = events
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._submitting = asyncio.Lock()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="printo-page-runner")
        self.wake()

    def wake(self) -> None:
        self._wake.set()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def request_stop(self, job_id: str):
        # Waiting for an lp submission to finish is what prevents a Stop race from adding another sheet.
        async with self._submitting:
            job = await asyncio.to_thread(self._mark_stop, job_id)
        self.events.publish_job(job)
        self.wake()
        return job

    def _mark_stop(self, job_id: str):
        job = self.jobs.get(job_id)
        if job is None:
            raise UserError(not_found(), 404)
        if job.trashed_at:
            raise UserError(in_trash(), 409)
        total = job.print_total or 0
        if job.status == WAITING:
            saved = self.jobs.transition(job.id, expect={WAITING}, status=STOPPED, message=stopped_at(job.print_done, total, sheet=self._sheets(job)), cups_job_id=None)
        elif job.status == PRINTING:
            saved = self.jobs.transition(job.id, expect={PRINTING}, status=STOPPING, message=stopping(sheet=self._sheets(job)))
        elif job.status in {STOPPING, STOPPED}:
            saved = job
        else:
            raise UserError("This print isn't running.", 409)
        if saved is None:
            raise UserError("This print changed. Please try again.", 409)
        return saved

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            while True:
                job = await asyncio.to_thread(self.jobs.next_waiting)
                if job is None:
                    break
                await self._run_job(job.id)

    async def _run_job(self, job_id: str) -> None:
        begun = await asyncio.to_thread(self._begin, job_id)
        if begun is None:
            return
        self.events.publish_job(begun)
        started = time.monotonic()
        while True:
            job = await asyncio.to_thread(self.jobs.get, job_id)
            if job is None or job.status not in {PRINTING, STOPPING}:
                return
            if job.status == STOPPING and not job.cups_job_id:
                paused = await asyncio.to_thread(self._pause, job, stopped_at(job.print_done, job.print_total or 0, sheet=self._sheets(job)))
                if paused:
                    self.events.publish_job(paused)
                return
            if not job.cups_job_id:
                submitted = await self._submit(job)
                if not submitted:
                    return
                started = time.monotonic()
                continue
            outcome = await asyncio.to_thread(self.cups.classify, job.cups_job_id)
            if outcome == "completed":
                total = job.print_total or 0
                settled = await asyncio.to_thread(
                    self.jobs.complete_page, job.id,
                    next_message=printing_page(job.print_done + 2, total, sheet=self._sheets(job)),
                    stopped_message=stopped_at(job.print_done + 1, total, sheet=self._sheets(job)), done_message="Sent to the printer.",
                )
                if settled:
                    self.events.publish_job(settled)
                if settled is None or settled.status != PRINTING:
                    return
                continue
            if outcome == "active" and time.monotonic() - started < self.settings.print_give_up_seconds:
                await asyncio.sleep(self.settings.print_poll_seconds)
                continue
            if outcome == "unknown" and time.monotonic() - started < self.settings.print_give_up_seconds:
                await asyncio.sleep(self.settings.print_poll_seconds)
                continue
            paused = await asyncio.to_thread(self._pause, job, paused_for_printer(rejected() if outcome == "aborted" else self.cups.status().summary))
            if paused:
                self.events.publish_job(paused)
            return

    def _begin(self, job_id: str):
        job = self.jobs.get(job_id)
        if job is None or job.status != WAITING or not job.print_total:
            return None
        return self.jobs.transition(
            job.id, expect={WAITING}, status=PRINTING,
            message=printing_page(job.print_done + 1, job.print_total, sheet=self._sheets(job)), cups_job_id=None,
        )

    async def _submit(self, job) -> bool:
        async with self._submitting:
            current = await asyncio.to_thread(self.jobs.get, job.id)
            if current is None or current.trashed_at or current.status != PRINTING:
                return False
            reason = await asyncio.to_thread(self._printer_reason)
            if reason:
                paused = await asyncio.to_thread(self._pause, current, paused_for_printer(reason))
                if paused:
                    self.events.publish_job(paused)
                return False
            page = await asyncio.to_thread(self._page_path, current)
            if page is None:
                paused = await asyncio.to_thread(self._pause, current, compose_failed())
                if paused:
                    self.events.publish_job(paused)
                return False
            try:
                cups_id = await asyncio.to_thread(self.cups.submit, page, f"printo {current.original_name}")
            except UserError as exc:
                paused = await asyncio.to_thread(self._pause, current, paused_for_printer(exc.message))
                if paused:
                    self.events.publish_job(paused)
                return False
            saved = await asyncio.to_thread(
                self.jobs.transition, current.id, expect={PRINTING}, status=PRINTING, cups_job_id=cups_id,
            )
        if saved is None:
            log.error("CUPS accepted %s for %s but its print state changed", cups_id, current.id)
            return False
        self.events.publish_job(saved)
        return True

    def _page_path(self, job):
        sheets = self.files.sheet_count(job.id)
        if sheets:
            page = self.files.print_page(job.id, job.print_done % sheets)
            return page if page.is_file() else None
        try:
            indexes = parse_pages(job.pages_spec or "all", job.page_count or 0)
        except UserError:
            return None
        if not indexes:
            return None
        page = self.files.print_page(job.id, indexes[job.print_done % len(indexes)])
        return page if page.is_file() else None

    def _sheets(self, job) -> bool:
        return self.files.sheet_count(job.id) is not None

    def _printer_reason(self) -> str | None:
        return refuse_reason(self.cups.status())

    def _pause(self, job, message: str):
        return self.jobs.transition(
            job.id, expect={PRINTING, STOPPING}, status=STOPPED, message=message, cups_job_id=None,
        )
