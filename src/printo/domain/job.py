"""A job is one uploaded file and where it is in the queue. The bytes live on disk, not in this object."""

import re
from dataclasses import dataclass

ID_RE = re.compile(r"^[a-f0-9]{32}$")


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    original_name: str
    kind: str
    source_ext: str
    status: str
    failure_stage: str | None
    message: str
    byte_size: int
    page_count: int | None
    pages_spec: str | None
    copies: int | None
    cups_job_id: str | None
    created_at: str
    updated_at: str
    # Left from when files were removed on a timer. Always cleared. Never used to delete a file.
    delete_after: str | None
    # Set while the file sits in Trash. The bytes stay until it is deleted from there.
    trashed_at: str | None


def display_name(raw: str | None) -> str:
    """Keep a name that is safe to show and to put in a download header. Never use it as a path."""
    base = (raw or "").replace("\\", "/").split("/")[-1].replace("\x00", "")
    cleaned = "".join(ch for ch in base if ch.isprintable()).strip()[:120]
    return cleaned or "Untitled"
