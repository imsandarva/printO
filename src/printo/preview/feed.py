"""The live nudge the counter already listens for, plus a quiet note when its files change."""

import json
import queue
import threading


class Hub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: list[queue.Queue[bytes]] = []

    def subscribe(self) -> queue.Queue[bytes]:
        box: queue.Queue[bytes] = queue.Queue(maxsize=64)
        with self._lock:
            self._subs.append(box)
        return box

    def unsubscribe(self, box: queue.Queue[bytes]) -> None:
        with self._lock:
            if box in self._subs:
                self._subs.remove(box)

    def publish(self, event: str, payload: dict) -> None:
        packed = pack(event, payload)
        with self._lock:
            boxes = tuple(self._subs)
        for box in boxes:
            _offer(box, packed)


def pack(event: str, payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n".encode()


def _offer(box: queue.Queue[bytes], packed: bytes) -> None:
    # A slow page misses a beat. The job list is still the record, same as the shop.
    try:
        box.put_nowait(packed)
    except queue.Full:
        pass
