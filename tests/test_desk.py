"""A phone can learn the shop name, and nothing else about the wifi."""

from tests.support import running


def test_a_phone_learns_the_shop_name_and_not_the_password(tmp_path):
    with running(tmp_path, client_host="10.42.0.8") as (phone, ctx, _cups):
        (ctx.settings.data_dir / "wifi").write_text("ssid=Hill Prints\npassword=printo123\n", encoding="utf-8")
        body = phone.get("/shop").json()
        assert body["ok"] is True and body["name"] == "Hill Prints" and "password" not in body
        assert "printo123" not in phone.get("/shop").text
        page = phone.get("/")
        assert "Connected to Hill Prints" in page.text and "printo123" not in page.text
