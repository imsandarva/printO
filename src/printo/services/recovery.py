"""After a crash or a power cut, finish or requeue whatever was left half-done. Never mark it printed."""

import logging
import shutil
from typing import Protocol

from printo.config import Settings
from printo.convert.worker import Converter
from printo.domain.job import Job
from printo.domain.status import CONVERTING, PRINTING, RECEIVED
from printo.messages import preparing
from printo.printing.cups import PrinterPort
from printo.printing.settle import settle
from printo.printing.watch import PrintWatch
from printo.services.events import Events
from printo.storage.files import Files
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.recover")


class Shop(Protocol):
    settings: Settings
    jobs: JobStore
    files: Files
    cups: PrinterPort
    converter: Converter
    watch: PrintWatch
    events: Events


def recover(shop: Shop) -> None:
    _drop_broken(shop)
    resumed: set[str] = set()
    for job in shop.jobs.matching(CONVERTING):
        reset = shop.jobs.transition(job.id, expect={CONVERTING}, status=RECEIVED, message=preparing(), failure_stage=None)
        if reset is not None:
            resumed.add(reset.id)
            shop.converter.enqueue(reset.id)
    for job in shop.jobs.matching(RECEIVED):
        if job.id not in resumed:
            shop.converter.enqueue(job.id)
    for job in shop.jobs.matching(PRINTING):
        _recover_print(shop, job)


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


def _recover_print(shop: Shop, job: Job) -> None:
    if not job.cups_job_id:
        _settle(shop, job.id, "failed", "missing")
        return
    outcome = shop.cups.classify(job.cups_job_id)
    if outcome == "completed":
        _settle(shop, job.id, "done", outcome)
        return
    if outcome in {"aborted", "missing"}:
        _settle(shop, job.id, "failed", outcome)
        return
    shop.watch.follow(job.id)


def _settle(shop: Shop, job_id: str, decision: str, outcome: str) -> None:
    settle(shop.jobs, shop.events, shop.jobs.clock, shop.settings, job_id, decision, outcome)
