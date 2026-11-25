"""Non-destructive rotation service for single images and Citizenship sheets."""

import json
import threading
from pathlib import Path

from printo.convert.images import rotate_image
from printo.domain.job import Job
from printo.domain.kinds import IMAGE
from printo.domain.rotate import parse_angle
from printo.domain.status import PRINTING, can_print
from printo.errors import UserError
from printo.messages import already_printing, in_trash, not_found, not_ready, present, validation
from printo.printing.pair import recompose_pair
from printo.storage.atomic import replace
from printo.storage.files import Files
from printo.storage.jobs import JobStore


class RotationService:
    def __init__(self, jobs: JobStore, files: Files) -> None:
        self.jobs = jobs
        self.files = files
        self._lock = threading.Lock()

    def meta(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise UserError(not_found(), 404)
        with self._lock:
            pair = _read_json(self.files.pair_meta(job_id))
            image = _read_json(self.files.image_meta(job_id))
        angle = int(image.get("angle", 0)) if image else 0
        return {"pair": pair, "angle": angle}

    def rotate(self, job_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise UserError(validation())
        target = payload.get("target")
        with self._lock:
            job = self._ready(job_id)
            if target == "pair":
                pair = self._rotate_pair_piece(job, payload)
                return {"job": present(job), "pair": pair}
            if target == "sheet":
                pair = self._rotate_pair_sheet(job, payload)
                return {"job": present(job), "pair": pair}
            if target == "image":
                angle = self._rotate_single_image(job, payload)
                return {"job": present(job), "angle": angle}
        raise UserError(validation())

    def _ready(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise UserError(not_found(), 404)
        if job.trashed_at:
            raise UserError(in_trash(), 409)
        if job.status == PRINTING:
            raise UserError(already_printing(), 409)
        if not can_print(job) or not self.files.document(job.id).is_file():
            raise UserError(not_ready(), 409)
        return job

    def _rotate_pair_piece(self, job: Job, payload: dict) -> dict:
        index = payload.get("index")
        if isinstance(index, bool) or index not in (0, 1):
            raise UserError(validation())
        meta = self._require_pair(job.id)
        rotations = list(meta.get("rotations") or [0, 0])
        sheet = int(meta.get("sheet", 0))
        rotations[index] = _next_angle(rotations[index], payload.get("angle"))
        return self._rebuild_pair(job.id, (rotations[0], rotations[1]), sheet)

    def _rotate_pair_sheet(self, job: Job, payload: dict) -> dict:
        meta = self._require_pair(job.id)
        rotations = list(meta.get("rotations") or [0, 0])
        sheet = _next_angle(int(meta.get("sheet", 0)), payload.get("angle"))
        return self._rebuild_pair(job.id, (rotations[0], rotations[1]), sheet)

    def _require_pair(self, job_id: str) -> dict:
        meta = _read_json(self.files.pair_meta(job_id))
        if meta is None or not self.files.pair_piece(job_id, 0).is_file() or not self.files.pair_piece(job_id, 1).is_file():
            raise UserError(validation())
        return meta

    def _rebuild_pair(self, job_id: str, rotations: tuple[int, int], sheet: int) -> dict:
        partial = self.files.new_partial()
        try:
            boxes = recompose_pair(self.files.job_dir(job_id), partial, rotations=rotations, sheet_rotation=sheet)
            replace(partial, self.files.document(job_id))
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        updated = {"rotations": [rotations[0], rotations[1]], "sheet": sheet, "boxes": boxes}
        _write_json(self.files.pair_meta(job_id), updated)
        return updated

    def _rotate_single_image(self, job: Job, payload: dict) -> int:
        if job.kind != IMAGE or job.page_count != 1 or not self.files.source_exists(job):
            raise UserError(validation())
        meta = _read_json(self.files.image_meta(job.id))
        current = int(meta.get("angle", 0)) if meta else 0
        angle = _next_angle(current, payload.get("angle"))
        rotate_image(self.files.source(job.id, job.source_ext), self.files.document(job.id), angle)
        _write_json(self.files.image_meta(job.id), {"angle": angle})
        return angle


def _next_angle(current: int, raw: object) -> int:
    if raw is None:
        return (current + 90) % 360
    return parse_angle(raw)


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(path.name + ".partial")
    try:
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
