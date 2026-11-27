"""The counter's Stop control must never cancel or queue another page."""

import time

from tests.support import FakeCups, pdf_bytes, running


def test_stop_finishes_one_page_then_continue_and_reprint_last(tmp_path):
    cups = FakeCups()
    cups.hold = True
    with running(tmp_path, cups=cups) as (client, _ctx, cups):
        assert client.post("/upload", files={"file": ("letter.pdf", pdf_bytes((200, 300)), "application/pdf")}).status_code == 201
        job = _wait(client, "letter.pdf", {"ready"})
        assert client.post(f"/admin/jobs/{job['id']}/print", json={"copies": 2}).status_code == 200
        printing = _wait(client, "letter.pdf", {"printing"})
        _wait_submissions(cups, 1)
        assert printing["print_total"] == 4 and len(cups.submitted) == 1

        stopping = client.post(f"/admin/jobs/{job['id']}/stop")
        assert stopping.status_code == 200 and stopping.json()["job"]["status"] == "stopping"
        active = cups.submitted[0][2]
        cups.jobs[active] = "completed"
        stopped = _wait(client, "letter.pdf", {"stopped"})
        assert stopped["print_done"] == 1 and len(cups.submitted) == 1 and cups.cancelled == []

        assert client.post(f"/admin/jobs/{job['id']}/reprint-last").status_code == 200
        _wait_submissions(cups, 2)
        assert cups.submitted[1][0].endswith("page-0001.pdf")
        cups.hold = False
        assert client.post(f"/admin/jobs/{job['id']}/continue").status_code == 409
        # The reprint is active, so complete it before continuing the remaining pages.
        cups.jobs[cups.submitted[1][2]] = "completed"
        stopped_again = _wait(client, "letter.pdf", {"stopped"})
        assert stopped_again["print_done"] == 1
        assert client.post(f"/admin/jobs/{job['id']}/continue").status_code == 200
        done = _wait(client, "letter.pdf", {"done"})
        assert done["print_done"] == 4 and len(cups.submitted) == 5


def test_trash_uses_the_same_safe_stop_boundary(tmp_path):
    cups = FakeCups()
    cups.hold = True
    with running(tmp_path, cups=cups) as (client, _ctx, cups):
        assert client.post("/upload", files={"file": ("letter.pdf", pdf_bytes((200, 300)), "application/pdf")}).status_code == 201
        job = _wait(client, "letter.pdf", {"ready"})
        assert client.post(f"/admin/jobs/{job['id']}/print", json={"copies": 2}).status_code == 200
        _wait_submissions(cups, 1)
        assert client.post(f"/admin/jobs/{job['id']}/trash").status_code == 200
        cups.jobs[cups.submitted[0][2]] = "completed"
        stopped = _wait_trash(client, "letter.pdf", {"stopped"})
        assert stopped["print_done"] == 1 and len(cups.submitted) == 1 and cups.cancelled == []


def _wait(client, name, statuses, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        jobs = client.get("/admin/jobs").json()["jobs"]
        job = next((item for item in jobs if item["name"] == name), None)
        if job and job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"{name} did not reach {statuses}")


def _wait_submissions(cups, count, seconds=2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if len(cups.submitted) >= count:
            return
        time.sleep(0.02)
    raise AssertionError(f"only {len(cups.submitted)} pages were sent")


def _wait_trash(client, name, statuses, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        jobs = client.get("/admin/jobs?trashed=1").json()["jobs"]
        job = next((item for item in jobs if item["name"] == name), None)
        if job and job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"{name} did not reach {statuses} in Trash")
