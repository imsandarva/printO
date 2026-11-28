"""The counter can be opened on its own, with sample files, and without the shop."""

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from printo.preview.paper import sheet
from printo.preview.serve import already_running, start
from printo.preview.watch import watch


def test_counter_opens_with_sample_files():
    preview = start(port=0, delay=0.05, sample=True)
    try:
        assert preview.server.server_address[0] == "127.0.0.1"
        assert already_running(preview.server.server_address[1])
        status, headers, body = _open(preview.url)
        assert status == 200 and "text/html" in headers["Content-Type"]
        assert b"/admin/c/counter.js" in body and b"/admin/c/preview.js" in body
        assert "default-src 'self'" in headers["Content-Security-Policy"]
        assert "preview.js" not in Path("src/printo/web/counter/index.html").read_text(encoding="utf-8")
        style, _, css = _open(preview.url.replace("/admin/", "/admin/c/counter.css"))
        assert style == 200 and b".ticket" in css and b".sheet-stack" in css and b".sheet-bar" in css and b"iframe" not in css
        bar = _open(preview.url.replace("/admin/", "/admin/c/bar.js"))
        assert bar[0] == 200 and b"holdPages" in bar[2]
        sheets = _open(preview.url.replace("/admin/", "/admin/c/sheets.js"))
        assert sheets[0] == 200 and b"showSheets" in sheets[2] and b"iframe" not in sheets[2]
        assert b"getDocument" not in sheets[2] and b"Preparing this page" not in sheets[2]
        rotate_mod = _open(preview.url.replace("/admin/", "/admin/c/rotate.js"))
        assert rotate_mod[0] == 200 and b"createRotateDock" in rotate_mod[2]
        assert _open(preview.url.replace("/admin/", "/c/pdf.min.mjs"))[0] == 404
        assert _open(preview.url.replace("/admin/", "/c/pdf.worker.min.mjs"))[0] == 404
        dates = _open(preview.url.replace("/admin/", "/admin/c/dates.js"))
        assert dates[0] == 200 and b"Today" in dates[2]
        assert _open(preview.url.replace("/admin/", "/"))[0] == 404
        jobs = _json(_open(f"{preview.url}jobs"))
        assert jobs["ok"] is True
        passport = next(job for job in jobs["jobs"] if job["name"] == "Passport photo.jpg")
        invitation = next(job for job in jobs["jobs"] if job["name"] == "Invitation.pdf")
        citizenship = _json(_open(f"{preview.url}citizenship", {"ids": [passport["id"], invitation["id"]]}))
        assert citizenship["job"]["name"] == "Citizenship_1.pdf" and citizenship["job"]["page_count"] == 1
        pair_info = _json(_open(f"{preview.url}jobs/{citizenship['job']['id']}/pair"))
        assert len(pair_info["pair"]["boxes"]) == 2
        turned_pair = _json(_open(f"{preview.url}jobs/{citizenship['job']['id']}/rotate", {"target": "pair", "index": 0, "angle": 90}))
        assert turned_pair["ok"] is True and turned_pair["pair"]["rotations"] == [90, 0]
        ready = next(job for job in jobs["jobs"] if job["name"] == "School admission form.pdf")
        assert ready["can_print"] is True and ready["page_count"] == 4
        bad = _json(_open(f"{preview.url}jobs/{ready['id']}/print", {"pages": "99", "copies": 1}))
        assert bad["ok"] is False and "4 pages" in bad["message"]
        printed = _json(_open(f"{preview.url}jobs/{ready['id']}/print", {"pages": "1-2", "copies": 2}))
        assert printed["job"]["status"] == "printing"
        assert _wait(preview, ready["id"])["status"] == "done"
        pdf = _open(f"{preview.url}jobs/{ready['id']}/file")
        assert pdf[2].startswith(b"%PDF") and b"/Count 4" in pdf[2]
        pics = _json(_open(f"{preview.url}jobs/{ready['id']}/previews"))
        assert pics["ok"] is True and pics["total"] == 4 and pics["ready"] == 4 and pics["revision"]
        image = _open(f"{preview.url}jobs/{ready['id']}/previews/1?v={pics['revision']}")
        assert image[0] == 200 and image[2].startswith(b"\xff\xd8") and "immutable" in image[1]["Cache-Control"]
        assert _open(f"{preview.url}jobs/{ready['id']}/previews/1?v=not-a-picture")[0] == 404
        busy = next(job for job in jobs["jobs"] if job["status"] == "printing")
        again = _json(_open(f"{preview.url}jobs/{busy['id']}/print", {"pages": "all", "copies": 1}))
        assert again["ok"] is False
        failed = next(job for job in jobs["jobs"] if job["can_retry"])
        assert _json(_open(f"{preview.url}jobs/{failed['id']}/retry", {}))["job"]["status"] == "converting"
        moved = _json(_open(f"{preview.url}jobs/{failed['id']}/trash", {}, "POST"))
        assert moved["ok"] is True and moved["message"] == "Moved to Trash."
        assert all(job["id"] != failed["id"] for job in _json(_open(f"{preview.url}jobs"))["jobs"])
        assert any(job["id"] == failed["id"] for job in _json(_open(f"{preview.url}jobs?trashed=1"))["jobs"])
        blocked = _json(_open(f"{preview.url}jobs/{ready['id']}", method="DELETE"))
        assert blocked["ok"] is False
        removed = _json(_open(f"{preview.url}jobs/{failed['id']}", method="DELETE"))
        assert removed["ok"] is True
        assert sheet(1).startswith(b"%PDF")
    finally:
        preview.close()


def test_a_save_is_noticed(tmp_path):
    path = tmp_path / "app.css"
    path.write_text("a", encoding="utf-8")
    seen: list[list[str]] = []
    stop = threading.Event()
    thread = threading.Thread(target=watch, args=([path], seen.append, stop, 0.05), daemon=True)
    thread.start()
    try:
        time.sleep(0.12)
        path.write_text("b", encoding="utf-8")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not seen:
            time.sleep(0.05)
        assert seen == [["app.css"]]
    finally:
        stop.set()
        thread.join(timeout=1)


def _wait(preview, job_id: str) -> dict:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        found = next(job for job in _json(_open(f"{preview.url}jobs"))["jobs"] if job["id"] == job_id)
        if found["status"] == "done":
            assert found["pages"] == "1-2" and found["copies"] == 2
            return found
        time.sleep(0.05)
    raise AssertionError("the sample file stayed on its way to the printer")


def _json(response: tuple) -> dict:
    return json.loads(response[2].decode())


def _open(url: str, payload: dict | None = None, method: str | None = None) -> tuple[int, dict, bytes]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"))
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()
