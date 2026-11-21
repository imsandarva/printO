"""Word and similar documents go through LibreOffice, one at a time, then the process exits.

LibreOffice often exits 0 even when it wrote nothing, and it locks its profile. We give it a private
profile, kill the whole process group on timeout, and only believe an output file that is a real PDF.
"""

import logging
import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from urllib.request import pathname2url

from printo.convert.pdf_doc import Prepared, page_count
from printo.errors import UserError
from printo.messages import office_failed, office_missing, office_timeout
from printo.storage.atomic import replace

log = logging.getLogger("printo.convert")


class Office:
    def __init__(self, binary: str, timeout: int) -> None:
        self.binary = binary
        self.timeout = timeout
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None

    def convert(self, source: Path, dest: Path, profile: Path) -> Prepared:
        if shutil.which(self.binary) is None and not Path(self.binary).is_file():
            raise UserError(office_missing())
        profile.mkdir(parents=True, exist_ok=True)
        self._clear_locks(profile)
        produced = source.with_suffix(".pdf")
        if produced.exists():
            produced.unlink()
        command = [
            self.binary, "--headless", "--nologo", "--nofirststartwizard", "--norestore", "--nolockcheck",
            f"-env:UserInstallation=file://{pathname2url(str(profile.resolve()))}",
            "--convert-to", "pdf", "--outdir", str(source.parent), str(source),
        ]
        try:
            code, err = self._run(command, profile)
        except subprocess.TimeoutExpired:
            raise UserError(office_timeout()) from None
        if not produced.is_file() or produced.stat().st_size == 0:
            log.warning("libreoffice wrote nothing (exit %s): %s", code, err[-400:])
            raise UserError(office_failed())
        try:
            prepared = Prepared(page_count(produced))
        except UserError:
            produced.unlink(missing_ok=True)
            raise UserError(office_failed()) from None
        if produced.resolve() != dest.resolve():
            replace(produced, dest)
        return prepared

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            _kill(proc)

    def _run(self, command: list[str], workdir: Path) -> tuple[int, str]:
        # HOME stays the shop account so fonts installed for that person (Nepali, for one) still apply.
        proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, cwd=str(workdir),
        )
        with self._lock:
            self._proc = proc
        try:
            out, err = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            _kill(proc)
            proc.communicate()
            raise
        finally:
            with self._lock:
                if self._proc is proc:
                    self._proc = None
        return proc.returncode, (err or out or b"").decode("utf-8", "replace")

    def _clear_locks(self, profile: Path) -> None:
        for lock in profile.glob("**/.lock"):
            lock.unlink(missing_ok=True)
        for lock in profile.glob("**/*.lock"):
            lock.unlink(missing_ok=True)


def _kill(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()
