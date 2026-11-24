from fastapi.testclient import TestClient

from printo.config import default_settings
from printo.http.app import create_app
from printo.logging_setup import setup_logging
from printo.wiring import build_context
from tests.support import FakeCups, jpeg_bytes
from tests.test_api import _wait


def test_startup_repairs_a_half_finished_queue(tmp_path):
    cups = FakeCups()
    cups.jobs["MF3010-9"] = "completed"
    settings = default_settings(tmp_path / "data")
    setup_logging(settings)
    ctx = build_context(settings, cups=cups)
    photo = "b" * 32
    ctx.files.source(photo, ".jpg").parent.mkdir(parents=True)
    ctx.files.source(photo, ".jpg").write_bytes(jpeg_bytes())
    ctx.jobs.insert_received(photo, "photo.jpg", "image", ".jpg", 20)
    ctx.jobs.transition(photo, expect={"received"}, status="converting", message="Getting it ready.")
    sent = "c" * 32
    ctx.files.source(sent, ".pdf").parent.mkdir(parents=True)
    ctx.files.source(sent, ".pdf").write_bytes(b"%PDF-1.4")
    ctx.jobs.insert_received(sent, "sent.pdf", "pdf", ".pdf", 10)
    ctx.jobs.transition(sent, expect={"received"}, status="printing", message="Printing.", cups_job_id="MF3010-9", page_count=1)
    lost = "d" * 32
    ctx.files.source(lost, ".pdf").parent.mkdir(parents=True)
    ctx.files.source(lost, ".pdf").write_bytes(b"%PDF-1.4")
    ctx.jobs.insert_received(lost, "lost.pdf", "pdf", ".pdf", 10)
    ctx.jobs.transition(lost, expect={"received"}, status="printing", message="Printing.", page_count=1)
    ctx.jobs.insert_received("e" * 32, "gone.pdf", "pdf", ".pdf", 10)
    (ctx.files.jobs / "not-a-job").mkdir()
    (ctx.files.partials / "left.partial").write_bytes(b"partial")
    with TestClient(create_app(ctx), client=("127.0.0.1", 50000)) as client:
        jobs = {job["name"]: job for job in client.get("/admin/jobs").json()["jobs"]}
        assert "gone.pdf" not in jobs
        assert jobs["sent.pdf"]["status"] == "done"
        assert "interrupted" in jobs["lost.pdf"]["message"]
        assert not (ctx.files.jobs / "not-a-job").exists()
        assert not (ctx.files.partials / "left.partial").exists()
        ready = _wait(client, "photo.jpg", {"ready", "failed"}, seconds=5)
        assert ready["status"] == "ready"
