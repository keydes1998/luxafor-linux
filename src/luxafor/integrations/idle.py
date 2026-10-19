"""Idle & screen-lock detection via D-Bus (logind / ScreenSaver services).

Uses jeepney (pure Python). If D-Bus is unavailable the integration disables
itself and reports the reason in diagnostics — manual control keeps working.
"""
from __future__ import annotations

import asyncio

from luxafor.core.logging_setup import get_logger
from luxafor.integrations.base import Integration

log = get_logger("idlelock")

LOGIN1 = "org.freedesktop.login1"
LOGIN1_PATH = "/org/freedesktop/login1"
LOGIN1_IFACE = "org.freedesktop.login1.Manager"


class IdleLockWatcher(Integration):
    name = "desktop"
    title = "Desktop-Überwachung"
    description = "Bildschirmsperre und Benutzerinaktivität."

    def __init__(self, context) -> None:
        super().__init__(context)
        self._tasks: list[asyncio.Task] = []
        self.locked = False
        self.idle = False
        self.available_services: list[str] = []

    async def start(self) -> None:
        await super().start()
        self._tasks.append(asyncio.create_task(self._lock_loop()))
        self._tasks.append(asyncio.create_task(self._idle_loop()))

    async def stop(self) -> None:
        await super().stop()
        for t in self._tasks:
            t.cancel()
        self._tasks = []

    # -- lock/watchdog -----------------------------------------------------------
    async def _lock_loop(self) -> None:
        """Listens to login1 Lock/Unlock signals."""
        try:
            from jeepney.io.asyncio import open_dbus_connection
            from jeepney.bus_messages import message_bus
        except ImportError:
            log.info("jeepney not available; screen-lock rule disabled")
            return
        try:
            conn = await open_dbus_connection()  # system bus
        except Exception as exc:
            log.info("system D-Bus unavailable (%s); screen-lock rule disabled", exc)
            return

        from jeepney.low_level import Message
        rule = message_bus.MatchRule(type="signal", interface=LOGIN1_IFACE)
        msg_gen = conn.filter(rule)
        await conn.send_message(message_bus.AddMatch(rule))
        log.info("listening for lock/unlock signals")
        member = ""
        try:
            async for msg in msg_gen:
                member = msg.header.member or ""
                if not self.enabled:
                    continue
                if member == "Lock":
                    await self._set_locked(True)
                elif member == "Unlock":
                    await self._set_locked(False)
                elif member == "PrepareForSleep" and bool(msg.body[0] if msg.body else True):
                    await self._set_locked(True)
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("lock loop ended")

    async def _set_locked(self, locked: bool) -> None:
        if self.locked == locked:
            return
        self.locked = locked
        log.info("screen lock: %s", locked)
        self.ctx.bus.publish("lock", {"locked": locked})
        if locked:
            # candidate with a long expiry as a safety net (e.g. missed Unlock)
            timeout_min = self._setting_minutes("lock.timeout_minutes", 60)
            import time
            expires = time.time() + timeout_min * 60
            await self.ctx.apply_context(
                "lock", {"lock": True}, expires={"lock": expires})
        else:
            await self.ctx.apply_context("lock", {"lock": False})

    # -- idle ----------------------------------------------------------------------
    async def _idle_loop(self) -> None:
        """Polls the session idle time via org.freedesktop.ScreenSaver."""
        try:
            from jeepney.io.asyncio import open_dbus_connection
            from jeepney.bus_messages import message_bus
            from jeepney.low_level import MessageType
        except ImportError:
            log.info("jeepney not available; idle rule disabled")
            return
        try:
            conn = await open_dbus_connection("SESSION")
        except Exception as exc:
            log.info("session D-Bus unavailable (%s); idle rule disabled", exc)
            return
        services = [
            ("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver"),
            ("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver"),
        ]
        threshold_ms = await self._idle_threshold_ms()

        while True:
            try:
                idle_ms = None
                for name, path in services:
                    idle_ms = await self._ask_idle(conn, name, path)
                    if idle_ms is not None:
                        self.available_services = sorted(set(self.available_services) | {name})
                        break
                if not self._setting_enabled("idle.enabled", False) and self.idle:
                    self.idle = False
                    await self.ctx.apply_context("idle", {"idle": False})
                if idle_ms is not None and self._setting_enabled("idle.enabled", False):
                    target = idle_ms >= threshold_ms
                    if target != self.idle:
                        self.idle = target
                        log.info("idle state: %s (%d ms)", target, idle_ms)
                        self.ctx.bus.publish("idle", {"idle": target})
                        if target:
                            import time
                            expires = time.time() + 5 * 60  # re-evaluated by timer anyway
                            await self.ctx.apply_context(
                                "idle", {"idle": True}, expires={"idle": expires})
                        else:
                            await self.ctx.apply_context("idle", {"idle": False})
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(30)
            await asyncio.sleep(20)

    @staticmethod
    async def _ask_idle(conn, name: str, path: str) -> int | None:
        from jeepney.bus_messages import message_bus
        from jeepney.low_level import Message, MessageType
        msg = Message(MessageType.method_call, path, name,
                      "org.freedesktop.ScreenSaver", "GetSessionIdleTime",
                      body=())
        reply = await conn.send_message_and_get_reply(msg, timeout=5)
        if reply is not None and not reply.header.message_type == MessageType.error and reply.body:
            return int(reply.body[0])
        return None

    # -- settings helpers ------------------------------------------------------------
    def _settings(self) -> dict:
        return self.ctx.db.get_all_settings()

    def _setting_enabled(self, key: str, default: bool) -> bool:
        v = self._settings().get(key)
        return default if v is None else str(v).lower() == "true"

    def _setting_minutes(self, key: str, default: int) -> int:
        try:
            return int(self._settings().get(key, str(default)))
        except (TypeError, ValueError):
            return default

    async def _idle_threshold_ms(self) -> int:
        minutes = self._setting_minutes("idle.threshold_minutes", 10)
        return max(1, minutes * 60 * 1000)

    def status(self) -> dict:
        return {
            "locked": self.locked,
            "idle": self.idle,
            "idle_services": self.available_services,
        }