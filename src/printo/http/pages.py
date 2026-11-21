"""The two screens. Phones get the send page. The counter is only for the laptop, because it lives under /admin.

A phone that just joined the wifi opens some other address first, to see if the internet is there.
That address is sent to the send page. Answering it directly would tell the phone there is nothing to open.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse
from starlette.exceptions import HTTPException

from printo.http.portal import to_portal

_ROOT = Path(__file__).resolve().parents[1] / "web"
_PAGE = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; "
        "img-src 'self' blob:; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'"
    ),
}
_ASSET = {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}
_PUBLIC = {
    "common.css": ("common.css", "text/css; charset=utf-8"),
    "customer.css": ("customer/app.css", "text/css; charset=utf-8"),
    "customer.js": ("customer/app.js", "text/javascript; charset=utf-8"),
    "mark.svg": ("mark.svg", "image/svg+xml"),
}
_COUNTER = {
    "counter.css": ("counter/app.css", "text/css; charset=utf-8"),
    "counter.js": ("counter/app.js", "text/javascript; charset=utf-8"),
}

router = APIRouter()


@router.get("/")
def customer_page() -> FileResponse:
    return _html("customer/index.html")


@router.get("/favicon.svg")
@router.get("/favicon.ico")
def icon() -> FileResponse:
    return _known(_PUBLIC, "mark.svg")


@router.get("/c/{name}")
def customer_asset(name: str) -> FileResponse:
    return _known(_PUBLIC, name)


@router.get("/admin")
@router.get("/admin/")
def counter_page() -> FileResponse:
    return _html("counter/index.html")


@router.get("/admin/c/{name}")
def counter_asset(name: str) -> FileResponse:
    return _known(_COUNTER, name)


@router.api_route("/{path:path}", methods=["GET", "HEAD"])
def any_other_page(path: str, request: Request) -> RedirectResponse:
    # Admin paths that are not a real route stay hidden. Everything else goes to the send page,
    # including the addresses phones use to test a wifi network.
    if path == "admin" or path.startswith("admin/"):
        raise HTTPException(404)
    return to_portal(request)


def _html(rel: str) -> FileResponse:
    return _file(rel, "text/html; charset=utf-8", _PAGE)


def _known(table: dict, name: str) -> FileResponse:
    found = table.get(name)
    if found is None:
        raise HTTPException(404)
    rel, media = found
    return _file(rel, media, _ASSET)


def _file(rel: str, media: str, headers: dict) -> FileResponse:
    root = _ROOT.resolve()
    path = (root / rel).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type=media, headers=headers)
