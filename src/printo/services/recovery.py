"""After a crash or a power cut, finish or requeue whatever was left half-done. Never mark it printed."""

import logging
import shutil
from typing import Protocol

from printo.config import Settings
from printo.convert.worker import Converter
from printo.domain.status import CONVERTING, PRINTING, RECEIVED, STOPPED, STOPPING, WAITING
from printo.messages import preparing, stopped_at
from printo.services.events import Events
from printo.storage.files import Files
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.recover")


class Shop(Protocol):
    settings: Settings
    jobs: JobStore
    files: Files
    converter: Converter
    events: Events


def recover(shop: Shop) -> None:
    _drop_broken(shop)
    resumed: set[str] = set()
    for job in shop.jobs.matching(CONVERTING, placed="all"):
        reset = shop.jobs.transition(job.id, expect={CONVERTING}, status=RECEIVED, message=preparing(), failure_stage=None)
        if reset is not None:
            resumed.add(reset.id)
            shop.converter.enqueue(reset.id)
    for job in shop.jobs.matching(RECEIVED):
        if job.id not in resumed:
            shop.converter.enqueue(job.id)
    for status in (WAITING, PRINTING, STOPPING):
        for job in shop.jobs.matching(status, placed="all"):
            # A sheet might be in the printer after a power cut. Never guess and start another one.
            saved = shop.jobs.transition(
                job.id, expect={status}, status=STOPPED, cups_job_id=None, print_reprint_last=False,
                message=stopped_at(job.print_done, job.print_total or 0),
            )
            if saved is not None:
                shop.events.publish_job(saved)


def _drop_broken(shop: Shop) -> None:
    known = {job.id for job in shop.jobs.all()}
    for directory in shop.files.job_dirs():
        if directory.name not in known:
            shutil.rmtree(directory, ignore_errors=True)
    for job in shop.jobs.all():
        if shop.files.source_exists(job):
            continue
        log.warning("dropped an unfinished file %s", job.original_name)
        shop.files.remove_job(job.id)
        shop.jobs.delete(job.id)
