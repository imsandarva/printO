"""Job states. A job only moves forward through an explicit transition in the store."""

RECEIVED, CONVERTING, READY = "received", "converting", "ready"
PRINTING, DONE, FAILED = "printing", "done", "failed"
STAGE_CONVERT, STAGE_PRINT = "convert", "print"
ALL = frozenset({RECEIVED, CONVERTING, READY, PRINTING, DONE, FAILED})

LABELS = {
    RECEIVED: "Just arrived",
    CONVERTING: "Getting it ready",
    READY: "Ready to print",
    PRINTING: "Printing",
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
