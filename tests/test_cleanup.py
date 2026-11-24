"""Sent files stay. An old removal time, from a build that deleted on a timer, is forgotten and the file is kept."""

from datetime import datetime, timedelta, timezone

from printo.clock import stamp
from printo.config import default_settings
from printo.wiring import build_context
from tests.support import FakeCups


class ManualClock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.moment


def test_files_stay_and_old_removal_times_are_forgotten(tmp_path):
    clock = ManualClock()
    ctx = build_context(default_settings(tmp_path / "data"), cups=FakeCups(), clock=clock)
    try:
        past = stamp(clock.now() - timedelta(days=30))
        job_id = _job(ctx, "a" * 32, "old.pdf", "done", past)
        folder = ctx.files.job_dir(job_id)
        folder.mkdir(parents=True)
        (folder / "document.pdf").write_bytes(b"%PDF")
        assert ctx.jobs.get(job_id) is not None
        assert not hasattr(ctx, "cleanup")
    finally:
        ctx.db.close()
    again = build_context(default_settings(tmp_path / "data"), cups=FakeCups(), clock=clock)
    try:
        job = again.jobs.get("a" * 32)
        assert job is not None and job.delete_after is None and job.original_name == "old.pdf"
        assert (again.files.job_dir("a" * 32) / "document.pdf").read_bytes() == b"%PDF"
    finally:
        again.db.close()


def _job(ctx, job_id: str, name: str, status: str, delete_after: str) -> str:
    ctx.jobs.insert_received(job_id, name, "pdf", ".pdf", 10)
    ctx.jobs.transition(
        job_id, expect={"received"}, status=status, message="Kept for the test.", delete_after=delete_after, page_count=1,
    )
    return job_id
