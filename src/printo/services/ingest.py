"""Accept one upload: finish the file on disk, then record it, then queue it to be prepared."""

import logging
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from printo.config import Settings
from printo.convert.sniff import detect
from printo.convert.worker import Converter
from printo.domain.job import Job
from printo.errors import UserError
from printo.messages import empty_file, too_big
from printo.services.events import Events
from printo.services.limits import Limits
from printo.storage.atomic import fsync_dir
from printo.storage.files import Files
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.ingest")


class Ingest:
    def __init__(self, settings: Settings, jobs: JobStore, files: Files, limits: Limits, converter: Converter, events: Events) -> None:
        self.settings = settings
        self.jobs = jobs
        self.files = files
        self.limits = limits
        self.converter = converter
        self.events = events

    async def accept(self, filename: str, blocks: AsyncIterator[bytes], ip: str) -> Job:
        self.limits.allow(ip)
        partial = self.files.new_partial()
        job: Job | None = None
        try:
            size = await _spool(partial, blocks, self.settings.max_upload_bytes)
            kind, ext = detect(partial)
            job = self._commit(partial, filename, kind, ext, size)
        finally:
            if job is None:
                partial.unlink(missing_ok=True)
        self.converter.enqueue(job.id)
        self.events.publish_job(job)
        log.info("received %s (%s, %s bytes)", job.public_code, job.kind, job.byte_size)
        return job

    def _commit(self, partial: Path, filename: str, kind: str, ext: str, size: int) -> Job:
        job_id = uuid.uuid4().hex
        try:
            self.files.adopt(partial, job_id, ext)
            return self.jobs.insert_received(job_id, filename, kind, ext, size)
        except Exception:
            self.files.remove_job(job_id)
            raise


async def _spool(path: Path, blocks: AsyncIterator[bytes], max_bytes: int) -> int:
    total = 0
    with path.open("wb") as handle:
        async for block in blocks:
            if not block:
                continue
            total += len(block)
            if total > max_bytes:
                raise UserError(too_big(), 413)
            handle.write(block)
        if total == 0:
            raise UserError(empty_file())
        handle.flush()
        os.fsync(handle.fileno())
    fsync_dir(path.parent)
    return total
