"""Page pictures are made once, kept beside the file, and replaced when that file changes."""

import time

from printo.pictures.maker import PictureMaker
from printo.storage.files import Files
from tests.support import pdf_bytes, running


def _wait_pictures(client, job_id, seconds=5):
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        last = client.get(f"/admin/jobs/{job_id}/previews").json()
        if last.get("ok") and last.get("ready") == last.get("total") and last.get("total"):
            return last
        time.sleep(0.05)
    raise AssertionError(last)


def test_each_page_is_saved_and_a_new_file_drops_the_old_ones(tmp_path):
    files = Files(tmp_path)
    files.ensure()
    job_id = "ab" * 16
    document = files.document(job_id)
    document.parent.mkdir(parents=True)
    document.write_bytes(pdf_bytes((200, 300, 400)))
    maker = PictureMaker(files)
    made = maker.refresh(job_id)
    assert made["total"] == 3 and made["ready"] == 3
    first = files.preview_image(job_id, made["revision"], 1)
    assert first.read_bytes().startswith(b"\xff\xd8")
    assert maker.status(job_id, 3)["ready"] == 3
    document.write_bytes(pdf_bytes((500,)))
    again = maker.refresh(job_id)
    assert again["revision"] != made["revision"] and again["ready"] == 1
    assert not first.exists()
    assert files.preview_image(job_id, again["revision"], 1).is_file()


def test_the_counter_is_given_a_picture_it_can_keep(tmp_path):
    with running(tmp_path) as (client, _ctx, _cups):
        assert client.post("/upload", files={"file": ("letter.pdf", pdf_bytes((200, 300)), "application/octet-stream")}).status_code == 201
        job = _wait_ready(client, "letter.pdf")
        pics = _wait_pictures(client, job["id"])
        page = client.get(f"/admin/jobs/{job['id']}/previews/1", params={"v": pics["revision"]})
        assert page.status_code == 200 and page.content.startswith(b"\xff\xd8")
        assert "immutable" in page.headers["cache-control"]
        assert client.get(f"/admin/jobs/{job['id']}/previews/2", params={"v": pics["revision"]}).status_code == 200
        assert client.get(f"/admin/jobs/{job['id']}/previews/1", params={"v": "deadbeef"}).status_code == 404
        again = client.get(f"/admin/jobs/{job['id']}/previews/1", params={"v": pics["revision"]})
        assert again.status_code == 200 and again.content == page.content


def _wait_ready(client, name):
    deadline = time.time() + 5
    while time.time() < deadline:
        found = next((job for job in client.get("/admin/jobs").json()["jobs"] if job["name"] == name), None)
        if found and found["status"] == "ready":
            return found
        time.sleep(0.05)
    raise AssertionError(name)
