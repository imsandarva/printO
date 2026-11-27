import time
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from printo.printing.compose import A4_HEIGHT, A4_WIDTH
from tests.support import FakeCups, jpeg_bytes, marked_pdf, pdf_bytes, running


def _upload(client, name, data):
    return client.post("/upload", files={"file": (name, data, "application/octet-stream")})


def _wait(client, name, statuses, seconds=5):
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        jobs = client.get("/admin/jobs").json()["jobs"]
        last = next((job for job in jobs if job["name"] == name), None)
        if last and last["status"] in statuses:
            return last
        time.sleep(0.05)
    raise AssertionError(last)


def test_photo_is_prepared_and_printed_in_order(tmp_path):
    with running(tmp_path) as (client, ctx, cups):
        response = _upload(client, "../../नागरिकता.jpg", jpeg_bytes())
        assert response.status_code == 201
        body = response.json()
        assert body["ok"] is True and body["message"] == "Received." and "number" not in body
        job = _wait(client, "नागरिकता.jpg", {"ready"})
        assert job["name"] == "नागरिकता.jpg"
        assert job["page_count"] == 1 and job["can_print"] is True
        printed = client.post(f"/admin/jobs/{job['id']}/print", json={"pages": "1", "copies": 2})
        assert printed.status_code == 200
        done = _wait(client, "नागरिकता.jpg", {"done"})
        assert done["message"] == "Sent to the printer."
        assert done["copies"] == 2
        assert len(cups.submitted) == 1
        assert cups.submitted[0][1] == "printo नागरिकता.jpg"
        saved = PdfReader(str(ctx.files.to_print(job["id"])))
        assert len(saved.pages) == 2
        file_response = client.get(f"/admin/jobs/{job['id']}/file")
        assert file_response.status_code == 200
        assert file_response.content.startswith(b"%PDF")


def test_selected_pdf_pages_repeat(tmp_path):
    with running(tmp_path) as (client, ctx, cups):
        assert _upload(client, "letter.pdf", pdf_bytes((200, 300, 400))).status_code == 201
        job = _wait(client, "letter.pdf", {"ready"})
        assert client.post(f"/admin/jobs/{job['id']}/print", json={"pages": "3,1", "copies": 2}).status_code == 200
        _wait(client, "letter.pdf", {"done"})
        pages = PdfReader(str(ctx.files.to_print(job["id"]))).pages
        assert len(pages) == 4
        assert [float(page.mediabox.width) for page in pages] == pytest.approx([A4_WIDTH] * 4)
        assert len(cups.submitted) == 1


def test_fit_is_printed_and_out_of_range_is_refused(tmp_path):
    with running(tmp_path) as (client, ctx, _cups):
        assert _upload(client, "letter.pdf", marked_pdf()).status_code == 201
        job = _wait(client, "letter.pdf", {"ready"})
        refused = client.post(f"/admin/jobs/{job['id']}/print", json={"copies": 1, "fit": 10})
        assert refused.status_code == 400
        assert "40%" in refused.json()["message"]
        too_big = client.post(f"/admin/jobs/{job['id']}/print", json={"copies": 1, "fit": 126})
        assert too_big.status_code == 400
        assert client.post(f"/admin/jobs/{job['id']}/print", json={"copies": 1, "fit": 50}).status_code == 200
        _wait(client, "letter.pdf", {"done"})
        page = PdfReader(str(ctx.files.to_print(job["id"]))).pages[0]
        assert float(page.mediabox.width) == pytest.approx(A4_WIDTH)
        assert float(page.mediabox.height) == pytest.approx(A4_HEIGHT)
        assert b"cm" in page.get_contents().get_data()


def test_printer_off_does_not_submit(tmp_path):
    cups = FakeCups()
    cups.state = "off"
    with running(tmp_path, cups=cups) as (client, _ctx, cups):
        assert _upload(client, "a.pdf", pdf_bytes((200,))).status_code == 201
        job = _wait(client, "a.pdf", {"ready"})
        refused = client.post(f"/admin/jobs/{job['id']}/print", json={})
        assert refused.status_code == 409
        assert "turned off" in refused.json()["message"]
        assert cups.submitted == []
        assert client.get(f"/admin/jobs/{job['id']}").json()["job"]["status"] == "ready"


def test_second_click_and_give_up(tmp_path):
    cups = FakeCups()
    cups.hold = True
    with running(tmp_path, cups=cups, print_give_up_seconds=0.8) as (client, _ctx, cups):
        assert _upload(client, "a.pdf", pdf_bytes((200,))).status_code == 201
        job = _wait(client, "a.pdf", {"ready"})
        assert client.post(f"/admin/jobs/{job['id']}/print", json={"copies": 1}).status_code == 200
        again = client.post(f"/admin/jobs/{job['id']}/print", json={"copies": 1})
        assert again.status_code == 409
        assert "already" in again.json()["message"]
        failed = _wait(client, "a.pdf", {"failed"}, seconds=3)
        assert "too long" in failed["message"]
        assert cups.cancelled
        assert failed["can_print"] is True


def test_phone_cannot_open_the_queue(tmp_path):
    with running(tmp_path, client_host="10.42.0.8") as (phone, _ctx, _cups):
        assert phone.get("/admin/jobs").status_code == 404
        assert phone.get("/admin/jobs/abcdef/file").status_code == 404
        opened = phone.get("/docs", follow_redirects=False)
        assert opened.status_code == 404 and opened.headers.get("location") is None
        uploaded = _upload(phone, "a.jpg", jpeg_bytes())
        assert uploaded.status_code == 201


def test_rejects_bad_files(tmp_path):
    with running(tmp_path, max_upload_bytes=64) as (client, _ctx, _cups):
        text = _upload(client, "notes.txt", b"hello")
        assert text.status_code == 201
        junk = _upload(client, "video.txt", b"\x00\x00\x00\x18ftypmp42")
        assert junk.status_code == 400 and "PDF" in junk.json()["message"]
        empty = _upload(client, "empty.pdf", b"")
        assert empty.status_code == 400 and "empty" in empty.json()["message"]
        huge = _upload(client, "big.jpg", b"\xff\xd8\xff" + b"x" * 80)
        assert huge.status_code == 413


def test_too_many_uploads(tmp_path):
    with running(tmp_path, uploads_per_ip=1) as (client, _ctx, _cups):
        assert _upload(client, "a.jpg", jpeg_bytes()).status_code == 201
        assert _upload(client, "b.jpg", jpeg_bytes()).status_code == 429


def test_locked_pdf_can_be_retried_only_when_that_makes_sense(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    buffer = BytesIO()
    writer.write(buffer)
    with running(tmp_path) as (client, _ctx, _cups):
        assert _upload(client, "locked.pdf", buffer.getvalue()).status_code == 201
        job = _wait(client, "locked.pdf", {"failed"})
        assert "password" in job["message"] and job["can_retry"] is True
        assert client.post(f"/admin/jobs/{job['id']}/print", json={}).status_code == 409
        retried = client.post(f"/admin/jobs/{job['id']}/retry")
        assert retried.status_code == 200
        again = _wait(client, "locked.pdf", {"failed"})
        assert again["can_retry"] is True


def test_delete_keeps_the_file_until_trash_says_so(tmp_path):
    with running(tmp_path) as (client, ctx, _cups):
        assert _upload(client, "a.pdf", pdf_bytes((200,))).status_code == 201
        job = _wait(client, "a.pdf", {"ready"})
        blocked = client.delete(f"/admin/jobs/{job['id']}")
        assert blocked.status_code == 409 and ctx.files.job_dir(job["id"]).exists()
        moved = client.post(f"/admin/jobs/{job['id']}/trash")
        assert moved.status_code == 200 and moved.json()["message"] == "Moved to Trash."
        assert client.get("/admin/jobs").json()["jobs"] == []
        assert [item["id"] for item in client.get("/admin/jobs?trashed=1").json()["jobs"]] == [job["id"]]
        assert client.post(f"/admin/jobs/{job['id']}/print", json={}).status_code == 409
        assert ctx.files.job_dir(job["id"]).exists()
        brought = client.post(f"/admin/jobs/{job['id']}/restore")
        assert brought.status_code == 200 and client.get("/admin/jobs").json()["jobs"][0]["id"] == job["id"]
        assert client.post(f"/admin/jobs/{job['id']}/trash").status_code == 200
        removed = client.delete(f"/admin/jobs/{job['id']}")
        assert removed.status_code == 200 and removed.json()["message"] == "Deleted."
        assert client.get(f"/admin/jobs/{job['id']}").status_code == 404
        assert client.get("/admin/jobs?trashed=1").json()["jobs"] == []
        assert not ctx.files.job_dir(job["id"]).exists()


def test_disk_full_and_health(tmp_path):
    with running(tmp_path, min_free_bytes=10**18) as (client, _ctx, _cups):
        assert client.get("/admin/health").json()["message"] == "printO is running."
        refused = _upload(client, "a.jpg", jpeg_bytes())
        assert refused.status_code == 507
        assert "too full" in refused.json()["message"]


def test_bad_page_range_leaves_the_file(tmp_path):
    with running(tmp_path) as (client, _ctx, cups):
        assert _upload(client, "a.pdf", pdf_bytes((200, 300))).status_code == 201
        job = _wait(client, "a.pdf", {"ready"})
        refused = client.post(f"/admin/jobs/{job['id']}/print", json={"pages": "9"})
        assert refused.status_code == 400 and "2 pages" in refused.json()["message"]
        assert cups.submitted == []
        assert client.get(f"/admin/jobs/{job['id']}").json()["job"]["status"] == "ready"


def test_single_image_rotation_and_pdf_page_rotations(tmp_path):
    with running(tmp_path) as (client, ctx, _cups):
        assert _upload(client, "sideways.jpg", jpeg_bytes("teal")).status_code == 201
        img_job = _wait(client, "sideways.jpg", {"ready"})
        rotated = client.post(f"/admin/jobs/{img_job['id']}/rotate", json={"target": "image", "angle": 90})
        assert rotated.status_code == 200 and rotated.json()["angle"] == 90
        assert client.get(f"/admin/jobs/{img_job['id']}/pair").json()["angle"] == 90
        img_pdf = PdfReader(str(ctx.files.document(img_job["id"]))).pages[0]
        assert float(img_pdf.mediabox.width) == pytest.approx(A4_WIDTH, abs=2)
        assert float(img_pdf.mediabox.height) == pytest.approx(A4_HEIGHT, abs=2)

        writer = PdfWriter()
        for width in (200, 300):
            page = writer.add_blank_page(width=width, height=800)
            stream = DecodedStreamObject()
            stream.set_data(b"0 0 m 10 10 l S")
            page[NameObject("/Contents")] = writer._add_object(stream)
        buf = BytesIO()
        writer.write(buf)
        assert _upload(client, "doc.pdf", buf.getvalue()).status_code == 201
        pdf_job = _wait(client, "doc.pdf", {"ready"})
        bad = client.post(f"/admin/jobs/{pdf_job['id']}/print", json={"pages": "all", "rotations": {"9": 90}})
        assert bad.status_code == 400
        ok = client.post(f"/admin/jobs/{pdf_job['id']}/print", json={"pages": "all", "rotations": {"2": 90}})
        assert ok.status_code == 200
        _wait(client, "doc.pdf", {"done"})
        printed_pages = PdfReader(str(ctx.files.to_print(pdf_job["id"]))).pages
        assert len(printed_pages) == 2
        assert b"-1 1 " in printed_pages[1].get_contents().get_data()
