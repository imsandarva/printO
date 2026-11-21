"""Mark a print finished. Only one caller can win, because the row has to still say printing."""

import logging

from printo.clock import Clock, after
from printo.config import Settings
from printo.domain.job import Job
from printo.domain.status import DONE, FAILED, PRINTING, STAGE_PRINT
from printo.messages import failure_after_wait, sent
from printo.services.events import Events
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.print")


def settle(jobs: JobStore, events: Events, clock: Clock, settings: Settings, job_id: str, decision: str, outcome: str) -> Job | None:
    if decision == "done":
        status, stage, message, hours = DONE, None, sent(), settings.printed_keep_hours
    else:
        status, stage, message, hours = FAILED, STAGE_PRINT, failure_after_wait(outcome), settings.unprinted_keep_hours
    job = jobs.transition(
        job_id, expect={PRINTING}, status=status, failure_stage=stage, message=message, delete_after=after(clock, hours),
    )
    if job is None:
        return None
    log.info("%s is %s", job.public_code, status)
    events.publish_job(job)
    return job
