"""Tiny async event bus connecting hardware, integrations and API."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from luxafor.core.logging_setup import get_logger

log = get_logger("events")


@dataclass
class Event:
    kind: str                 # e.g. "state", "presence", "device", "calendar", "log"
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[tuple[str | None, asyncio.Queue[Event]]] = []
        self._closed = False

    def subscribe(self, kind: str | None = None) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        self._subscribers.append((kind, q))
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        self._subscribers = [(k, qq) for k, qq in self._subscribers if qq is not q]

    def publish(self, kind: str, data: dict[str, Any] | None = None) -> None:
        ev = Event(kind, data or {})
        for k, q in list(self._subscribers):
            if k is None or k == kind:
                try:
                    q.put_nowait(ev)
                except asyncio.QueueFull:
                    log.warning("event queue overflow for kind=%s", kind)

    async def events(self, kinds: list[str] | None = None) -> AsyncIterator[Event]:
        q = self.subscribe()
        try:
            while True:
                ev = await q.get()
                if ev.kind == "_closed":
                    return
                if kinds is None or ev.kind in kinds:
                    yield ev
        finally:
            self.unsubscribe(q)

    def close(self) -> None:
        self.publish("_closed", {})