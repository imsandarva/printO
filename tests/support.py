"""Shared fixtures. CUPS is a stand-in, so tests never touch the real printer."""

import io
import threading
from contextlib import contextmanager
from dataclasses import replace

from PIL import Image
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from printo.config import default_settings
from printo.http.app import create_app
from printo.logging_setup import setup_logging
from printo.printing.cups import PrinterStatus
from printo.wiring import build_context

_SUMMARIES = {
    "ready": "The printer is ready.",
    "busy": "The printer is working right now.",
    "off": "The printer is turned off or unplugged.",
    "missing": "The printer isn't set up on this computer.",
    "down": "The printer service isn't responding. The file is still here.",
}


class FakeCups:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = "ready"
        self.jobs: dict[str, str] = {}
        self.submitted: list[tuple[str, str, str]] = []
        self.cancelled: list[str] = []
        self.hold = False

    def status(self) -> PrinterStatus:
        with self._lock:
            state = self.state
        return PrinterStatus("MF3010", state, _SUMMARIES[state])

    def submit(self, pdf, title: str) -> str:
        with self._lock:
            job_id = f"MF3010-{len(self.submitted) + 1}"
            self.submitted.append((str(pdf), title, job_id))
            self.jobs[job_id] = "active" if self.hold else "completed"
            return job_id

    def classify(self, job_id: str) -> str:
        with self._lock:
            return self.jobs.get(job_id, "missing")

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            self.cancelled.append(job_id)
            self.jobs[job_id] = "aborted"
            return True


def jpeg_bytes(color: str = "red") -> bytes:
    image = Image.new("RGB", (80, 40), color)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


def pdf_bytes(widths: tuple[int, ...] = (200, 300, 400)) -> bytes:
    writer = PdfWriter()
    for width in widths:
        writer.add_blank_page(width=width, height=800)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@contextmanager
def running(tmp_path, cups: FakeCups | None = None, client_host: str = "127.0.0.1", **overrides):
    cups = cups or FakeCups()
    values = dict(
        print_poll_seconds=0.05, print_missing_grace_seconds=0.2, print_give_up_seconds=30,
    )
    values.update(overrides)
    settings = replace(default_settings(tmp_path / "data"), **values)
    setup_logging(settings)
    ctx = build_context(settings, cups=cups)
    with TestClient(create_app(ctx), client=(client_host, 50000)) as client:
        yield client, ctx, cups
