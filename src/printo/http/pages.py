"""The two screens. Phones get the send page. The counter is only for the laptop, because it lives under /admin."""

import json
import re
from html import escape
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse
from starlette.exceptions import HTTPException

from printo.desk import shop_name
from printo.messages import customer_copy

_ROOT = Path(__file__).resolve().parents[1] / "web"
_PAGE = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; "
        "connect-src 'self'; img-src 'self' blob:; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'"
    ),
}
# Customer scripts live beside the page. The name has to be a single safe segment so it cannot climb out of that folder.
_MODULE = re.compile(r"^[A-Za-z0-9._-]+$")
_MODULE_TYPES = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8"}
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
def customer_page(request: Request) -> HTMLResponse:
    settings = request.app.state.ctx.settings
    boot = {"name": shop_name(settings.data_dir), "max_bytes": settings.max_upload_bytes, "copy": customer_copy()}
    return HTMLResponse(_customer_html(boot), headers=_PAGE)


@router.get("/favicon.svg")
@router.get("/favicon.ico")
def icon() -> FileResponse:
    return _known(_PUBLIC, "mark.svg")


@router.get("/c/{name}")
def customer_asset(name: str) -> FileResponse:
    if name in _PUBLIC:
        return _known(_PUBLIC, name)
    # Modules the page imports, including the local PDF viewer. Not a general file host.
    if ".." not in name and _MODULE.fullmatch(name) and _MODULE_TYPES.get(Path(name).suffix):
        return _file(f"customer/{name}", _MODULE_TYPES[Path(name).suffix], _ASSET)
    raise HTTPException(404)


@router.get("/admin")
@router.get("/admin/")
def counter_page() -> FileResponse:
    return _html("counter/index.html")


@router.get("/admin/c/{name}")
def counter_asset(name: str) -> FileResponse:
    if name in _COUNTER:
        return _known(_COUNTER, name)
    # Modules the counter imports. Not a general file host.
    if ".." not in name and _MODULE.fullmatch(name) and _MODULE_TYPES.get(Path(name).suffix):
        return _file(f"counter/{name}", _MODULE_TYPES[Path(name).suffix], _ASSET)
    raise HTTPException(404)


def _customer_html(boot: dict) -> str:
    copy = boot["copy"]
    link = copy["connected_named"].replace("{name}", boot["name"]) if boot["name"] else copy["connected_shop"]
    raw = (_ROOT / "customer" / "index.html").read_text(encoding="utf-8")
    # Keep the boot JSON from being able to close the script tag.
    payload = json.dumps(boot, ensure_ascii=False).replace("<", "\\u003c")
    for key, value in {
        "__LINK__": escape(link),
        "__HEADING__": escape(copy["heading"]),
        "__SUPPORT__": escape(copy["support"]),
        "__CHOOSE__": escape(copy["choose"]),
        "__TYPES__": escape(copy["types"]),
        "__NOSCRIPT__": escape(copy["noscript"]),
        "__BOOT__": payload,
    }.items():
        raw = raw.replace(key, value)
    return raw


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
