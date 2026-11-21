import time
from io import BytesIO

from pypdf import PdfReader, PdfWriter

from tests.support import FakeCups, jpeg_bytes, pdf_bytes, running


def _upload(client, name, data):
    return client.post("/upload", files={"file": (name, data, "application/octet-stream")})


def _wait(client, number, statuses, seconds=5):
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        jobs = client.get("/admin/jobs").json()["jobs"]
        last = next((job for job in jobs if job["number"] == number), None)
        if last and last["status"] in statuses:
            return last
        time.sleep(0.05)
    raise AssertionError(last)


def test_photo_is_prepared_and_printed_in_order(tmp_path):
    with running(tmp_path) as (client, ctx, cups):
        response = _upload(client, "../../नागरिकता.jpg", jpeg_bytes())
        assert response.status_code == 201
        body = response.json()
        assert body["ok"] is True and "counter" in body["message"]
        job = _wait(client, body["number"], {"ready"})
        assert job["name"] == "नागरिकता.jpg"
        assert job["page_count"] == 1 and job["can_print"] is True
        printed = client.post(f"/admin/jobs/{job['id']}/print", json={"pages": "1", "copies": 2})
        assert printed.status_code == 200
        done = _wait(client, body["number"], {"done"})
        assert done["message"] == "Sent to the printer."
        assert done["copies"] == 2
        assert len(cups.submitted) == 1
        assert cups.submitted[0][1] == f"printo {body['number']}"
        saved = PdfReader(str(ctx.files.to_print(job["id"])))
        assert len(saved.pages) == 2
        file_response = client.get(f"/admin/jobs/{job['id']}/file")
        assert file_response.status_code == 200
        assert file_response.content.startswith(b"%PDF")


def test_selected_pdf_pages_repeat(tmp_path):
    with running(tmp_path) as (client, ctx, cups):
        response = _upload(client, "letter.pdf", pdf_bytes((200, 300, 400)))
        number = response.json()["number"]
        job = _wait(client, number, {"ready"})
        assert client.post(f"/admin/jobs/{job['id']}/print", json={"pages": "3,1", "copies": 2}).status_code == 200
        _wait(client, number, {"done"})
        widths = [int(page.mediabox.width) for page in PdfReader(str(ctx.files.to_print(job["id"]))).pages]
        assert widths == [400, 200, 400, 200]
        assert len(cups.submitted) == 1


def test_printer_off_does_not_submit(tmp_path):
    cups = FakeCups()
    cups.state = "off"
    with running(tmp_path, cups=cups) as (client, _ctx, cups):
        number = _upload(client, "a.pdf", pdf_bytes((200,))).json()["number"]
        job = _wait(client, number, {"ready"})
        refused = client.post(f"/admin/jobs/{job['id']}/print", json={})
        assert refused.status_code == 409
        assert "turned off" in refused.json()["message"]
        assert cups.submitted == []
        assert client.get(f"/admin/jobs/{job['id']}").json()["job"]["status"] == "ready"


def test_second_click_and_give_up(tmp_path):
    cups = FakeCups()
    cups.hold = True
    with running(tmp_path, cups=cups, print_give_up_seconds=0.8) as (client, _ctx, cups):
        number = _upload(client, "a.pdf", pdf_bytes((200,))).json()["number"]
        job = _wait(client, number, {"ready"})
        assert client.post(f"/admin/jobs/{job['id']}/print", json={"copies": 1}).status_code == 200
        again = client.post(f"/admin/jobs/{job['id']}/print", json={"copies": 1})
        assert again.status_code == 409
        assert "already" in again.json()["message"]
        failed = _wait(client, number, {"failed"}, seconds=3)
        assert "too long" in failed["message"]
        assert cups.cancelled
        assert failed["can_print"] is True


def test_phone_cannot_open_the_queue(tmp_path):
    with running(tmp_path, client_host="10.42.0.8") as (phone, _ctx, _cups):
        assert phone.get("/admin/jobs").status_code == 404
        assert phone.get("/admin/jobs/abcdef/file").status_code == 404
        assert "isn't available" in phone.get("/docs").json()["message"]
        uploaded = _upload(phone, "a.jpg", jpeg_bytes())
        assert uploaded.status_code == 201


def test_rejects_bad_files(tmp_path):
    with running(tmp_path, max_upload_bytes=64) as (client, _ctx, _cups):
        junk = _upload(client, "notes.txt", b"hello")
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
        number = _upload(client, "locked.pdf", buffer.getvalue()).json()["number"]
        job = _wait(client, number, {"failed"})
        assert "password" in job["message"] and job["can_retry"] is True
        assert client.post(f"/admin/jobs/{job['id']}/print", json={}).status_code == 409
        retried = client.post(f"/admin/jobs/{job['id']}/retry")
        assert retried.status_code == 200
        again = _wait(client, number, {"failed"})
        assert again["can_retry"] is True


def test_remove_deletes_the_file(tmp_path):
    with running(tmp_path) as (client, ctx, _cups):
        number = _upload(client, "a.pdf", pdf_bytes((200,))).json()["number"]
        job = _wait(client, number, {"ready"})
        removed = client.delete(f"/admin/jobs/{job['id']}")
        assert removed.status_code == 200 and removed.json()["message"] == "Removed."
        assert client.get(f"/admin/jobs/{job['id']}").status_code == 404
        assert client.get("/admin/jobs").json()["jobs"] == []
        assert not ctx.files.job_dir(job["id"]).exists()


def test_disk_full_and_health(tmp_path):
    with running(tmp_path, min_free_bytes=10**18) as (client, _ctx, _cups):
        assert client.get("/admin/health").json()["message"] == "printO is running."
        refused = _upload(client, "a.jpg", jpeg_bytes())
        assert refused.status_code == 507
        assert "too full" in refused.json()["message"]


def test_bad_page_range_leaves_the_file(tmp_path):
    with running(tmp_path) as (client, _ctx, cups):
        number = _upload(client, "a.pdf", pdf_bytes((200, 300))).json()["number"]
        job = _wait(client, number, {"ready"})
        refused = client.post(f"/admin/jobs/{job['id']}/print", json={"pages": "9"})
        assert refused.status_code == 400 and "2 pages" in refused.json()["message"]
        assert cups.submitted == []
        assert client.get(f"/admin/jobs/{job['id']}").json()["job"]["status"] == "ready"
