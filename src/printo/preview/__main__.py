"""Open the counter by itself. This only wires the pieces and runs them."""

import errno

from printo.preview.browser import open_browser
from printo.preview.serve import already_running, counter_url, listen_port, start
from printo.preview.shop import ensure_shop


def main() -> None:
    port = listen_port()
    url = counter_url(port)
    if already_running(port):
        _show(url, "The counter is already open.")
        return
    shop = ensure_shop()
    preview = None
    try:
        preview = start(port, shop_port=shop.port)
        extra = " It started printO in the background." if shop.spawned else ""
        _show(preview.url, f"The counter is open with the same files as the shop.{extra} Leave this window here while you change the page, and it will update on its own. Press Ctrl+C when you are done.")
        preview.wait()
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        _say("Something else is already using the counter's page. Close it, then try again.")
        raise SystemExit(1) from None
    finally:
        if preview is not None:
            preview.close()
        shop.close()


def _show(url: str, message: str) -> None:
    if not open_browser(url):
        message = f"{message} You can open it here: {url}"
    _say(message)


def _say(message: str) -> None:
    print(message, flush=True)


if __name__ == "__main__":
    main()