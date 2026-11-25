"""The queue. Status changes happen inside one write transaction, or they don't happen."""

import re
import sqlite3
from collections.abc import Iterable

from printo.clock import Clock, stamp
from printo.domain.job import ID_RE, Job, display_name
from printo.domain.kinds import KINDS
from printo.domain.status import ALL
from printo.errors import UserError
from printo.messages import arrived, ready, try_again, validation
from printo.storage.database import Database

# Chosen in the same write as the row, so two clicks cannot both take Citizenship_1.pdf.
_PAIR_NAME = re.compile(r"^Citizenship_(\d+)\.pdf$")

_FIELDS = frozenset({
    "message", "failure_stage", "page_count", "pages_spec", "copies", "cups_job_id", "delete_after",
})
class JobStore:
    def __init__(self, db: Database, clock: Clock) -> None:
        self.db = db
        self.clock = clock

    def insert_received(self, job_id: str, original_name: str, kind: str, source_ext: str, byte_size: int) -> Job:
        if kind not in KINDS or not ID_RE.fullmatch(job_id):
            raise UserError(try_again(), 503)
        for _ in range(8):
            try:
                return self._insert_once(job_id, original_name, kind, source_ext, byte_size)
            except sqlite3.IntegrityError:
                continue
        raise UserError(try_again(), 503)

    def insert_ready(self, job_id: str, kind: str, source_ext: str, byte_size: int, page_count: int) -> Job:
        if kind not in KINDS or source_ext not in {".pdf"} or not ID_RE.fullmatch(job_id) or byte_size < 1 or page_count < 1:
            raise UserError(try_again(), 503)
        moment = stamp(self.clock.now())
        with self.db.transaction() as conn:
            name = _next_pair_name(conn)
            conn.execute(
                """INSERT INTO jobs (
                    id, original_name, kind, source_ext, status, failure_stage, message,
                    byte_size, page_count, pages_spec, copies, cups_job_id, created_at, updated_at, delete_after
                ) VALUES (?, ?, ?, ?, 'ready', NULL, ?, ?, ?, NULL, NULL, NULL, ?, ?, NULL)""",
                (job_id, name, kind, source_ext, ready(), byte_size, page_count, moment, moment),
            )
            return _job(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def get(self, job_id: str) -> Job | None:
        if not ID_RE.fullmatch(job_id or ""):
            return None
        rows = self.db.query("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return _job(rows[0]) if rows else None

    def matching(self, status: str | None = None, *, placed: str = "counter") -> list[Job]:
        # counter hides Trash. trash is only Trash. all is both, so a restart can still see every file.
        if status is not None and status not in ALL:
            raise UserError(validation())
        if placed not in {"counter", "trash", "all"}:
            raise RuntimeError(f"unknown place: {placed}")
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if placed == "counter":
            clauses.append("trashed_at IS NULL")
        elif placed == "trash":
            clauses.append("trashed_at IS NOT NULL")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self.db.query(f"SELECT * FROM jobs{where} ORDER BY created_at DESC", tuple(params))
        return [_job(row) for row in rows]

    def all(self) -> list[Job]:
        return self.matching(None, placed="all")

    def place_in_trash(self, job_id: str) -> Job | None:
        return self._mark_trash(job_id, True)

    def restore(self, job_id: str) -> Job | None:
        return self._mark_trash(job_id, False)

    def transition(self, job_id: str, expect: Iterable[str], status: str, **fields: object) -> Job | None:
        if set(fields) - _FIELDS:
            raise RuntimeError(f"unknown job fields: {sorted(set(fields) - _FIELDS)}")
        if not ID_RE.fullmatch(job_id or "") or status not in ALL:
            return None
        expected = tuple(expect)
        if not expected or any(item not in ALL for item in expected):
            return None
        assignments = ["status = ?", "updated_at = ?"]
        values: list[object] = [status, stamp(self.clock.now())]
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(value)
        marks = ",".join("?" for _ in expected)
        values.extend([job_id, *expected])
        sql = f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ? AND status IN ({marks})"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, values)
            if cursor.rowcount != 1:
                return None
            return _job(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def _mark_trash(self, job_id: str, into: bool) -> Job | None:
        if not ID_RE.fullmatch(job_id or ""):
            return None
        moment = stamp(self.clock.now())
        with self.db.transaction() as conn:
            if into:
                cursor = conn.execute(
                    "UPDATE jobs SET trashed_at = ?, updated_at = ? WHERE id = ? AND trashed_at IS NULL",
                    (moment, moment, job_id),
                )
            else:
                cursor = conn.execute(
                    "UPDATE jobs SET trashed_at = NULL, updated_at = ? WHERE id = ? AND trashed_at IS NOT NULL",
                    (moment, job_id),
                )
            if cursor.rowcount != 1:
                return None
            return _job(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def delete(self, job_id: str) -> bool:
        if not ID_RE.fullmatch(job_id or ""):
            return False
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            return cursor.rowcount == 1

    def _insert_once(self, job_id: str, original_name: str, kind: str, source_ext: str, byte_size: int) -> Job:
        moment = stamp(self.clock.now())
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO jobs (
                    id, original_name, kind, source_ext, status, failure_stage, message,
                    byte_size, page_count, pages_spec, copies, cups_job_id, created_at, updated_at, delete_after
                ) VALUES (?, ?, ?, ?, 'received', NULL, ?, ?, NULL, NULL, NULL, NULL, ?, ?, NULL)""",
                (job_id, display_name(original_name), kind, source_ext, arrived(), byte_size, moment, moment),
            )
            return _job(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())


def _next_pair_name(conn: sqlite3.Connection) -> str:
    highest = 0
    for row in conn.execute("SELECT original_name FROM jobs"):
        match = _PAIR_NAME.fullmatch(row["original_name"] or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"Citizenship_{highest + 1}.pdf"


def _job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"], original_name=row["original_name"], kind=row["kind"],
        source_ext=row["source_ext"], status=row["status"], failure_stage=row["failure_stage"], message=row["message"],
        byte_size=row["byte_size"], page_count=row["page_count"], pages_spec=row["pages_spec"], copies=row["copies"],
        cups_job_id=row["cups_job_id"], created_at=row["created_at"], updated_at=row["updated_at"],
        delete_after=row["delete_after"], trashed_at=row["trashed_at"],
    )
