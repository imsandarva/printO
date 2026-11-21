"""The only thing a phone can do: hand over one file."""

from fastapi import APIRouter, File, Request, UploadFile

from printo.http.guard import host_of
from printo.http.respond import succeed
from printo.messages import received

router = APIRouter()


@router.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    job = await request.app.state.ctx.ingest.accept(file.filename or "", _blocks(file), host_of(request))
    return succeed({"number": job.public_code, "message": received(job.public_code)}, 201)


async def _blocks(file: UploadFile):
    while True:
        block = await file.read(1024 * 1024)
        if not block:
            break
        yield block
