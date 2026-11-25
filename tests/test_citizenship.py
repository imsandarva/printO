import time
from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfReader

from printo.printing.compose import A4_HEIGHT, A4_WIDTH
from tests.support import jpeg_bytes, pdf_bytes, running


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


def _pair(client, first, second):
    return client.post("/admin/citizenship", json={"ids": [first, second]})


def _heights(page):
    data = page.get_contents().get_data().decode("latin1")
    found = []
    for line in data.splitlines():
        parts = line.split()
        if len(parts) == 7 and parts[-1] == "cm":
            found.append(float(parts[5]))
    return found


def test_two_photos_become_one_sheet_named_in_order(tmp_path):
    with running(tmp_path) as (client, ctx, _cups):
        assert _upload(client, "front.jpg", jpeg_bytes("red")).status_code == 201
        assert _upload(client, "back.jpg", jpeg_bytes("navy")).status_code == 201
        front = _wait(client, "front.jpg", {"ready"})
        back = _wait(client, "back.jpg", {"ready"})
        made = _pair(client, front["id"], back["id"])
        assert made.status_code == 200
        job = made.json()["job"]
        assert job["name"] == "Citizenship_1.pdf"
        assert job["status"] == "ready" and job["page_count"] == 1 and job["can_print"] is True
        assert client.get("/admin/jobs").json()["jobs"][0]["id"] == job["id"]
        page = PdfReader(str(ctx.files.document(job["id"]))).pages[0]
        assert float(page.mediabox.width) == pytest.approx(A4_WIDTH)
        assert float(page.mediabox.height) == pytest.approx(A4_HEIGHT)
        assert len(list(page.images)) == 2
        placed = sorted((value for value in _heights(page) if value > 1), reverse=True)
        assert placed[0] > placed[1] > 20
        again = _pair(client, front["id"], back["id"])
        assert again.status_code == 200
        assert again.json()["job"]["name"] == "Citizenship_2.pdf"
        assert client.post(f"/admin/jobs/{job['id']}/print", json={}).status_code == 200
        assert _wait(client, "Citizenship_1.pdf", {"done"})["message"] == "Sent to the printer."


def test_two_single_page_pdfs_share_one_sheet(tmp_path):
    with running(tmp_path) as (client, ctx, _cups):
        assert _upload(client, "front.pdf", pdf_bytes((420,))).status_code == 201
        assert _upload(client, "back.pdf", pdf_bytes((380,))).status_code == 201
        front = _wait(client, "front.pdf", {"ready"})
        back = _wait(client, "back.pdf", {"ready"})
        made = _pair(client, front["id"], back["id"])
        assert made.status_code == 200
        job = made.json()["job"]
        assert job["name"] == "Citizenship_1.pdf" and job["page_count"] == 1
        page = PdfReader(str(ctx.files.document(job["id"]))).pages[0]
        assert float(page.mediabox.height) == pytest.approx(A4_HEIGHT)
        assert len(PdfReader(str(ctx.files.document(job["id"]))).pages) == 1


def test_refuses_the_wrong_pair(tmp_path):
    with running(tmp_path) as (client, _ctx, _cups):
        assert _upload(client, "front.jpg", jpeg_bytes()).status_code == 201
        assert _upload(client, "letter.pdf", pdf_bytes((200, 300))).status_code == 201
        front = _wait(client, "front.jpg", {"ready"})
        letter = _wait(client, "letter.pdf", {"ready"})
        one = client.post("/admin/citizenship", json={"ids": [front["id"]]})
        assert one.status_code == 400 and "two" in one.json()["message"].lower()
        same = _pair(client, front["id"], front["id"])
        assert same.status_code == 400 and "different" in same.json()["message"].lower()
        many = client.post("/admin/citizenship", json={"ids": [front["id"], letter["id"], front["id"]]})
        assert many.status_code == 400
        pages = _pair(client, front["id"], letter["id"])
        assert pages.status_code == 400 and "single page" in pages.json()["message"].lower()


def test_a_phone_cannot_pair(tmp_path):
    with running(tmp_path, client_host="10.42.0.8") as (phone, _ctx, _cups):
        assert phone.post("/admin/citizenship", json={"ids": ["a", "b"]}).status_code == 404


def test_trashed_name_is_not_reused(tmp_path):
    with running(tmp_path) as (client, _ctx, _cups):
        assert _upload(client, "front.jpg", jpeg_bytes("red")).status_code == 201
        assert _upload(client, "back.jpg", jpeg_bytes("navy")).status_code == 201
        front = _wait(client, "front.jpg", {"ready"})
        back = _wait(client, "back.jpg", {"ready"})
        first = _pair(client, front["id"], back["id"]).json()["job"]
        assert client.post(f"/admin/jobs/{first['id']}/trash").status_code == 200
        second = _pair(client, front["id"], back["id"]).json()["job"]
        assert second["name"] == "Citizenship_2.pdf"


def _wide_jpeg(color: str, size: tuple[int, int] = (400, 200)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def test_citizenship_rotates_front_back_and_sheet_independently(tmp_path):
    with running(tmp_path) as (client, ctx, _cups):
        assert _upload(client, "front.jpg", _wide_jpeg("red")).status_code == 201
        assert _upload(client, "back.jpg", _wide_jpeg("navy")).status_code == 201
        front = _wait(client, "front.jpg", {"ready"})
        back = _wait(client, "back.jpg", {"ready"})
        job = _pair(client, front["id"], back["id"]).json()["job"]

        meta = client.get(f"/admin/jobs/{job['id']}/pair")
        assert meta.status_code == 200
        pair = meta.json()["pair"]
        assert pair["rotations"] == [0, 0] and pair["sheet"] == 0 and len(pair["boxes"]) == 2
        box0_initial, box1_initial = pair["boxes"]
        assert box0_initial["w"] > box0_initial["h"]
        assert box1_initial["w"] > box1_initial["h"]

        # Rotate only front photo (index 0) 90 deg CW: front becomes tall, back stays unchanged.
        rot_front = client.post(f"/admin/jobs/{job['id']}/rotate", json={"target": "pair", "index": 0, "angle": 90})
        assert rot_front.status_code == 200
        pair_front = rot_front.json()["pair"]
        assert pair_front["rotations"] == [90, 0]
        assert pair_front["boxes"][0]["h"] > pair_front["boxes"][0]["w"]
        assert pair_front["boxes"][1]["w"] == pytest.approx(box1_initial["w"], abs=1e-4)
        assert pair_front["boxes"][1]["h"] == pytest.approx(box1_initial["h"], abs=1e-4)

        # Rotate whole sheet 90 deg CW.
        rot_sheet = client.post(f"/admin/jobs/{job['id']}/rotate", json={"target": "sheet", "angle": 90})
        assert rot_sheet.status_code == 200
        assert rot_sheet.json()["pair"]["sheet"] == 90
        page = PdfReader(str(ctx.files.document(job["id"]))).pages[0]
        assert float(page.mediabox.width) == pytest.approx(A4_WIDTH)
        assert float(page.mediabox.height) == pytest.approx(A4_HEIGHT)

        # Bad target / angle / index is refused.
        assert client.post(f"/admin/jobs/{job['id']}/rotate", json={"target": "pair", "index": 2, "angle": 90}).status_code == 400
        assert client.post(f"/admin/jobs/{job['id']}/rotate", json={"target": "pair", "index": 0, "angle": 45}).status_code == 400
