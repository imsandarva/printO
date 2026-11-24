"""Mark a print finished. Only one caller can win, because the row has to still say printing."""

import logging

from printo.domain.job import Job
from printo.domain.status import DONE, FAILED, PRINTING, STAGE_PRINT
from printo.messages import failure_after_wait, sent
from printo.services.events import Events
from printo.storage.jobs import JobStore

log = logging.getLogger("printo.print")


def settle(jobs: JobStore, events: Events, job_id: str, decision: str, outcome: str) -> Job | None:
    if decision == "done":
        status, stage, message = DONE, None, sent()
    else:
        status, stage, message = FAILED, STAGE_PRINT, failure_after_wait(outcome)
    job = jobs.transition(job_id, expect={PRINTING}, status=status, failure_stage=stage, message=message, delete_after=None)
    if job is None:
        return None
    log.info("%s is %s", job.original_name, status)
    events.publish_job(job)
    return job
