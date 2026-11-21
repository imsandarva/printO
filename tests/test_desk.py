"""The counter tells a customer how to join, and then which address to open."""

from printo.desk import desk_message
from printo.messages import front_desk
from tests.support import running


def test_the_counter_says_how_to_connect(tmp_path):
    address = "http://10.42.0.1:8088/"
    with running(tmp_path) as (client, ctx, _cups):
        (ctx.settings.data_dir / "wifi").write_text(f"ssid=printO\npassword=printo123\naddress={address}\n", encoding="utf-8")
        body = client.get("/admin/front").json()
        assert body["ok"] is True
        assert body["message"] == front_desk("printO", "printo123", address)
        assert "on its own" not in body["message"]
        assert address in body["message"]
    assert address in desk_message(tmp_path / "data")


def test_a_phone_learns_the_shop_name_and_not_the_password(tmp_path):
    with running(tmp_path, client_host="10.42.0.8") as (phone, ctx, _cups):
        (ctx.settings.data_dir / "wifi").write_text("ssid=Hill Prints\npassword=printo123\n", encoding="utf-8")
        body = phone.get("/shop").json()
        assert body["ok"] is True and body["name"] == "Hill Prints" and "password" not in body
        assert "printo123" not in phone.get("/shop").text
        page = phone.get("/")
        assert "Connected to Hill Prints" in page.text and "printo123" not in page.text


def test_a_phone_cannot_read_the_counter_note(tmp_path):
    with running(tmp_path, client_host="10.42.0.8") as (phone, ctx, _cups):
        (ctx.settings.data_dir / "wifi").write_text("ssid=printO\npassword=printo123\n", encoding="utf-8")
        denied = phone.get("/admin/front")
        assert denied.status_code == 404
