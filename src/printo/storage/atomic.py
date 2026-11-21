"""Crash-safe writes. A power cut should leave the old file or the new one, not a torn half."""

import os
import shutil
from pathlib import Path


def fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def copy_sealed(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + ".partial")
    with src.open("rb") as source, temporary.open("wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, dest)
    fsync_dir(dest.parent)


def replace(src: Path, dest: Path) -> None:
    with src.open("rb+") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dest)
    fsync_dir(dest.parent)
