import sqlite3

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
    first = store.transition(job.id, expect={job.status}, status=READY, page_count=2, message="Ready to print.")
    second = store.transition(job.id, expect={job.status}, status=PRINTING, message="Printing.")
    assert first is not None and first.status == READY and first.page_count == 2
    assert second is None
    assert store.get(job.id).status == READY
    store.db.close()


def test_visit_columns_do_not_hide_the_queue(tmp_path):
    path = tmp_path / "printo.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 2")
    conn.execute(
        """CREATE TABLE jobs (
            id TEXT PRIMARY KEY, public_code TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL,
            kind TEXT NOT NULL, source_ext TEXT NOT NULL, status TEXT NOT NULL, failure_stage TEXT,
            message TEXT NOT NULL, byte_size INTEGER NOT NULL, page_count INTEGER, pages_spec TEXT,
            copies INTEGER, cups_job_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            delete_after TEXT, visit_token TEXT NOT NULL DEFAULT '', visit_code TEXT NOT NULL DEFAULT ''
        )"""
    )
    conn.execute(
        """INSERT INTO jobs (
            id, public_code, original_name, kind, source_ext, status, message, byte_size, created_at, updated_at, visit_token, visit_code
        ) VALUES (?, ?, ?, 'image', '.jpg', 'ready', 'Ready to print.', 12, ?, ?, ?, ?)""",
        ("b" * 32, "V8QR", "passport.jpg", "2026-11-21T10:03:04+00:00", "2026-11-21T10:03:04+00:00", "b" * 32, "V8QR"),
    )
    conn.commit()
    conn.close()
    store = JobStore(Database(path), SystemClock())
    found = store.all()
    assert len(found) == 1 and found[0].original_name == "passport.jpg"
    columns = {row[1] for row in store.db.query("PRAGMA table_info(jobs)")}
    assert "public_code" not in columns and "trashed_at" in columns
    assert store.db.query("PRAGMA user_version")[0][0] == 4
    store.db.close()


def test_an_existing_queue_gains_trash_without_losing_a_file(tmp_path):
    path = tmp_path / "printo.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 3")
    conn.execute(
        """CREATE TABLE jobs (
            id TEXT PRIMARY KEY, original_name TEXT NOT NULL, kind TEXT NOT NULL, source_ext TEXT NOT NULL,
            status TEXT NOT NULL, failure_stage TEXT, message TEXT NOT NULL, byte_size INTEGER NOT NULL,
            page_count INTEGER, pages_spec TEXT, copies INTEGER, cups_job_id TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, delete_after TEXT
        )"""
    )
    conn.execute(
        """INSERT INTO jobs (
            id, original_name, kind, source_ext, status, message, byte_size, created_at, updated_at
        ) VALUES (?, 'bill.pdf', 'pdf', '.pdf', 'ready', 'Ready to print.', 20, ?, ?)""",
        ("c" * 32, "2026-11-21T10:03:04+00:00", "2026-11-21T10:03:04+00:00"),
    )
    conn.commit()
    conn.close()
    store = JobStore(Database(path), SystemClock())
    found = store.all()
    assert len(found) == 1 and found[0].original_name == "bill.pdf" and found[0].trashed_at is None
    assert store.matching(placed="trash") == []
    assert store.db.query("PRAGMA user_version")[0][0] == 4
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
