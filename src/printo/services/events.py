"""A nudge for the shop screen. The job list is the source of truth; this stream can drop a beat."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from printo.domain.job import Job
from printo.messages import connected, present, removed_event

log = logging.getLogger("printo.events")


class Events:
    def __init__(self, heartbeat: float) -> None:
        self.heartbeat = heartbeat
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subs: set[asyncio.Queue[dict]] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish_job(self, job: Job) -> None:
        self._send(present(job))

    def publish_removed(self, job_id: str) -> None:
        self._send(removed_event(job_id))

    def subscribe(self) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=32)
        self._subs.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        self._subs.discard(queue)

    async def stream(self) -> AsyncIterator[str]:
        queue = self.subscribe()
        try:
            yield _pack("ready", {"message": connected()})
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=self.heartbeat)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _pack("job", payload)
        finally:
            self.unsubscribe(queue)

    def _send(self, payload: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._fanout(payload)
        else:
            loop.call_soon_threadsafe(self._fanout, payload)

    def _fanout(self, payload: dict) -> None:
        for queue in tuple(self._subs):
            if queue.full():
                log.debug("dropped a live update; the job list is still complete")
                continue
            queue.put_nowait(payload)


def _pack(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
