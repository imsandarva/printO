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


def test_old_finished_files_go_and_a_live_print_stays(tmp_path):
    clock = ManualClock()
    ctx = build_context(default_settings(tmp_path / "data"), cups=FakeCups(), clock=clock)
    try:
        past = stamp(clock.now() - timedelta(hours=5))
        future = stamp(clock.now() + timedelta(hours=10))
        old = _job(ctx, "a" * 32, "old.pdf", "done", past)
        fresh = _job(ctx, "b" * 32, "fresh.pdf", "ready", future)
        live = _job(ctx, "c" * 32, "live.pdf", "printing", past)
        ctx.cleanup.sweep()
        assert ctx.jobs.get(old) is None
        assert ctx.jobs.get(fresh) is not None
        assert ctx.jobs.get(live) is not None
        assert not ctx.files.job_dir(old).exists()
    finally:
        ctx.db.close()


def _job(ctx, job_id: str, name: str, status: str, delete_after: str) -> str:
    ctx.jobs.insert_received(job_id, name, "pdf", ".pdf", 10)
    ctx.jobs.transition(
        job_id, expect={"received"}, status=status, message="Kept for the test.", delete_after=delete_after, page_count=1,
    )
    return job_id
