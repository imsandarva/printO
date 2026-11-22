"""Watch the counter's own files. A save is enough; nothing is copied or built."""

import threading
from pathlib import Path


def watch(paths: list[Path], emit, stop: threading.Event, pause: float = 0.35) -> None:
    seen = _stamp(paths)
    while not stop.wait(pause):
        current = _stamp(paths)
        if current == seen:
            continue
        # Editors often write twice. Wait out the second one, then say what changed.
        if stop.wait(0.12):
            return
        current = _stamp(paths)
        names = _changed(seen, current)
        seen = current
        if names:
            emit(names)


def _changed(before: tuple, after: tuple) -> list[str]:
    previous = {name: rest for name, *rest in before}
    return [name for name, *rest in after if previous.get(name) != rest]


def _stamp(paths: list[Path]) -> tuple:
    found = []
    for path in paths:
        found.append((path.name, *_mark(path)))
    return tuple(found)


def _mark(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
    except OSError:
        return 0, 0
    return stat.st_mtime_ns, stat.st_size
