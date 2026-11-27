"""Job states. A job only moves forward through an explicit transition in the store."""

RECEIVED, CONVERTING, READY = "received", "converting", "ready"
WAITING, PRINTING, STOPPING, STOPPED, DONE, FAILED = "waiting", "printing", "stopping", "stopped", "done", "failed"
STAGE_CONVERT, STAGE_PRINT = "convert", "print"
ALL = frozenset({RECEIVED, CONVERTING, READY, WAITING, PRINTING, STOPPING, STOPPED, DONE, FAILED})

LABELS = {
    RECEIVED: "Just arrived",
    CONVERTING: "Getting it ready",
    READY: "Ready to print",
    WAITING: "Waiting to print",
    PRINTING: "Printing",
    STOPPING: "Stopping after this page",
    STOPPED: "Stopped",
    DONE: "Sent to the printer",
    FAILED: "Needs attention",
}


def label_for(status: str) -> str:
    return LABELS.get(status, "Needs attention")


def can_print(job: object) -> bool:
    """Ready work, a finished job (print it again), or a print that failed after a PDF existed."""
    page_count = getattr(job, "page_count", None)
    status, stage = getattr(job, "status", ""), getattr(job, "failure_stage", None)
    if not page_count:
        return False
    if status in {READY, DONE}:
        return True
    return status == FAILED and stage == STAGE_PRINT


def can_retry(job: object) -> bool:
    """The original file is still here, but turning it into a PDF failed."""
    return getattr(job, "status", "") == FAILED and getattr(job, "failure_stage", None) == STAGE_CONVERT


def can_continue(job: object) -> bool:
    return getattr(job, "status", "") == STOPPED and bool(getattr(job, "print_total", 0))
