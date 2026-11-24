"""One SQLite file. WAL plus synchronous=FULL survives a power cut without a second database."""

import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("printo.db")

# One table is enough: the file on disk is the document, and this row is only its state.
# Version 2 only added visit columns this build does not read. They stay. Version 3 drops the spoken code.
_KNOWN = 3
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        original_name TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('pdf', 'image', 'office')),
        source_ext TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('received', 'converting', 'ready', 'printing', 'done', 'failed')),
        failure_stage TEXT CHECK (failure_stage IS NULL OR failure_stage IN ('convert', 'print')),
        message TEXT NOT NULL,
        byte_size INTEGER NOT NULL CHECK (byte_size > 0),
        page_count INTEGER CHECK (page_count IS NULL OR page_count > 0),
        pages_spec TEXT,
        copies INTEGER CHECK (copies IS NULL OR copies > 0),
        cups_job_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        delete_after TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_delete_after ON jobs(delete_after)",
)


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()
        self._require_intact()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        # BEGIN IMMEDIATE takes the write lock before we read-and-update a job, so two clicks can't both print it.
        with self._lock:
            conn = self._require()
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                self._rollback(conn)
                raise
            else:
                try:
                    conn.execute("COMMIT")
                except sqlite3.Error:
                    self._rollback(conn)
                    raise

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._require().execute(sql, params))

    def close(self) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.close()
            self._conn = None

    def _migrate(self) -> None:
        conn = self._require()
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > _KNOWN:
            raise SystemExit("printO's saved queue is from a newer version, so it stopped rather than risk those files.")
        for statement in _SCHEMA:
            conn.execute(statement)
        _drop_code(conn)
        if version < _KNOWN:
            conn.execute(f"PRAGMA user_version = {_KNOWN}")

    def _require_intact(self) -> None:
        row = self._require().execute("PRAGMA quick_check").fetchone()
        if row is None or row[0] != "ok":
            raise SystemExit("printO's saved queue looks damaged, so it stopped rather than risk losing files.")

    def _require(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("database is closed")
        return self._conn

    def _rollback(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            log.exception("rollback failed")


# SQLite will not drop a UNIQUE column in place, so an older queue is copied without that column.
_CORE = (
    "id", "original_name", "kind", "source_ext", "status", "failure_stage", "message", "byte_size",
    "page_count", "pages_spec", "copies", "cups_job_id", "created_at", "updated_at", "delete_after",
)


def _drop_code(conn: sqlite3.Connection) -> None:
    info = list(conn.execute("PRAGMA table_info(jobs)"))
    if not any(row[1] == "public_code" for row in info):
        return
    kept = [row[1] for row in info if row[1] != "public_code"]
    listed = ", ".join(_ident(name) for name in kept)
    conn.execute("BEGIN")
    try:
        conn.execute("DROP TABLE IF EXISTS jobs_next")
        conn.execute(_SCHEMA[0].replace("CREATE TABLE IF NOT EXISTS jobs", "CREATE TABLE jobs_next", 1))
        for row in info:
            if row[1] in _CORE or row[1] == "public_code":
                continue
            conn.execute(f"ALTER TABLE jobs_next ADD COLUMN {_ident(row[1])} {_extra(row)}")
        conn.execute(f"INSERT INTO jobs_next ({listed}) SELECT {listed} FROM jobs")
        conn.execute("DROP TABLE jobs")
        conn.execute("ALTER TABLE jobs_next RENAME TO jobs")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_delete_after ON jobs(delete_after)")
        if "visit_token" in kept:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_visit ON jobs(visit_token)")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _extra(row: sqlite3.Row) -> str:
    parts = [row[2] or "TEXT"]
    if row[3]:
        parts.append("NOT NULL")
    if row[4] is not None:
        parts.append(f"DEFAULT {row[4]}")
    return " ".join(parts)
