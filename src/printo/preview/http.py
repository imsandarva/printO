"""Answer the counter. These are the same paths the page already uses."""

import json
import queue
import re
import threading
import traceback
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from printo.domain.status import ALL
from printo.errors import UserError
from printo.messages import connected, hidden, printer_ready, try_again, unexpected, validation
from printo.preview.feed import pack
from printo.preview.files import asset, asset_headers, counter_page, page_headers

_ITEM = re.compile(r"^/admin/jobs/([0-9a-f]{32})$")
_FILE = re.compile(r"^/admin/jobs/([0-9a-f]{32})/file$")
_PRINT = re.compile(r"^/admin/jobs/([0-9a-f]{32})/print$")
_RETRY = re.compile(r"^/admin/jobs/([0-9a-f]{32})/retry$")
_JSON = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        dispatch(self, "GET")

    def do_POST(self) -> None:
        dispatch(self, "POST")

    def do_DELETE(self) -> None:
        dispatch(self, "DELETE")

    def log_message(self, format: str, *args) -> None:
        return


def dispatch(handler: Handler, method: str) -> None:
    try:
        route(handler, method, path_of(handler))
    except UserError as exc:
        send_json(handler, {"ok": False, "message": exc.message}, exc.status)
    except Exception:
        traceback.print_exc()
        send_json(handler, {"ok": False, "message": unexpected()}, 500)


def route(handler: Handler, method: str, path: str) -> None:
    if path == "/admin" and method == "GET":
        send_page(handler)
        return
    if path == "/admin/health" and method == "GET":
        send_json(handler, {"ok": True, "preview": True, "message": "The counter is open."})
        return
    if path == "/admin/printer" and method == "GET":
        send_printer(handler)
        return
    if path == "/admin/jobs" and method == "GET":
        send_jobs(handler)
        return
    if path == "/admin/events" and method == "GET":
        send_events(handler)
        return
    if (found := _ITEM.fullmatch(path)) and method == "GET":
        send_json(handler, {"ok": True, "job": handler.server.desk.one(found.group(1))})
        return
    if (found := _FILE.fullmatch(path)) and method == "GET":
        send_bytes(handler, 200, "application/pdf", handler.server.desk.file(found.group(1)), _JSON)
        return
    if (found := _PRINT.fullmatch(path)) and method == "POST":
        send_print(handler, found.group(1))
        return
    if (found := _RETRY.fullmatch(path)) and method == "POST":
        send_json(handler, {"ok": True, "job": handler.server.desk.retry(found.group(1))})
        return
    if (found := _ITEM.fullmatch(path)) and method == "DELETE":
        send_json(handler, {"ok": True, "message": handler.server.desk.remove(found.group(1))})
        return
    if found_any(path):
        raise UserError(try_again(), 405)
    found_asset = asset(path) if method == "GET" else None
    if found_asset is None:
        raise UserError(hidden(), 404)
    body, media = found_asset
    send_bytes(handler, 200, media, body, asset_headers())


def send_page(handler: Handler) -> None:
    body = counter_page()
    if body is None:
        raise UserError(hidden(), 404)
    send_bytes(handler, 200, "text/html; charset=utf-8", body, page_headers())


def send_jobs(handler: Handler) -> None:
    status = (parse_qs(urlsplit(handler.path).query).get("status") or [None])[0]
    if status is not None and status not in ALL:
        raise UserError(validation())
    send_json(handler, {"ok": True, "jobs": handler.server.desk.jobs(status)})


def send_print(handler: Handler, job_id: str) -> None:
    body = read_json(handler)
    pages, copies = body.get("pages", "all"), body.get("copies", 1)
    send_json(handler, {"ok": True, "job": handler.server.desk.print_job(job_id, pages, copies)})


def send_printer(handler: Handler) -> None:
    desk = handler.server.desk
    if _live_desk(desk):
        send_json(handler, desk.printer())
        return
    send_json(handler, {"ok": True, "name": "MF3010", "state": "ready", "message": printer_ready()})


def send_events(handler: Handler) -> None:
    if _live_desk(handler.server.desk):
        send_events_live(handler)
        return
    send_events_sample(handler)


def send_events_sample(handler: Handler) -> None:
    box = handler.server.hub.subscribe()
    try:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()
        handler.wfile.write(pack("ready", {"message": connected()}))
        handler.wfile.flush()
        while True:
            handler.wfile.write(_next(box))
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
        return
    finally:
        handler.server.hub.unsubscribe(box)


def send_events_live(handler: Handler) -> None:
    desk = handler.server.desk
    stop = threading.Event()
    gate = threading.Lock()
    box = handler.server.hub.subscribe()

    def relay() -> None:
        try:
            with urllib.request.urlopen(desk.upstream_events_url(), timeout=30) as upstream:
                while not stop.is_set():
                    chunk = upstream.read(1024)
                    if not chunk:
                        break
                    with gate:
                        handler.wfile.write(chunk)
                        handler.wfile.flush()
        except (OSError, urllib.error.URLError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            stop.set()

    try:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()
        threading.Thread(target=relay, name="counter-preview-events", daemon=True).start()
        while not stop.is_set():
            try:
                piece = box.get(timeout=15)
            except queue.Empty:
                piece = b": ping\n\n"
            with gate:
                handler.wfile.write(piece)
                handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
        return
    finally:
        stop.set()
        handler.server.hub.unsubscribe(box)


def send_json(handler: Handler, payload: dict, status: int = 200) -> None:
    send_bytes(handler, status, "application/json; charset=utf-8", json.dumps(payload, separators=(",", ":")).encode(), _JSON)


def send_bytes(handler: Handler, status: int, media: str, body: bytes, headers: dict) -> None:
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", media)
        handler.send_header("Content-Length", str(len(body)))
        for key, value in headers.items():
            handler.send_header(key, value)
        handler.end_headers()
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        return


def read_json(handler: Handler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length < 0 or length > 8000:
        raise UserError(validation())
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        raise UserError(validation()) from None
    if not isinstance(body, dict):
        raise UserError(validation())
    return body


def path_of(handler: Handler) -> str:
    path = urlsplit(handler.path).path
    if ".." in path:
        raise UserError(hidden(), 404)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


def found_any(path: str) -> bool:
    return bool(_ITEM.fullmatch(path) or _FILE.fullmatch(path) or _PRINT.fullmatch(path) or _RETRY.fullmatch(path))


def _next(box: queue.Queue[bytes]) -> bytes:
    try:
        return box.get(timeout=15)
    except queue.Empty:
        return b": ping\n\n"


def _live_desk(desk: object) -> bool:
    return hasattr(desk, "upstream_events_url")
