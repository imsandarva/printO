"""Sample files for the counter. Clicks change this list only; the printer is never asked."""

import threading
from datetime import datetime, timedelta, timezone

from printo.clock import stamp
from printo.config import default_settings
from printo.domain.job import Job
from printo.domain.kinds import IMAGE, OFFICE, PDF
from printo.domain.pages import selection
from printo.domain.status import CONVERTING, DONE, FAILED, PRINTING, READY, RECEIVED, STAGE_CONVERT, STAGE_PRINT, can_print, can_retry
from printo.errors import UserError
from printo.messages import (
    already_printing, arrived, convert_failed, in_trash, no_retry, not_found, not_ready, office_failed, preparing, present,
    printing, ready, rejected, removed, removed_but_printer, removed_event, sent, still_kept, trashed, trashed_but_printer,
)
from printo.preview.paper import sheet


class Scene:
    def __init__(self, emit, delay: float = 0.9) -> None:
        limits = default_settings()
        self._emit = emit
        self._delay = delay
        self._copies = limits.max_copies
        self._sheets = limits.max_sheets
        self._lock = threading.Lock()
        self._jobs = _samples()
        self._timers: dict[str, threading.Timer] = {}

    def close(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

    def jobs(self, status: str | None = None, *, trashed: bool = False) -> list[dict]:
        with self._lock:
            chosen = [job for job in self._jobs if bool(job.trashed_at) is trashed and (status is None or job.status == status)]
            chosen.sort(key=lambda job: job.created_at, reverse=True)
            return [present(job) for job in chosen]

    def one(self, job_id: str) -> dict:
        with self._lock:
            return present(self._get(job_id))

    def file(self, job_id: str) -> bytes:
        with self._lock:
            count = self._get(job_id).page_count or 0
        if count < 1:
            raise UserError(not_found(), 404)
        return sheet(count)

    def print_job(self, job_id: str, pages: str, copies: int) -> dict:
        with self._lock:
            job = self._get(job_id)
            if job.trashed_at:
                raise UserError(in_trash(), 409)
            if job.status == PRINTING:
                raise UserError(already_printing(), 409)
            if not can_print(job):
                raise UserError(not_ready(), 409)
            selection(pages or "all", job.page_count or 0, copies, self._copies, self._sheets)
            spec = (pages or "all").strip() or "all"
            updated = _with(job, status=PRINTING, failure_stage=None, pages_spec=spec, copies=copies, message=printing())
            self._save(updated)
            self._arm(job_id, self._finish_print)
        self._emit("job", present(updated))
        return present(updated)

    def retry(self, job_id: str) -> dict:
        with self._lock:
            job = self._get(job_id)
            if job.trashed_at:
                raise UserError(in_trash(), 409)
            if not can_retry(job):
                raise UserError(no_retry(), 409)
            updated = _with(job, status=CONVERTING, failure_stage=None, message=preparing(), page_count=None)
            self._save(updated)
            self._arm(job_id, self._finish_retry)
        self._emit("job", present(updated))
        return present(updated)

    def trash(self, job_id: str) -> dict:
        with self._lock:
            job = self._get(job_id)
            warning = job.status == PRINTING and not job.trashed_at
            updated = job if job.trashed_at else _with(job, trashed_at=stamp(datetime.now(timezone.utc)))
            self._save(updated)
        self._emit("job", present(updated))
        return {"message": trashed_but_printer() if warning else trashed(), "job": present(updated)}

    def restore(self, job_id: str) -> dict:
        with self._lock:
            job = self._get(job_id)
            if not job.trashed_at:
                raise UserError(not_found(), 404)
            updated = _with(job, trashed_at=None)
            self._save(updated)
        self._emit("job", present(updated))
        return present(updated)

    def remove(self, job_id: str) -> str:
        with self._lock:
            job = self._get(job_id)
            if not job.trashed_at:
                raise UserError(still_kept(), 409)
            self._jobs = [item for item in self._jobs if item.id != job_id]
            self._drop_timer(job_id)
            was_printing = job.status == PRINTING
        self._emit("job", removed_event(job_id))
        return removed_but_printer() if was_printing else removed()

    def _finish_print(self, job_id: str) -> None:
        self._finish(job_id, PRINTING, status=DONE, failure_stage=None, message=sent())

    def _finish_retry(self, job_id: str) -> None:
        self._finish(job_id, CONVERTING, status=READY, failure_stage=None, message=ready(), page_count=2, pages_spec="all", copies=1)

    def _finish(self, job_id: str, expect: str, **changes: object) -> None:
        with self._lock:
            self._timers.pop(job_id, None)
            job = self._find(job_id)
            if job is None or job.status != expect:
                return
            updated = _with(job, **changes)
            self._save(updated)
        self._emit("job", present(updated))

    def _arm(self, job_id: str, fn) -> None:
        # Caller holds the lock. The timer runs later, on its own thread.
        self._drop_timer(job_id)
        timer = threading.Timer(self._delay, fn, args=(job_id,))
        timer.daemon = True
        self._timers[job_id] = timer
        timer.start()

    def _drop_timer(self, job_id: str) -> None:
        timer = self._timers.pop(job_id, None)
        if timer is not None:
            timer.cancel()

    def _save(self, job: Job) -> None:
        self._jobs = [job if item.id == job.id else item for item in self._jobs]

    def _get(self, job_id: str) -> Job:
        job = self._find(job_id)
        if job is None:
            raise UserError(not_found(), 404)
        return job

    def _find(self, job_id: str) -> Job | None:
        return next((job for job in self._jobs if job.id == job_id), None)


def _samples() -> list[Job]:
    # Newest first is decided when the list is read. The times only have to be in the right order.
    return [
        _job("1", "School admission form.pdf", PDF, ".pdf", READY, ready(), pages=4, ago=20),
        _job("2", "Passport photo.jpg", IMAGE, ".jpg", READY, ready(), pages=1, ago=8 * 60),
        _job("3", "Rent receipt.pdf", PDF, ".pdf", PRINTING, printing(), pages=2, ago=14 * 60),
        _job("4", "Notes from class.docx", OFFICE, ".docx", CONVERTING, preparing(), ago=20 * 60),
        _job("5", "Scan from the counter.pdf", PDF, ".pdf", RECEIVED, arrived(), ago=28 * 60),
        _job("6", "Letter to the ward office.doc", OFFICE, ".doc", FAILED, office_failed(), failure=STAGE_CONVERT, ago=45 * 60),
        _job("7", "Photocopy of the citizenship certificate application.pdf", PDF, ".pdf", FAILED, rejected(), pages=3, failure=STAGE_PRINT, ago=2 * 3600),
        _job("8", "Homework.pdf", PDF, ".pdf", DONE, sent(), pages=2, spec="1-2", copies=2, ago=5 * 3600),
        _job("9", "Old scan.pdf", PDF, ".pdf", FAILED, convert_failed(), failure=STAGE_CONVERT, ago=6 * 3600),
        _job("10", "Bank statement.pdf", PDF, ".pdf", DONE, sent(), pages=3, ago=4 * 86400),
        _job("11", "Invitation.pdf", PDF, ".pdf", DONE, sent(), pages=1, ago=4 * 86400 + 3600),
        _job("12", "Electricity bill.pdf", PDF, ".pdf", DONE, sent(), pages=2, ago=40 * 86400),
        _job("13", "Old admission form.pdf", PDF, ".pdf", READY, ready(), pages=2, ago=400 * 86400),
    ]


def _job(number: str, name: str, kind: str, ext: str, status: str, message: str, pages: int | None = None, spec: str | None = None, copies: int | None = None, failure: str | None = None, ago: float = 0) -> Job:
    moment = stamp(datetime.now(timezone.utc) - timedelta(seconds=ago))
    return Job(
        id=f"{int(number):032x}", original_name=name, kind=kind, source_ext=ext, status=status,
        failure_stage=failure, message=message, byte_size=48_000, page_count=pages, pages_spec=spec or ("all" if pages else None),
        copies=copies or (1 if pages else None), cups_job_id=None, created_at=moment, updated_at=moment, delete_after=None, trashed_at=None,
    )


def _with(job: Job, **changes: object) -> Job:
    values = {name: getattr(job, name) for name in Job.__dataclass_fields__}
    values.update(changes)
    values["updated_at"] = stamp(datetime.now(timezone.utc))
    return Job(**values)
