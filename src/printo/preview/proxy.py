"""Forward counter actions to the real printO on the shop port."""

import json
import urllib.error
import urllib.parse
import urllib.request

from printo.errors import UserError
from printo.messages import try_again, unexpected

_HOST = "127.0.0.1"
_TIMEOUT = 60


class ProxyDesk:
    def __init__(self, shop_port: int) -> None:
        self._base = f"http://{_HOST}:{shop_port}/admin"

    def close(self) -> None:
        return

    def upstream_events_url(self) -> str:
        return f"{self._base}/events"

    def jobs(self, status: str | None = None) -> list[dict]:
        trail = f"?status={urllib.parse.quote(status)}" if status else ""
        return _json(self, "GET", f"jobs{trail}")["jobs"]

    def one(self, job_id: str) -> dict:
        return _json(self, "GET", f"jobs/{job_id}")["job"]

    def file(self, job_id: str) -> bytes:
        return _bytes(self, "GET", f"jobs/{job_id}/file")

    def print_job(self, job_id: str, pages: str, copies: int) -> dict:
        return _json(self, "POST", f"jobs/{job_id}/print", {"pages": pages, "copies": copies})["job"]

    def retry(self, job_id: str) -> dict:
        return _json(self, "POST", f"jobs/{job_id}/retry", {})["job"]

    def remove(self, job_id: str) -> str:
        return _json(self, "DELETE", f"jobs/{job_id}")["message"]

    def printer(self) -> dict:
        return _json(self, "GET", "printer")


def _json(desk: ProxyDesk, method: str, path: str, body: dict | None = None) -> dict:
    payload = _load(_call(desk, method, path, body))
    if not payload.get("ok"):
        raise UserError(payload.get("message") or try_again(), 502)
    return payload


def _bytes(desk: ProxyDesk, method: str, path: str) -> bytes:
    return _call(desk, method, path)


def _call(desk: ProxyDesk, method: str, path: str, body: dict | None = None) -> bytes:
    url = f"{desk._base}/{path}"
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        payload = _load(exc.read())
        raise UserError(payload.get("message") or try_again(), exc.code) from None
    except (OSError, urllib.error.URLError):
        raise UserError(try_again(), 502) from None


def _load(raw: bytes) -> dict:
    try:
        body = json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError):
        raise UserError(unexpected(), 502) from None
    return body if isinstance(body, dict) else {}