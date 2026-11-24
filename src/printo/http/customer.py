"""What a phone can do: see which shop it reached, and hand over one file at a time."""

from fastapi import APIRouter, File, Request, UploadFile

from printo.desk import shop_name
from printo.http.guard import host_of
from printo.http.respond import succeed
from printo.messages import received

router = APIRouter()


@router.get("/shop")
def shop(request: Request) -> object:
    settings = request.app.state.ctx.settings
    # Name only. The password is never sent to the phone.
    return succeed({"name": shop_name(settings.data_dir), "max_bytes": settings.max_upload_bytes})


@router.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    job = await request.app.state.ctx.ingest.accept(file.filename or "", _blocks(file), host_of(request))
    return succeed({"message": received()}, 201)


async def _blocks(file: UploadFile):
    while True:
        block = await file.read(1024 * 1024)
        if not block:
            break
        yield block
