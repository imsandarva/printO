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

    def jobs(self, status: str | None = None, *, trashed: bool = False) -> list[dict]:
        parts: list[str] = []
        if status:
            parts.append("status=" + urllib.parse.quote(status))
        if trashed:
            parts.append("trashed=1")
        trail = ("?" + "&".join(parts)) if parts else ""
        return _json(self, "GET", f"jobs{trail}")["jobs"]

    def one(self, job_id: str) -> dict:
        return _json(self, "GET", f"jobs/{job_id}")["job"]

    def file(self, job_id: str) -> bytes:
        return _bytes(self, "GET", f"jobs/{job_id}/file")

    def preview_status(self, job_id: str) -> dict:
        body = _json(self, "GET", f"jobs/{job_id}/previews")
        return {"total": body.get("total", 0), "ready": body.get("ready", 0), "revision": body.get("revision", "")}

    def preview_image(self, job_id: str, page: int, revision: str) -> bytes:
        query = urllib.parse.urlencode({"v": revision})
        return _bytes(self, "GET", f"jobs/{job_id}/previews/{page}?{query}")

    def pair_meta(self, job_id: str) -> dict:
        body = _json(self, "GET", f"jobs/{job_id}/pair")
        return {"pair": body.get("pair"), "angle": body.get("angle", 0)}

    def rotate(self, job_id: str, payload: dict) -> dict:
        # The new picture has to come back with the angle. Without it the sheet stays as it was.
        return rotation_result(_json(self, "POST", f"jobs/{job_id}/rotate", payload))

    def print_job(self, job_id: str, pages: str, copies: int, fit: int = 100, rotations: dict | None = None, landscape: bool = False) -> dict:
        payload: dict = {"pages": pages, "copies": copies, "fit": fit}
        if rotations:
            payload["rotations"] = rotations
        if landscape:
            payload["landscape"] = True
        return _json(self, "POST", f"jobs/{job_id}/print", payload)["job"]

    def citizenship(self, ids: list[str]) -> dict:
        return _json(self, "POST", "citizenship", {"ids": ids})["job"]

    def retry(self, job_id: str) -> dict:
        return _json(self, "POST", f"jobs/{job_id}/retry", {})["job"]

    def trash(self, job_id: str) -> dict:
        body = _json(self, "POST", f"jobs/{job_id}/trash", {})
        return {"message": body["message"], "job": body["job"]}

    def restore(self, job_id: str) -> dict:
        return _json(self, "POST", f"jobs/{job_id}/restore", {})["job"]

    def remove(self, job_id: str) -> str:
        return _json(self, "DELETE", f"jobs/{job_id}")["message"]

    def printer(self) -> dict:
        return _json(self, "GET", "printer")


def rotation_result(body: dict) -> dict:
    """Keep the rebuilt picture with the turn. A photo is placed again; the sheet has to show that."""
    kept = {"job": body["job"]}
    for key in ("pair", "angle", "preview"):
        if key in body:
            kept[key] = body[key]
    return kept


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
