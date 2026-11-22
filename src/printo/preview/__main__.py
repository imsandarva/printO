"""Open the counter by itself. This only wires the pieces and runs them."""

import errno

from printo.preview.browser import open_browser
from printo.preview.serve import already_running, counter_url, listen_port, start


def main() -> None:
    port = listen_port()
    url = counter_url(port)
    if already_running(port):
        _show(url, "The counter is already open.")
        return
    try:
        preview = start(port)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        _say("Something else is already using the counter's page. Close it, then try again.")
        raise SystemExit(1) from None
    try:
        _show(preview.url, "The counter is open. Leave this window here while you change the page, and it will update on its own. Press Ctrl+C when you are done.")
        preview.wait()
    finally:
        preview.close()


def _show(url: str, message: str) -> None:
    if not open_browser(url):
        message = f"{message} You can open it here: {url}"
    _say(message)


def _say(message: str) -> None:
    print(message, flush=True)


if __name__ == "__main__":
    main()
