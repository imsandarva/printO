import pytest

from printo.clock import SystemClock
from printo.config import load_settings
from printo.domain.status import PRINTING, READY
from printo.storage.database import Database
from printo.storage.jobs import JobStore


def test_second_transition_loses(tmp_path):
    store = JobStore(Database(tmp_path / "printo.db"), SystemClock())
    job = store.insert_received("a" * 32, "../../नागरिकता.pdf", "pdf", ".pdf", 12)
    assert job.original_name == "नागरिकता.pdf"
    assert job.public_code.isalnum() and len(job.public_code) == 4
    first = store.transition(job.id, expect={job.status}, status=READY, page_count=2, message="Ready to print.")
    second = store.transition(job.id, expect={job.status}, status=PRINTING, message="Printing.")
    assert first is not None and first.status == READY and first.page_count == 2
    assert second is None
    assert store.get(job.id).status == READY
    store.db.close()


def test_settings_reject_a_bad_printer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRINTO_PRINTER", "not a printer")
    with pytest.raises(SystemExit) as caught:
        load_settings([])
    assert "printer" in str(caught.value)


def test_env_overrides_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "printo.toml").write_text('port = 9000\nprinter = "MF3010"\n')
    monkeypatch.setenv("PRINTO_PORT", "9001")
    settings = load_settings([])
    assert settings.port == 9001
    assert settings.printer == "MF3010"
