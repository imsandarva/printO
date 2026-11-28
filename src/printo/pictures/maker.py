"""Make each page's picture once, and keep it until the file itself is deleted.

Page 1 of a file that just arrived goes before the leftover pages of an older one.
A photo or a Citizenship sheet is pictured again before the answer goes back,
because that answer is the moment the counter shows the new sheet.
"""

import logging
import shutil
import threading
from collections import deque
from pathlib import Path

import fitz

from printo.errors import UserError
from printo.messages import not_found
from printo.pictures.raster import BLANK_JPEG, jpeg_page, open_pdf
from printo.storage.atomic import replace
from printo.storage.files import Files

log = logging.getLogger("printo.pictures")


class PictureMaker:
    def __init__(self, files: Files) -> None:
        self.files = files
        self._render = threading.Lock()
        self._gate = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._front: deque[str] = deque()
        self._back: deque[str] = deque()
        self._queued: set[str] = set()
        self._active: str | None = None
        self._thread: threading.Thread | None = None
        self._doc: fitz.Document | None = None
        self._doc_key: tuple[str, str] | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="printo-pictures", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)
        self._thread = None
        self._close_doc()

    def schedule(self, job_id: str) -> None:
        """Ask for page 1 first. Ignored when this file is already in line or being pictured."""
        with self._gate:
            if job_id in self._queued or job_id == self._active:
                return
            self._front.append(job_id)
            self._queued.add(job_id)
        self._wake.set()

    def status(self, job_id: str, page_count: int) -> dict:
        total = page_count if isinstance(page_count, int) and page_count > 0 else 0
        path = self.files.document(job_id)
        if total < 1 or not path.is_file():
            raise UserError(not_found(), 404)
        revision = _revision(path)
        ready = _ready_count(self.files, job_id, revision, total)
        if ready < total:
            self.schedule(job_id)
        return {"total": total, "ready": ready, "revision": revision}

    def image(self, job_id: str, page: int, revision: str) -> Path:
        path = self.files.document(job_id)
        if not path.is_file() or _revision(path) != revision:
            raise UserError(not_found(), 404)
        try:
            picture = self.files.preview_image(job_id, revision, page)
        except ValueError:
            raise UserError(not_found(), 404) from None
        if not picture.is_file():
            self.schedule(job_id)
            raise UserError(not_found(), 404)
        return picture

    def refresh(self, job_id: str) -> dict:
        """Picture every page before returning. Used when the sheet itself was just rebuilt."""
        with self._render:
            try:
                made = self._complete(job_id)
            except Exception:
                log.exception("could not refresh %s", job_id)
                made = None
        if made is not None:
            return made
        path = self.files.document(job_id)
        if not path.is_file():
            raise UserError(not_found(), 404)
        self.schedule(job_id)
        return {"total": 1, "ready": 0, "revision": _revision(path)}

    def _loop(self) -> None:
        while not self._stop.is_set():
            taken = self._take()
            if taken is None:
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            job_id, only_first = taken
            try:
                with self._render:
                    if not self._stop.is_set():
                        self._step(job_id, only_first=only_first)
            except Exception:
                log.exception("could not picture %s", job_id)
            finally:
                with self._gate:
                    if self._active == job_id:
                        self._active = None

    def _take(self) -> tuple[str, bool] | None:
        with self._gate:
            front = bool(self._front)
            queue = self._front if front else self._back
            if not queue:
                return None
            job_id = queue.popleft()
            self._queued.discard(job_id)
            self._active = job_id
            return job_id, front

    def _again(self, job_id: str) -> None:
        # The file is still the active one, so schedule() would drop this. The rest of the pages still need a turn.
        with self._gate:
            if job_id in self._queued:
                return
            self._back.append(job_id)
            self._queued.add(job_id)
        self._wake.set()

    def _step(self, job_id: str, *, only_first: bool) -> None:
        path = self.files.document(job_id)
        if not path.is_file():
            return
        revision = _revision(path)
        doc = self._open(path, revision)
        total = doc.page_count
        if total < 1:
            return
        ready = _ready_count(self.files, job_id, revision, total)
        if ready >= total:
            self._close_doc()
            return
        if only_first and ready >= 1:
            self._again(job_id)
            return
        page = ready + 1
        if not self._write_page(path, job_id, revision, doc, page):
            self._close_doc()
            return
        if page == 1:
            _drop_other(self.files, job_id, revision)
        if page < total:
            self._again(job_id)
        else:
            self._close_doc()
            log.info("pictured %s (%s pages)", job_id, total)

    def _complete(self, job_id: str) -> dict | None:
        path = self.files.document(job_id)
        if not path.is_file():
            return None
        revision = _revision(path)
        doc = self._open(path, revision)
        total = doc.page_count
        ready = _ready_count(self.files, job_id, revision, total)
        while ready < total and not self._stop.is_set():
            if not self._write_page(path, job_id, revision, doc, ready + 1):
                self._close_doc()
                break
            ready += 1
            if ready == 1:
                _drop_other(self.files, job_id, revision)
        if ready >= total:
            self._close_doc()
        return {"total": total, "ready": ready, "revision": revision}

    def _write_page(self, path: Path, job_id: str, revision: str, doc: fitz.Document, page: int) -> bool:
        # The file may have been replaced while this picture was waiting. Don't store it under the old name.
        if _revision(path) != revision:
            return False
        try:
            data = jpeg_page(doc, page)
        except Exception:
            log.exception("page %s of %s", page, job_id)
            data = BLANK_JPEG
        _store(self.files.preview_image(job_id, revision, page), data)
        return True

    def _open(self, path: Path, revision: str) -> fitz.Document:
        key = (str(path), revision)
        if self._doc is not None and self._doc_key == key:
            return self._doc
        self._close_doc()
        self._doc = open_pdf(path)
        self._doc_key = key
        return self._doc

    def _close_doc(self) -> None:
        if self._doc is not None:
            self._doc.close()
        self._doc = None
        self._doc_key = None


def _revision(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size:x}-{stat.st_mtime_ns:x}"


def _ready_count(files: Files, job_id: str, revision: str, total: int) -> int:
    ready = 0
    for page in range(1, total + 1):
        try:
            picture = files.preview_image(job_id, revision, page)
        except ValueError:
            break
        if not picture.is_file() or picture.stat().st_size < 1:
            break
        ready += 1
    return ready


def _store(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + ".partial")
    temporary.write_bytes(data)
    replace(temporary, dest)


def _drop_other(files: Files, job_id: str, revision: str) -> None:
    root = files.preview_root(job_id)
    if not root.is_dir():
        return
    for child in list(root.iterdir()):
        if child.name == revision:
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
