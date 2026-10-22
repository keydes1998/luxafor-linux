"""Teams presence synchronization (Graph /me/presence polling)."""
from __future__ import annotations

import asyncio

from luxafor.core.logging_setup import get_logger
from luxafor.integrations.base import Integration
from luxafor.integrations.msgraph.client import GraphClient, GraphError

log = get_logger("presence")

MAX_BACKOFF = 60.0


class PresenceSyncer(Integration):
    """Polls /me/presence and pushes it through the rule engine.

    Graph change notifications (webhooks) require a publicly reachable HTTPS
    endpoint and are therefore not used; adaptive polling keeps reaction fast
    and reliable on desktop Linux.
    """

    name = "teams"
    title = "Microsoft Teams Präsenz"
    description = "Synchronisiert den Teams-Anwesenheitsstatus auf die LED."

    def __init__(self, context) -> None:
        super().__init__(context)
        self.presence: dict | None = None
        self._task: asyncio.Task | None = None
        self._last_ok = None
        self._last_error: str | None = None
        self._last_err_hint: str | None = None
        self.poll_count = 0

    @property
    def client(self) -> GraphClient:
        return self.ctx.graph_client

    # -- lifecycle -------------------------------------------------------------
    async def start(self) -> None:
        await super().start()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        await super().stop()
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        backoff = 2.0
        # initial quick poll, then the configured interval
        first = True
        while True:
            interval = self._interval_seconds()
            try:
                if first:
                    await asyncio.sleep(1)
                    first = False
                self.presence = await self.client.presence()
                self._last_ok = asyncio.get_event_loop().time()
                self._last_error = None
                self._last_err_hint = None
                self.poll_count += 1
                backoff = 2.0
                self.ctx.bus.publish("presence", dict(self.presence))
                await self.ctx.apply_context("presence", {"presence": self.presence})
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return
            except GraphError as exc:
                self._last_error = str(exc)
                self._last_err_hint = exc.hint
                self.ctx.engine.note_sync_result(False, str(exc))
                self.ctx.bus.publish("presence_error", {"error": str(exc), "hint": exc.hint})
                log.warning("presence poll fehlgeschlagen: %s (retry in %.0fs)", exc, min(backoff, 60))
                await asyncio.sleep(min(backoff, MAX_BACKOFF))
                backoff = min(backoff * 2, MAX_BACKOFF)
            except Exception:
                log.exception("presence loop error")
                await asyncio.sleep(min(backoff, MAX_BACKOFF))
                backoff = min(backoff * 2, MAX_BACKOFF)

    def _interval_seconds(self) -> int:
        try:
            return max(20, int(self.ctx.db.get_all_settings().get("sync.interval_seconds", "60")))
        except (TypeError, ValueError):
            return 60

    def sync_now(self):
        """Immediate re-poll (used after login or settings change)."""
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = asyncio.create_task(self._run())

    # -- status ------------------------------------------------------------------
    def status(self) -> dict:
        import time
        return {
            "presence": self.presence,
            "last_ok_epoch": self._last_ok,
            "last_error": self._last_error,
            "hint": self._last_err_hint,
            "poll_count": self.poll_count,
            "interval": self._interval_seconds(),
        }