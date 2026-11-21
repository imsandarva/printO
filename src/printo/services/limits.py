"""Stop a phone, or a burst of phones, from filling the disk."""

import shutil
import threading
import time
from collections import deque

from printo.config import Settings
from printo.errors import UserError
from printo.messages import disk_full, rate_limited
from printo.storage.files import Files


class Limits:
    def __init__(self, settings: Settings, files: Files) -> None:
        self.settings = settings
        self.files = files
        self._lock = threading.Lock()
        self._per_ip: dict[str, deque[float]] = {}
        self._global: deque[float] = deque()

    def allow(self, ip: str) -> None:
        self._disk()
        self._rate(ip or "unknown")

    def _disk(self) -> None:
        target = self.files.root if self.files.root.exists() else self.files.root.parent
        free = shutil.disk_usage(target).free
        needed = self.settings.min_free_bytes + self.settings.max_upload_bytes
        if free < needed:
            raise UserError(disk_full(), 507)

    def _rate(self, ip: str) -> None:
        now = time.monotonic()
        window = self.settings.upload_window_seconds
        with self._lock:
            self._prune(self._global, now, window)
            bucket = self._per_ip.setdefault(ip, deque())
            self._prune(bucket, now, window)
            if not bucket:
                self._per_ip.pop(ip, None)
                bucket = self._per_ip.setdefault(ip, deque())
            if len(bucket) >= self.settings.uploads_per_ip or len(self._global) >= self.settings.uploads_global:
                raise UserError(rate_limited(), 429)
            bucket.append(now)
            self._global.append(now)

    def _prune(self, bucket: deque[float], now: float, window: int) -> None:
        while bucket and now - bucket[0] > window:
            bucket.popleft()
