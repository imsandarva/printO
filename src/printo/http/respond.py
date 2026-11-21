"""JSON replies. The sentence in ``message`` is what a person should read."""

from fastapi.responses import JSONResponse


def succeed(payload: dict, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, **payload}, status_code=status)


def fail(message: str, status: int) -> JSONResponse:
    return JSONResponse({"ok": False, "message": message}, status_code=status)
