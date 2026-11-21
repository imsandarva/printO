"""The phone gets the send page. The counter stays on the laptop."""

from tests.support import running


def test_phone_sees_the_send_page_and_not_the_counter(tmp_path):
    with running(tmp_path, client_host="10.42.0.8") as (phone, _ctx, _cups):
        page = phone.get("/")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        assert "/admin" not in page.text
        assert phone.get("/c/customer.js").status_code == 200
        assert "Choose a file" in phone.get("/c/customer.js").text
        probe = phone.get("/hotspot-detect.html")
        assert probe.status_code == 200 and "text/html" in probe.headers["content-type"]
        assert "text/html" in phone.get("/generate_204").headers["content-type"]
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
        assert client.get("/c/customer.css").status_code == 200
        assert client.get("/c/nope.css").status_code == 404
        assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg")
        assert client.get("/admin").status_code == 200
