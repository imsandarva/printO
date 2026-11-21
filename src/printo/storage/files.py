"""Files live under the data directory. Job ids are random, so a phone can never choose a path."""

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from printo.domain.job import ID_RE, Job
from printo.domain.kinds import EXTENSIONS
from printo.storage.atomic import replace


class Files:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.jobs = root / "jobs"
        self.partials = root / "incoming"
        # LibreOffice gets this private profile so it never touches a person's own LibreOffice, and never shares a lock.
        self.profile = root / "lo-profile"
        self.logs = root / "logs"

    def ensure(self) -> None:
        for path in (self.root, self.jobs, self.partials, self.profile, self.logs):
            path.mkdir(parents=True, exist_ok=True)

    def new_partial(self) -> Path:
        self.partials.mkdir(parents=True, exist_ok=True)
        return self.partials / f"{uuid.uuid4().hex}.partial"

    def adopt(self, partial: Path, job_id: str, ext: str) -> Path:
        # incoming/ and jobs/ are on the same drive so this rename cannot tear the file in half.
        dest = self.source(job_id, ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        replace(partial, dest)
        return dest

    def source(self, job_id: str, ext: str) -> Path:
        return self.job_dir(job_id) / f"source{ext}"

    def source_exists(self, job: Job) -> bool:
        if job.source_ext not in EXTENSIONS:
            return False
        try:
            return self.source(job.id, job.source_ext).is_file()
        except ValueError:
            return False

    def document(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "document.pdf"

    def to_print(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "to-print.pdf"

    def job_dir(self, job_id: str) -> Path:
        if not ID_RE.fullmatch(job_id or ""):
            raise ValueError("unsafe job id")
        path = (self.jobs / job_id).resolve()
        if path.parent != self.jobs.resolve():
            raise ValueError("unsafe job path")
        return path

    def job_dirs(self) -> list[Path]:
        if not self.jobs.is_dir():
            return []
        return [path for path in self.jobs.iterdir() if path.is_dir()]

    def remove_job(self, job_id: str) -> None:
        try:
            directory = self.job_dir(job_id)
        except ValueError:
            return
        if directory.exists():
            shutil.rmtree(directory)

    def drop_partials(self) -> None:
        self._unlink(self.partials.glob("*.partial") if self.partials.exists() else [])
        self._unlink(self.jobs.glob("*/*partial") if self.jobs.exists() else [])

    def drop_old_partials(self, older_than: datetime) -> None:
        if not self.partials.exists():
            return
        for path in self.partials.glob("*.partial"):
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified < older_than:
                path.unlink(missing_ok=True)

    def _unlink(self, paths: object) -> None:
        for path in paths:  # type: ignore[union-attr]
            path.unlink(missing_ok=True)
