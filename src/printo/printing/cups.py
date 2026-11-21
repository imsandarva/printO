"""Talk to the printer the laptop already has. CUPS owns the Canon driver; we only submit a PDF."""

import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from printo.errors import UserError
from printo.messages import printer_busy, printer_down, printer_missing, printer_off, printer_off_action, printer_ready, rejected

log = logging.getLogger("printo.print")
_REQUEST = re.compile(r"request id is (\S+)")
_BAD_ALERT = ("abort", "cancel", "stop-point", "error", "failed")


@dataclass(frozen=True, slots=True)
class CommandResult:
    code: int
    out: str
    err: str


@dataclass(frozen=True, slots=True)
class PrinterStatus:
    name: str
    state: str
    summary: str


class PrinterPort(Protocol):
    def status(self) -> PrinterStatus: ...
    def submit(self, pdf: Path, title: str) -> str: ...
    def classify(self, job_id: str) -> str: ...
    def cancel(self, job_id: str) -> bool: ...


def run_command(args: list[str], timeout: float) -> CommandResult:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    return CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def refuse_reason(status: PrinterStatus) -> str | None:
    if status.state in {"ready", "busy"}:
        return None
    if status.state == "off":
        return printer_off_action()
    if status.state == "missing":
        return printer_missing()
    return printer_down()


def parse_printer(text: str, err: str, code: int) -> tuple[str, str]:
    if code != 0:
        blob = f"{text}\n{err}".lower()
        if "unknown" in blob or "invalid destination" in blob:
            return "missing", printer_missing()
        return "down", printer_down()
    first = next((line.strip().lower() for line in text.splitlines() if line.strip()), "")
    body = text.lower()
    if "disabled" in first or "unplugged" in body or "turned off" in body:
        return "off", printer_off()
    if "now printing" in first or first.startswith("printer ") and "processing" in first:
        return "busy", printer_busy()
    if "is idle" in first or "enabled" in first:
        return "ready", printer_ready()
    return "down", printer_down()


def parse_job_alerts(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    current: str | None = None
    alerts: list[str] = []

    def flush() -> None:
        nonlocal current, alerts
        if current:
            found[current] = " ".join(alerts)
        current, alerts = None, []

    for raw in text.splitlines():
        if not raw.strip():
            continue
        if raw[:1].isspace():
            piece = raw.strip()
            if piece.lower().startswith("alerts:"):
                alerts.append(piece.split(":", 1)[1].strip())
            continue
        flush()
        current = raw.split()[0]
        alerts = []
    flush()
    return found


def job_outcome(active_text: str, done_text: str, job_id: str) -> str:
    # Match the whole id. ``MF3010-1`` must not count as ``MF3010-15``.
    if job_id in parse_job_alerts(active_text):
        return "active"
    done = parse_job_alerts(done_text)
    if job_id not in done:
        return "missing"
    alerts = done[job_id].lower()
    if any(word in alerts for word in _BAD_ALERT):
        return "aborted"
    return "completed"


class Cups:
    def __init__(self, printer: str, runner: Callable[[list[str], float], CommandResult] | None = None) -> None:
        self.printer = printer
        self._run = runner or run_command

    def status(self) -> PrinterStatus:
        if shutil.which("lpstat") is None:
            return PrinterStatus(self.printer, "down", printer_down())
        try:
            result = self._run(["lpstat", "-p", self.printer], 8)
        except (OSError, subprocess.TimeoutExpired):
            log.exception("could not ask the printer how it is")
            return PrinterStatus(self.printer, "down", printer_down())
        state, summary = parse_printer(result.out, result.err, result.code)
        return PrinterStatus(self.printer, state, summary)

    def submit(self, pdf: Path, title: str) -> str:
        # Copies are already repeated in the PDF, so CUPS is asked for one copy. See compose.py.
        result = self._run(["lp", "-d", self.printer, "-n", "1", "-o", "media=A4", "-t", title, str(pdf)], 30)
        match = _REQUEST.search(result.out) or _REQUEST.search(result.err)
        if result.code != 0 or match is None:
            log.warning("printer refused the file (%s): %s", result.code, (result.err or result.out)[-400:])
            raise UserError(rejected())
        return match.group(1)

    def classify(self, job_id: str) -> str:
        try:
            active = self._run(["lpstat", "-W", "not-completed", "-l", "-o", self.printer], 8)
            done = self._run(["lpstat", "-W", "completed", "-l", "-o", self.printer], 8)
        except (OSError, subprocess.TimeoutExpired):
            log.exception("could not read the printer queue")
            return "unknown"
        if active.code != 0:
            return "unknown"
        if done.code != 0:
            return "active" if job_id in parse_job_alerts(active.out) else "unknown"
        return job_outcome(active.out, done.out, job_id)

    def cancel(self, job_id: str) -> bool:
        if not _looks_like_cups_id(job_id):
            return False
        try:
            result = self._run(["cancel", job_id], 8)
        except (OSError, subprocess.TimeoutExpired):
            log.exception("could not cancel %s", job_id)
            return False
        if result.code != 0:
            log.warning("cancel %s failed: %s", job_id, (result.err or result.out)[-300:])
        return result.code == 0


def _looks_like_cups_id(job_id: str) -> bool:
    # CUPS ids look like ``QueueName-42``. Reject anything that could be read as a flag or a path.
    if not job_id or job_id.startswith("-") or any(ch in job_id for ch in " /\\\n\r\t"):
        return False
    queue, sep, number = job_id.rpartition("-")
    return bool(sep) and bool(queue) and number.isdigit()
