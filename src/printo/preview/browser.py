"""Open the counter the same way the shop does: its own window, apart from this one."""

import shutil
import subprocess

# Same order as scripts/common.sh. A new session so closing this window does not close the page.
_COMMANDS = (
    ("google-chrome", "--app={url}"),
    ("chromium", "--app={url}"),
    ("chromium-browser", "--app={url}"),
    ("firefox", "--new-window"),
    ("xdg-open",),
)


def open_browser(url: str) -> bool:
    for command in _COMMANDS:
        if shutil.which(command[0]) is None:
            continue
        _launch(command, url)
        return True
    return False


def _launch(command: tuple[str, ...], url: str) -> None:
    args = [part.format(url=url) for part in command]
    if command[0] == "firefox":
        args.append(url)
    elif command[0] == "xdg-open":
        args.append(url)
    subprocess.Popen(args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
