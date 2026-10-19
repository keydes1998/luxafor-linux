"""State engine: merges status candidates by priority and drives the LED.

Every integration (manual control, Teams presence, Outlook calendar, schedule,
idle/lock detection, webhooks) contributes *candidates*. The engine picks the
highest-priority non-expired candidate and applies it to the device manager.

Default priority model (adjustable per rule/source):

    95 webhook (critical notification)
    90 manual override
    70 active Teams call / presentation
    70 Outlook meeting
    60 focus mode
    40 normal Teams presence
    30 automatic absence (idle)
    20 schedules
    10 standard color / offline
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from luxafor.core import config
from luxafor.core.database import Database
from luxafor.core.devices import DeviceManager
from luxafor.core.events import EventBus
from luxafor.core.logging_setup import get_logger

log = get_logger("state")


@dataclass
class Candidate:
    origin: str            # manual | presence | activity | meeting | buffer | schedule | idle | lock | webhook
    label: str
    color: str
    effect: str = "solid"
    priority: int = 40
    expires_at: float | None = None
    created_at: float = field(default_factory=time.time, compare=False)

    def fresh(self, now: float) -> bool:
        return self.expires_at is None or self.expires_at > now


class StateEngine:
    def __init__(self, db: Database, devices: DeviceManager, bus: EventBus) -> None:
        self.db = db
        self.devices = devices
        self.bus = bus
        self.candidates: dict[str, Candidate] = {}
        self.current: dict = {"color": "#000000", "effect": "solid", "origin": "none", "label": "—"}
        self.paused = False
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._last_sync_ok: float | None = None
        self._last_sync_err: str | None = None

    # -- lifecycle ------------------------------------------------------------
    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        self.request_recompute()

    async def stop(self) -> None:
        self._wakeup.set()
        if self._task:
            self._task.cancel()

    # -- candidates -----------------------------------------------------------
    def set_candidate(self, key: str, cand: Candidate) -> None:
        old = self.candidates.get(key)
        if old and old == cand:
            return
        self.candidates[key] = cand
        log.info("candidate %s: %s (%s, prio %d)", key, cand.color, cand.origin, cand.priority)
        self.db.log_activity("candidate", {"key": key, **cand.__dict__})
        self.request_recompute()

    def clear_candidate(self, key: str) -> None:
        if key in self.candidates:
            del self.candidates[key]
            log.info("candidate cleared: %s", key)
            self.db.log_activity("candidate_cleared", {"key": key})
            self.request_recompute()

    def set_paused(self, paused: bool) -> None:
        self.paused = bool(paused)
        self.bus.publish("state", {"paused": self.paused})
        self.db.log_activity("pause", {"paused": self.paused})
        self.request_recompute()

    def note_sync_result(self, ok: bool, error: str | None = None) -> None:
        if ok:
            self._last_sync_ok = time.time()
            self._last_sync_err = None
        else:
            self._last_sync_err = error
        self.bus.publish("sync", {"ok": ok, "error": error, "ts": self._last_sync_ok})

    # -- evaluation -----------------------------------------------------------
    def request_recompute(self) -> None:
        self._wakeup.set()

    def recompute_now(self) -> None:
        """Immediate synchronous evaluation (used by the API for fresh responses)."""
        self._evaluate()

    async def _run(self) -> None:
        while True:
            await self._wakeup.wait()
            self._wakeup.clear()
            self._evaluate()
            # wake again at the next candidate expiry
            now = time.time()
            expirations = [c.expires_at for c in self.candidates.values()
                           if c.expires_at is not None and c.expires_at > now]
            delay = min(expirations) - now if expirations else 30.0
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=max(0.5, min(delay, 60)))
            except asyncio.TimeoutError:
                pass

    def _evaluate(self) -> None:
        now = time.time()
        for k in [k for k, c in self.candidates.items() if not c.fresh(now)]:
            del self.candidates[k]
            log.info("candidate expired: %s", k)
        if self.paused:
            return
        if self.candidates:
            best_key = max(self.candidates,
                           key=lambda k: (self.candidates[k].priority, self.candidates[k].created_at))
            cand = self.candidates[best_key]
        else:
            best_key, cand = "default", self._default_candidate()
        self._apply(best_key, cand)

    def _default_candidate(self) -> Candidate:
        settings = self.db.get_all_settings()
        profile = self.db.active_profile()
        color = config.safe_get(settings, "default_color", "#00AA00")
        effect = config.safe_get(settings, "default_effect", "solid")
        if profile and profile.get("data", {}).get("default_color"):
            color = profile["data"]["default_color"]
            effect = profile["data"].get("default_effect", effect)
        return Candidate(origin="standard", label="Standardfarbe", color=color,
                         effect=effect, priority=int(config.safe_get(settings, "default_priority", "10")))

    def _apply(self, key: str, cand: Candidate) -> None:
        changed = (self.current.get("key") != key
                   or self.current.get("color") != cand.color
                   or self.current.get("effect") != cand.effect)
        if not changed:
            self.current["ts"] = time.time()
            return
        try:
            ok = self.devices.apply_state(cand.color, cand.effect)
        except Exception:
            ok = False
            log.exception("apply failed")
        self.current = {
            "key": key,
            "origin": cand.origin,
            "label": cand.label,
            "color": cand.color,
            "effect": cand.effect,
            "priority": cand.priority,
            "applied": ok,
            "ts": time.time(),
        }
        self.bus.publish("state", {**self.current})
        log.info("state -> %s %s [%s/%s]", cand.color, cand.effect, key, cand.origin)

    # -- manual control ---------------------------------------------------------
    async def manual_status(self, status_name: str | None, color: str | None = None,
                            effect: str | None = None, duration: float = 0) -> bool:
        """Manual override. Uses the status catalog when only a name is given."""
        statuses = {s["name"]: s for s in self.db.statuses()}
        preset = statuses.get(status_name or "")
        color = color or (preset["color"] if preset else None)
        effect = effect or (preset["effect"] if preset else "solid")
        if not color:
            return False
        expires = time.time() + duration if duration and duration > 0 else None
        self.set_candidate(
            "manual",
            Candidate(origin="manual", label=status_name or "Manuell", color=color,
                      effect=effect, priority=preset["priority"] if preset else 90,
                      expires_at=expires),
        )
        return True

    def restore_automatic(self) -> None:
        """'Automatischen Status wiederherstellen' — drops the manual override."""
        self.clear_candidate("manual")

    def manual_active(self) -> bool:
        c = self.candidates.get("manual")
        return bool(c and c.fresh(time.time()))

    # -- reporting --------------------------------------------------------------
    def snapshot(self) -> dict:
        now = time.time()
        return {
            "current": self.current,
            "paused": self.paused,
            "manual_active": self.manual_active(),
            "candidates": [
                {**c.__dict__, "key": k, "expired": not c.fresh(now)}
                for k, c in sorted(self.candidates.items(),
                                   key=lambda kv: (-kv[1].priority, kv[1].created_at))
            ],
            "last_sync_ok": self._last_sync_ok,
            "last_sync_error": self._last_sync_err,
            "profile": self.db.active_profile()["name"] if self.db.active_profile() else None,
        }