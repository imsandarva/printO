"""Files live under the data directory. Job ids are random, so a phone can never choose a path."""

import json
import re
import shutil
import uuid
from pathlib import Path

from printo.domain.job import ID_RE, Job

# A picture revision is a short hex token, or size and time joined by one dash. Never a path.
_REVISION = re.compile(r"^[0-9a-f]{1,32}(?:-[0-9a-f]{1,32})?$")
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

    def preview_root(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "previews"

    def preview_image(self, job_id: str, revision: str, page: int) -> Path:
        # The revision and the page are part of the path, so both are checked before joining.
        if isinstance(page, bool) or not isinstance(page, int) or page < 1 or page > 4000 or not _REVISION.fullmatch(revision or ""):
            raise ValueError("unsafe preview")
        root = self.preview_root(job_id).resolve()
        folder = (root / revision).resolve()
        path = (folder / f"{page:04d}.jpg").resolve()
        if folder.parent != root or path.parent != folder:
            raise ValueError("unsafe preview")
        return path

    def pair_meta(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "pair.json"

    def pair_piece(self, job_id: str, index: int) -> Path:
        return self.job_dir(job_id) / f"piece-{index}.pdf"

    def image_meta(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "rotation.json"

    def to_print(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "to-print.pdf"

    def print_pages(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "print-pages"

    def print_page(self, job_id: str, source_index: int) -> Path:
        if source_index < 0:
            raise ValueError("unsafe page index")
        return self.print_pages(job_id) / f"page-{source_index + 1:04d}.pdf"

    def sheet_count(self, job_id: str) -> int | None:
        """How many landscape sheets this run feeds, or nothing when each file is one page."""
        path = self.print_pages(job_id) / "plan.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        count = payload.get("sheets") if isinstance(payload, dict) else None
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            return None
        return count

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

    def _unlink(self, paths: object) -> None:
        for path in paths:  # type: ignore[union-attr]
            path.unlink(missing_ok=True)
