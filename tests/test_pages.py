"""The phone gets the send page. The counter stays on the laptop."""

from tests.support import running


def test_phone_sees_the_send_page_and_not_the_counter(tmp_path):
    with running(tmp_path, client_host="10.42.0.8") as (phone, _ctx, _cups):
        page = phone.get("/")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        assert "/admin" not in page.text
        assert "What would you like to print?" in page.text
        assert "Choose files" in page.text
        assert "Sandipa Stationery" in page.text
        assert "capture=\"environment\"" in page.text
        assert phone.get("/c/customer.js").status_code == 200
        assert phone.get("/c/transfer.js").status_code == 200
        assert "/upload" in phone.get("/c/transfer.js").text
        assert phone.get("/c/pdf.min.mjs").status_code == 200
        assert phone.get("/c/../common.css").status_code == 404
        assert "open your browser" not in page.text
        probe = phone.get("/hotspot-detect.html", follow_redirects=False)
        assert probe.status_code == 404 and probe.headers.get("location") is None
        assert "isn't available" in probe.json()["message"]
        again = phone.get("/generate_204", follow_redirects=False)
        assert again.status_code == 404 and again.headers.get("location") is None
        for path in ("/admin", "/admin/", "/admin/c/counter.js", "/admin/jobs"):
            denied = phone.get(path)
            assert denied.status_code == 404 and "isn't available" in denied.json()["message"]


def test_counter_page_is_served_on_the_laptop(tmp_path):
    with running(tmp_path) as (client, _ctx, _cups):
        page = client.get("/admin/")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        assert "/admin/c/counter.js" in page.text
        assert "default-src 'self'" in page.headers["content-security-policy"]
        script = client.get("/admin/c/counter.js")
        assert script.status_code == 200 and "Print" in script.text
        dates = client.get("/admin/c/dates.js")
        assert dates.status_code == 200 and "Today" in dates.text
        assert client.get("/c/customer.css").status_code == 200
        assert client.get("/c/nope.css").status_code == 404
        assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg")
        assert client.get("/admin/jobs").json()["max_copies"] == 100
        assert client.get("/admin").status_code == 200
