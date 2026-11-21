"""The shop side. These routes exist only for the laptop at the counter."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from printo.desk import desk_message
from printo.domain.job import Job
from printo.errors import UserError
from printo.http.respond import succeed
from printo.messages import not_found, present, running

router = APIRouter(prefix="/admin")


class PrintBody(BaseModel):
    pages: str = "all"
    copies: int = 1


@router.get("/health")
def health() -> object:
    return succeed({"message": running()})


@router.get("/front")
def front(request: Request) -> object:
    return succeed({"message": desk_message(request.app.state.ctx.settings.data_dir)})


@router.get("/printer")
def printer(request: Request) -> object:
    status = request.app.state.ctx.cups.status()
    return succeed({"name": status.name, "state": status.state, "message": status.summary})


@router.get("/jobs")
def list_jobs(request: Request, status: str | None = None) -> object:
    jobs = request.app.state.ctx.jobs.matching(status)
    return succeed({"jobs": [present(job) for job in jobs]})


@router.get("/jobs/{job_id}")
def one_job(request: Request, job_id: str) -> object:
    job = _job(request, job_id)
    return succeed({"job": present(job)})


@router.get("/jobs/{job_id}/file")
def download(request: Request, job_id: str) -> FileResponse:
    job = _job(request, job_id)
    path = request.app.state.ctx.files.document(job.id)
    if not job.page_count or not path.is_file():
        raise UserError(not_found(), 404)
    return FileResponse(path, media_type="application/pdf", filename=_download_name(job.original_name))


@router.post("/jobs/{job_id}/print")
async def print_job(request: Request, job_id: str, body: PrintBody) -> object:
    job = await request.app.state.ctx.printing.print_job(job_id, body.pages, body.copies)
    return succeed({"job": present(job)})


@router.post("/jobs/{job_id}/retry")
def retry(request: Request, job_id: str) -> object:
    job = request.app.state.ctx.converter.retry(job_id)
    return succeed({"job": present(job)})


@router.delete("/jobs/{job_id}")
async def remove(request: Request, job_id: str) -> object:
    message = await request.app.state.ctx.printing.cancel_job(job_id)
    return succeed({"message": message})


@router.get("/events")
def events(request: Request) -> StreamingResponse:
    stream = request.app.state.ctx.events.stream()
    return StreamingResponse(stream, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def _job(request: Request, job_id: str) -> Job:
    job = request.app.state.ctx.jobs.get(job_id)
    if job is None:
        raise UserError(not_found(), 404)
    return job


def _download_name(original: str) -> str:
    stem = Path(original).stem
    cleaned = "".join(ch for ch in stem if ch.isalnum() or ch in " ._-").strip()[:80]
    return f"{cleaned or 'document'}.pdf"
