"""Outlook calendar synchronization (Graph /me/calendarview)."""
from __future__ import annotations

import asyncio
import datetime as dt

from luxafor.core.logging_setup import get_logger
from luxafor.integrations.base import Integration
from luxafor.integrations.msgraph.client import GraphClient, GraphError

log = get_logger("calendar")

BUSY_SHOW_AS = {"busy", "oof"}


class CalendarSyncer(Integration):
    """Watches upcoming meetings and drives meeting/buffer candidates.

    Timeline logic: a meeting starting at 10:00 (with 5 min buffer) switches
    the LED to the buffer color at 09:55, to the meeting color at 10:00 and
    hands back to Teams at 11:00. Boundary changes are implemented via
    candidate expiry so no extra polling tick is needed.
    """

    name = "outlook"
    title = "Outlook Kalender"
    description = "Berücksichtigt aktuelle und bevorstehende Termine."

    def __init__(self, context) -> None:
        super().__init__(context)
        self._task: asyncio.Task | None = None
        self.upcoming: list[dict] = []
        self._last_ok = None
        self._last_error: str | None = None
        self._last_hint: str | None = None

    @property
    def client(self) -> GraphClient:
        return self.ctx.graph_client

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
        tick = 0
        while True:
            try:
                await asyncio.sleep(30 if tick else 1)
                tick += 1
                settings = self.ctx.db.get_all_settings()
                if settings.get("calendar.enabled", "false") != "true":
                    continue
                scope = int(settings.get("calendar.scope_minutes", "1440") or 1440)
                events = await self.client.calendarview(minutes_ahead=scope, look_back=15)
                self._last_ok = dt.datetime.now()
                self._last_error = None
                self._last_hint = None
                self.upcoming = self._normalize(events, settings)
                await self._apply(settings)
                self.ctx.bus.publish("calendar", {"upcoming": self.upcoming[:10]})
            except asyncio.CancelledError:
                return
            except GraphError as exc:
                self._last_error = str(exc)
                self._last_hint = exc.hint
                self.ctx.bus.publish("calendar_error", {"error": str(exc), "hint": exc.hint})
                await asyncio.sleep(60)
            except Exception:
                log.exception("calendar loop error")
                await asyncio.sleep(60)

    def _normalize(self, events: list[dict], settings: dict) -> list[dict]:
        out = []
        hide_private = settings.get("calendar.hide_private", "true") == "true"
        for e in events:
            try:
                start = dt.datetime.fromisoformat(e["start"]["dateTime"].replace("Z", "+00:00"))
                end = dt.datetime.fromisoformat(e["end"]["dateTime"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            show_as = (e.get("showAs") or "").lower()
            if show_as not in BUSY_SHOW_AS:
                continue
            private = (e.get("sensitivity") or "").lower() in ("private", "confidential")
            title = None
            if not hide_private or not private:
                title = e.get("subject") or "Termin"
            if private and hide_private:
                title = "Termin (privat)"  # busy without contents
            out.append({
                "title": title,
                "start": start,
                "end": end,
                "private": private,
                "is_all_day": bool(e.get("isAllDay")),
            })
        out.sort(key=lambda ev: ev["start"])
        return out

    async def _apply(self, settings: dict) -> None:
        now = dt.datetime.now(dt.UTC)
        buf_before = max(0, int(settings.get("calendar.buffer_before", "5") or 0))
        buf_after = max(0, int(settings.get("calendar.buffer_after", "0") or 0))

        meeting = None          # event containing 'now' (busy window)
        buffer_event = None     # next event starting within buffer_before
        for ev in self.upcoming:
            eff_start = ev["start"] - dt.timedelta(minutes=buf_before)
            eff_end = ev["end"] + dt.timedelta(minutes=buf_after)
            if eff_start <= now < eff_end:
                meeting = ev
                break
        if meeting is None:
            for ev in self.upcoming:
                if ev["end"] <= now:
                    continue
                delta_min = (ev["start"] - now).total_seconds() / 60
                if delta_min <= buf_before and buf_before > 0:
                    buffer_event = ev
                break

        conflict = settings.get("presence.conflict_policy", "teams_after_meeting")
        prio_meeting = int(settings.get("calendar.priority_meeting", "70"))
        prio_buffer = int(settings.get("calendar.priority_buffer", "55"))
        if conflict == "teams_wins":
            prio_meeting = min(prio_meeting, 35)
            prio_buffer = min(prio_buffer, 35)

        context = {"calendar": {
            "meeting": bool(meeting),
            "meeting_title": meeting["title"] if meeting else None,
            "buffer": bool(buffer_event),
            "next_time": buffer_event["start"].strftime("%H:%M") if buffer_event else None,
            "next_title": buffer_event["title"] if buffer_event else None,
        }}
        # precise expiry: hand back control to Teams exactly at the boundary
        expiry = {}
        if meeting:
            expiry["calendar:meeting"] = (meeting["end"] + dt.timedelta(minutes=buf_after)).timestamp()
        if buffer_event:
            expiry["calendar:buffer"] = buffer_event["start"].timestamp()
        await self.ctx.apply_context("meeting", context, expires=expiry)

    def status(self) -> dict:
        return {
            "upcoming": [
                {**{k: (v.isoformat() if isinstance(v, dt.datetime) else v)
                     for k, v in ev.items()}} for ev in self.upcoming[:10]
            ],
            "last_error": self._last_error,
            "hint": self._last_hint,
            "next": (self.upcoming[0]["start"].isoformat() if self.upcoming else None),
        }