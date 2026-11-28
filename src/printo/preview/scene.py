"""Sample files for the counter. Clicks change this list only; the printer is never asked."""

import hashlib
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone

from printo.clock import stamp
from printo.config import default_settings
from printo.domain.fit import parse_fit
from printo.domain.job import Job
from printo.domain.kinds import IMAGE, OFFICE, PDF
from printo.domain.pages import selection
from printo.domain.rotate import parse_angle, parse_rotations
from printo.domain.status import CONVERTING, DONE, FAILED, PRINTING, READY, RECEIVED, STAGE_CONVERT, STAGE_PRINT, can_print, can_retry
from printo.errors import UserError
from printo.messages import (
    already_printing, arrived, convert_failed, in_trash, no_retry, not_found, not_ready, office_failed, preparing, present,
    citizenship_choose, citizenship_pages, citizenship_same, citizenship_wait, printing, ready, rejected, removed,
    removed_but_printer, removed_event, sent, still_kept, trashed, trashed_but_printer, validation,
)
from printo.pictures.raster import BLANK_JPEG, render_bytes
from printo.preview.paper import pair_sheet, sheet

_PAIR_NAME = re.compile(r"^Citizenship_(\d+)\.pdf$")


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
        self._pairs: dict[str, dict] = {}
        self._image_angles: dict[str, int] = {}
        self._files: dict[str, bytes] = {}
        self._pictures: dict[tuple[str, str, int], bytes] = {}
        self._pictured: set[tuple[str, str]] = set()
        self._pic_lock = threading.Lock()

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

    def preview_status(self, job_id: str) -> dict:
        with self._lock:
            job = self._get(job_id)
            count = job.page_count or 0
            custom = self._files.get(job_id)
        if count < 1:
            raise UserError(not_found(), 404)
        data = custom if custom is not None else sheet(count)
        revision = hashlib.sha256(data).hexdigest()[:16]
        self._ensure_pictures(job_id, revision, data, count)
        return {"total": count, "ready": count, "revision": revision}

    def preview_image(self, job_id: str, page: int, revision: str) -> bytes:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise UserError(not_found(), 404)
        self.preview_status(job_id)
        with self._pic_lock:
            found = self._pictures.get((job_id, revision, page))
        if not found:
            raise UserError(not_found(), 404)
        return found

    def file(self, job_id: str) -> bytes:
        with self._lock:
            job = self._get(job_id)
            count = job.page_count or 0
            custom = self._files.get(job_id)
        if count < 1:
            raise UserError(not_found(), 404)
        return custom if custom is not None else sheet(count)

    def pair_meta(self, job_id: str) -> dict:
        with self._lock:
            self._get(job_id)
            return {"pair": self._pairs.get(job_id), "angle": self._image_angles.get(job_id, 0)}

    def rotate(self, job_id: str, payload: dict) -> dict:
        target = payload.get("target")
        with self._lock:
            job = self._get(job_id)
            if job.trashed_at:
                raise UserError(in_trash(), 409)
            if job.status == PRINTING:
                raise UserError(already_printing(), 409)
            if not can_print(job):
                raise UserError(not_ready(), 409)
            if target in {"pair", "sheet"}:
                meta = self._pairs.get(job_id)
                if meta is None:
                    raise UserError(validation())
                rotations = list(meta["rotations"])
                cur_sheet = int(meta["sheet"])
                if target == "pair":
                    index = payload.get("index")
                    if isinstance(index, bool) or index not in (0, 1):
                        raise UserError(validation())
                    raw = payload.get("angle")
                    rotations[index] = (rotations[index] + 90) % 360 if raw is None else parse_angle(raw)
                else:
                    raw = payload.get("angle")
                    cur_sheet = (cur_sheet + 90) % 360 if raw is None else parse_angle(raw)
                pdf_bytes, boxes = pair_sheet(rotations=(rotations[0], rotations[1]), sheet_rotation=cur_sheet)
                updated = {"rotations": rotations, "sheet": cur_sheet, "boxes": boxes}
                self._pairs[job_id] = updated
                self._files[job_id] = pdf_bytes
                outcome = {"job": present(job), "pair": updated}
            elif target == "image" and job.kind == IMAGE and job.page_count == 1:
                raw = payload.get("angle")
                angle = (self._image_angles.get(job_id, 0) + 90) % 360 if raw is None else parse_angle(raw)
                self._image_angles[job_id] = angle
                self._files[job_id] = sheet(1, rotate=angle)
                outcome = {"job": present(job), "angle": angle}
            else:
                outcome = None
        if outcome is None:
            raise UserError(validation())
        outcome["preview"] = self.preview_status(job_id)
        return outcome

    def print_job(self, job_id: str, pages: str, copies: int, fit: int = 100, rotations: dict | None = None, landscape: bool = False) -> dict:
        parse_fit(fit)
        with self._lock:
            job = self._get(job_id)
            if job.trashed_at:
                raise UserError(in_trash(), 409)
            if job.status == PRINTING:
                raise UserError(already_printing(), 409)
            if not can_print(job):
                raise UserError(not_ready(), 409)
            parse_rotations(rotations, job.page_count or 0)
            selection(pages or "all", job.page_count or 0, copies, self._copies, self._sheets, landscape=bool(landscape))
            spec = (pages or "all").strip() or "all"
            updated = _with(job, status=PRINTING, failure_stage=None, pages_spec=spec, copies=copies, message=printing())
            self._save(updated)
            self._arm(job_id, self._finish_print)
        self._emit("job", present(updated))
        return present(updated)

    def citizenship(self, ids: list[str]) -> dict:
        if len(ids) != 2 or not all(isinstance(item, str) for item in ids):
            raise UserError(citizenship_choose())
        if ids[0] == ids[1]:
            raise UserError(citizenship_same())
        with self._lock:
            for job_id in ids:
                job = self._get(job_id)
                if job.trashed_at:
                    raise UserError(in_trash(), 409)
                if not can_print(job):
                    raise UserError(citizenship_wait(), 409)
                if job.page_count != 1:
                    raise UserError(citizenship_pages())
            moment = stamp(datetime.now(timezone.utc))
            new_id = uuid.uuid4().hex
            pdf_bytes, boxes = pair_sheet()
            self._pairs[new_id] = {"rotations": [0, 0], "sheet": 0, "boxes": boxes}
            self._files[new_id] = pdf_bytes
            created = Job(
                id=new_id, original_name=self._next_pair_name(), kind=PDF, source_ext=".pdf", status=READY,
                failure_stage=None, message=ready(), byte_size=48_000, page_count=1, pages_spec="all", copies=1,
                cups_job_id=None, print_total=None, print_done=0, print_reprint_last=False,
                created_at=moment, updated_at=moment, delete_after=None, trashed_at=None,
            )
            self._jobs.append(created)
        result = present(created)
        self._emit("job", result)
        return result

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

    def _ensure_pictures(self, job_id: str, revision: str, data: bytes, count: int) -> None:
        with self._pic_lock:
            if (job_id, revision) in self._pictured:
                return
            made: dict[int, bytes] = {}
            for page in range(1, count + 1):
                try:
                    made[page] = render_bytes(data, page)
                except Exception:
                    made[page] = BLANK_JPEG
            for page, blob in made.items():
                self._pictures[(job_id, revision, page)] = blob
            self._pictured.add((job_id, revision))

    def _next_pair_name(self) -> str:
        highest = 0
        for job in self._jobs:
            match = _PAIR_NAME.fullmatch(job.original_name)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"Citizenship_{highest + 1}.pdf"


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
            copies=copies or (1 if pages else None), cups_job_id=None, print_total=None, print_done=0, print_reprint_last=False,
            created_at=moment, updated_at=moment, delete_after=None, trashed_at=None,
    )


def _with(job: Job, **changes: object) -> Job:
    values = {name: getattr(job, name) for name in Job.__dataclass_fields__}
    values.update(changes)
    values["updated_at"] = stamp(datetime.now(timezone.utc))
    return Job(**values)
