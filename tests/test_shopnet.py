"""The shop wifi has to answer a phone immediately, even with no internet behind it."""

import shutil
import signal
import socket
import subprocess
import time
from types import SimpleNamespace

import pytest

from printo.desk import desk_message
from printo.http.portal import portal_target
from printo.messages import front_desk
from printo.shopnet import dns_config, records
from tests.support import running


def test_a_phone_is_sent_to_port_80_when_the_shop_wifi_is_up():
    request = SimpleNamespace(
        scope={"server": ["10.42.0.1", 8088]},
        app=SimpleNamespace(state=SimpleNamespace(ctx=SimpleNamespace(settings=SimpleNamespace(public_port=80)))),
    )
    assert portal_target(request) == "http://10.42.0.1/"
    request.app.state.ctx.settings = SimpleNamespace(public_port=None)
    assert portal_target(request) == "http://10.42.0.1:8088/"


def test_the_counter_says_how_to_connect(tmp_path):
    with running(tmp_path) as (client, ctx, _cups):
        (ctx.settings.data_dir / "wifi").write_text("ssid=printO\npassword=printo123\naddress=10.42.0.1\n", encoding="utf-8")
        body = client.get("/admin/front").json()
        assert body["ok"] is True
        assert body["message"] == front_desk("printO", "printo123", "10.42.0.1")
    assert "10.42.0.1" in desk_message(tmp_path / "data")


def test_a_phone_cannot_read_the_counter_note(tmp_path):
    with running(tmp_path, client_host="10.42.0.8") as (phone, ctx, _cups):
        (ctx.settings.data_dir / "wifi").write_text("ssid=printO\npassword=printo123\n", encoding="utf-8")
        denied = phone.get("/admin/front")
        assert denied.status_code == 404


def test_names_answer_at_once_even_when_the_internet_does_not(tmp_path):
    if shutil.which("dnsmasq") is None:
        pytest.skip("dnsmasq is not installed")
    port = _free_port()
    conf = tmp_path / "printo.conf"
    conf.write_text(dns_config("10.42.0.1"), encoding="utf-8")
    proc = subprocess.Popen(
        ["dnsmasq", f"--conf-file={conf}", "--server=192.0.2.1", f"--port={port}", "--listen-address=127.0.0.1",
         "--no-daemon", "--bind-interfaces", "--no-hosts"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        found = _until(lambda: records("127.0.0.1", "captive.apple.com", "A", 0.4, port))
        other = records("127.0.0.1", "connectivitycheck.gstatic.com", "AAAA", 1.0, port)
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=3)
    assert found == ["10.42.0.1"]
    assert other == ["::"]


def _until(read):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        found = read()
        if found:
            return found
        time.sleep(0.05)
    return None


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port
