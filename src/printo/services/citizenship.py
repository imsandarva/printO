"""Two single pages become one sheet the counter can preview and print like any other file."""

import logging
import uuid

from printo.domain.job import Job
from printo.domain.kinds import IMAGE, PDF
from printo.domain.status import can_print
from printo.errors import UserError
from printo.messages import citizenship_choose, citizenship_failed, citizenship_pages, citizenship_same, citizenship_wait, in_trash, not_found
from printo.printing.pair import Piece, compose_pair
from printo.services.events import Events
from printo.storage.atomic import copy_sealed
from printo.storage.files import Files
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.citizenship")


class Citizenship:
    def __init__(self, jobs: JobStore, files: Files, events: Events) -> None:
        self.jobs = jobs
        self.files = files
        self.events = events

    def pair(self, ids: list[str]) -> Job:
        if len(ids) != 2 or not all(isinstance(item, str) for item in ids):
            raise UserError(citizenship_choose())
        if ids[0] == ids[1]:
            raise UserError(citizenship_same())
        top, bottom = self._piece(ids[0]), self._piece(ids[1])
        return self._store(top, bottom)

    def _piece(self, job_id: str) -> Piece:
        job = self.jobs.get(job_id)
        if job is None:
            raise UserError(not_found(), 404)
        if job.trashed_at:
            raise UserError(in_trash(), 409)
        if not can_print(job):
            raise UserError(citizenship_wait(), 409)
        if job.page_count != 1:
            raise UserError(citizenship_pages())
        return _source(self.files, job)

    def _store(self, top: Piece, bottom: Piece) -> Job:
        job_id = uuid.uuid4().hex
        partial = self.files.new_partial()
        try:
            compose_pair(top, bottom, partial)
            size = partial.stat().st_size
            if size < 1:
                raise UserError(citizenship_failed())
            self.files.adopt(partial, job_id, ".pdf")
            copy_sealed(self.files.source(job_id, ".pdf"), self.files.document(job_id))
            job = self.jobs.insert_ready(job_id, PDF, ".pdf", size, 1)
        except UserError:
            _discard(self.files, partial, job_id)
            raise
        except Exception:
            log.exception("could not place two files on one page")
            _discard(self.files, partial, job_id)
            raise UserError(citizenship_failed()) from None
        self.events.publish_job(job)
        log.info("citizenship %s", job.original_name)
        return job


def _source(files: Files, job: Job) -> Piece:
    # The original photo, not the A4 it was already placed on. A PDF is the page itself.
    if job.kind == IMAGE and files.source_exists(job):
        return Piece(files.source(job.id, job.source_ext), image=True)
    document = files.document(job.id)
    if document.is_file():
        return Piece(document, image=False)
    if job.kind == PDF and files.source_exists(job):
        return Piece(files.source(job.id, job.source_ext), image=False)
    raise UserError(not_found(), 404)


def _discard(files: Files, partial, job_id: str) -> None:
    partial.unlink(missing_ok=True)
    files.remove_job(job_id)
