"""Device manager: discovery, reconnect, applying states and direct control."""
from __future__ import annotations

import asyncio
from typing import Any

from luxafor.core.config import safe_get
from luxafor.core.database import Database
from luxafor.core.events import EventBus
from luxafor.core.logging_setup import get_logger
from luxafor.hardware import discovery
from luxafor.hardware.hidraw_native import HidrawDevice, discover_native
from luxafor.hardware.base import (
    Led,
    LedCommand,
    WAVE_RANGE,
    PATTERN_RANGE,
    clamp8,
    dim_rgb,
    format_color,
    parse_color,
)
from luxafor.hardware.flag import FlagHidDevice
from luxafor.hardware.simulator import SimulatorDevice

log = get_logger("devices")


def _topology_of(dev: Any) -> str:
    """Ermittelt den USB-Topologie-String einer Geräte-Instanz (deduplication)."""
    try:
        path = dev.path
        if path:
            return str(path)
    except AttributeError:
        pass
    return ""


def looks_new(dev: Any, seen: dict[str, Any]) -> bool:
    topo = _topology_of(dev)
    for other in seen.values():
        if _topology_of(other) == topo and topo:
            return False
    return True


class DeviceManager:
    """Owns all Luxafor devices. The state engine and the API both go through
    this class so that reconnect logic, brightness and multi-device handling
    are implemented in exactly one place."""

    def __init__(self, db: Database, bus: EventBus) -> None:
        self.db = db
        self.bus = bus
        self.devices: dict[str, Any] = {}   # dict[str, LuxaforDevice|SimulatorDevice]
        self._sim_devices: dict[str, SimulatorDevice] = {}
        self._discovery_cache: dict[str, Any] = {}  # id → device instance (scan-stabil)
        self._scan_task: asyncio.Task | None = None
        self._flash_tasks: dict[str, asyncio.Task] = {}
        self._stopping = False
        self._last_color: dict[str, tuple[int, int, int]] = {}
        self._last_state: tuple[str, str] = ("#000000", "solid")

    # -- lifecycle -----------------------------------------------------------
    async def start(self) -> None:
        self._scan_now()
        interval = int(safe_get(self.db.get_all_settings(), "hardware.reconnect_interval", "5"))
        self._scan_task = asyncio.create_task(self._scan_loop(max(2, interval)))
        log.info("device manager started (%d device(s))", len(self.devices))

    async def stop(self) -> None:
        self._stopping = True
        if self._scan_task:
            self._scan_task.cancel()
        for dev in list(self.devices.values()):
            dev.close()
        for t in self._flash_tasks.values():
            t.cancel()
        log.info("device manager stopped")

    def _simulator_mode(self) -> str:
        return safe_get(self.db.get_all_settings(), "hardware.simulator", "auto")

    def _scan_now(self) -> None:
        """One discovery pass: open new devices, refresh metadata."""
        seen: dict[str, Any] = {}
        enumerated_count = 0
        mode = self._simulator_mode()
        if mode != "force":
            # 1) nativer hidraw-Zugriff (ehrliche errno, kein libusb-Umweg).
            #    Instanzen werden pro Geräte-ID gecached, damit der Scan nicht
            #    jedes Mal ein neues fd-Handle öffnet (fd-Leak).
            for node, vid, pid, hid_name, topology in discover_native():
                enumerated_count += 1
                ident = f"flag:{topology or node.replace('/dev/', '')}"
                dev = self._discovery_cache.get(ident)
                if dev is None:
                    dev = HidrawDevice(node, vid, pid, hid_name, topology)
                    self._discovery_cache[ident] = dev
                if node != dev.path:
                    dev.path = node  # hidraw-Nummer verschiebt sich nach Replug
                if not dev.is_open:
                    try:
                        dev.open()
                    except OSError as exc:
                        dev.last_error = str(exc)
                        log.warning("cannot open %s: %s", node, exc)
                if dev.is_open:
                    dev.last_error = None
                seen[dev.device_id] = dev
            # 2) hidapi nur als Fallback, falls die sysfs-Native-Erkennung nichts findet
            if not seen and discovery.hid is not None:
                for dev in discovery.enumerate_luxafor(discovery.hid):
                    enumerated_count += 1
                    ident = dev.device_id
                    cached = self._discovery_cache.get(ident)
                    if cached is not None:
                        dev = cached
                    else:
                        self._discovery_cache[ident] = dev
                    try:
                        if not dev.is_open:
                            dev.open()
                    except Exception as exc:
                        dev.last_error = str(exc)
                        log.warning("cannot open (hidapi) device %s: %s", ident, exc)
                    seen[ident] = dev
        use_sim = mode == "force" or (mode == "auto" and enumerated_count == 0)
        if use_sim:
            if not self._sim_devices:
                sim = SimulatorDevice("sim:0")
                sim.open()
                self._sim_devices[sim.device_id] = sim
            for sim in self._sim_devices.values():
                if not sim.is_open:
                    sim.open()
                seen[sim.device_id] = sim
        elif self._sim_devices:
            for sim in list(self._sim_devices.values()):
                sim.close()
            self._sim_devices.clear()

        removed = set(self.devices) - set(seen)
        for did in removed:
            if did not in self._flash_tasks:  # keep flashed temp handles alive
                self.devices[did].close()
                del self.devices[did]
                self.bus.publish("device", {"action": "removed", "id": did})
                log.info("device removed: %s", did)
                self._discovery_cache.pop(did, None)
        added = set(seen) - set(self.devices)
        for did, dev in seen.items():
            if did not in self.devices:
                self.devices[did] = dev
                self.bus.publish("device", {"action": "add", "device": dev.info()})
                log.info("device added: %s (%s)", did, dev.model)

    async def _scan_loop(self, interval: int) -> None:
        while not self._stopping:
            await asyncio.sleep(interval)
            try:
                for did, dev in list(self.devices.items()):
                    if isinstance(dev, SimulatorDevice):
                        continue
                    if not dev.is_open:
                        try:
                            dev.open()
                            self.bus.publish("device", {"action": "reconnect", "id": did})
                            log.info("reconnected device %s", did)
                            # re-apply the last logical state after a drop
                            if self._last_state[0] and self._last_state[0] != "#000000":
                                self.apply_state(*self._last_state)
                        except Exception as exc:
                            dev.last_error = str(exc)
                self._scan_now()
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("device scan loop error")

    # -- state application ----------------------------------------------------
    @property
    def brightness(self) -> int:
        return clamp8(int(safe_get(self.db.get_all_settings(), "hardware.brightness", "100")))

    def apply_color(self, rgb: tuple[int, int, int], led: Led = Led.ALL,
                    device_ids: list[str] | None = None) -> bool:
        """Sets a solid color (the device manager dims according to settings)."""
        rgb = dim_rgb(rgb, self.brightness)
        targets = self._targets(device_ids)
        ok = bool(targets)
        for dev in targets:
            if dev.is_open and dev.write(LedCommand(kind="color", rgb=rgb, led=led)):
                if led in (Led.ALL, Led.FRONT, Led.BACK):
                    self._last_color[dev.device_id] = rgb
            else:
                ok = False
        self.bus.publish("led", {"color": format_color(rgb), "led": str(led)})
        return ok

    def apply_off(self, device_ids: list[str] | None = None) -> bool:
        targets = self._targets(device_ids)
        ok = bool(targets)
        for dev in targets:
            if dev.is_open and not dev.write(LedCommand(kind="off")):
                ok = False
            self._last_color[dev.device_id] = (0, 0, 0)
        self.bus.publish("led", {"color": "#000000", "led": "off"})
        return ok

    def apply_state(self, color: str | tuple[int, int, int], effect: str,
                    led: Led = Led.ALL, device_ids: list[str] | None = None) -> bool:
        """Applies a full logical state (color + effect). Solid/off effects map
        directly; waves/patterns/strobes use the documented device commands."""
        rgb = parse_color(color) if isinstance(color, str) else tuple(color)
        if effect in ("off", "solid", ""):
            if effect == "off":
                self._last_state = ("#000000", "solid")
                return self.apply_off(device_ids)
            self._last_state = (format_color(dim_rgb(rgb, self.brightness)), "solid")
            return self.apply_color(rgb, led, device_ids)
        targets = self._targets(device_ids)
        ok = bool(targets)
        for dev in targets:
            cmd = self._effect_command(effect, rgb)
            if cmd is None or not dev.is_open or not dev.write(cmd):
                ok = False
            else:
                self._last_color[dev.device_id] = rgb
        self._last_state = (format_color(rgb), effect)
        self.bus.publish("led", {"color": format_color(rgb), "effect": effect})
        return ok

    @staticmethod
    def _effect_command(effect: str, rgb: tuple[int, int, int], led: Led = Led.ALL) -> LedCommand | None:
        """Encodes a logical effect ('solid', 'off', 'wave[:type[:delay]]',
        'pattern[:id]', 'strobe[:speed[:repeat]]') into a hardware command.
        Returns None for unknown effects so callers can reject them up front."""
        if not effect:
            return None
        base = effect.split(":")[0]
        if base not in ("solid", "off", "wave", "pattern", "strobe"):
            return None
        if effect == "solid":
            return LedCommand(kind="color", rgb=rgb, led=led)
        if effect == "off":
            return LedCommand(kind="off")
        try:
            parts = effect.split(":")
            if base == "strobe":
                speed = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 4
                repeat = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                if speed < 0 or speed > 255 or repeat < 0 or repeat > 255:
                    return None
                return LedCommand(kind="strobe", rgb=rgb, led=led, speed=speed, repeat=repeat)
            if base == "wave":
                wtype = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
                delay = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
                if wtype not in WAVE_RANGE:
                    return None
                return LedCommand(kind="wave", rgb=rgb, wave_type=wtype, wave_delay=clamp8(delay), repeat=0)
            if base == "pattern":
                pid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 4
                if pid not in PATTERN_RANGE:
                    return None
                return LedCommand(kind="pattern", pattern_id=pid, repeat=0)
        except ValueError:
            return None
        return None

    def known_effects(self) -> list[dict]:
        return [
            {"id": "solid", "name": "Dauerlicht", "doc": "Static color"},
            {"id": "off", "name": "Aus", "doc": "All LEDs off"},
            {"id": "strobe:4", "name": "Blinken (Strobe)", "doc": "Speed 0..255, repeat 0..255"},
            {"id": "wave:2", "name": "Welle", "doc": "Types 1..5, delay in s"},
            {"id": "pattern:4", "name": "Pattern", "doc": "Patterns 1..7 predefined by firmware"},
        ]

    # -- direct device control (GUI/API) -------------------------------------
    def device_infos(self) -> list[dict]:
        out = []
        for dev in self.devices.values():
            info = dev.info()
            info["color"] = format_color(self._last_color.get(dev.device_id, (0, 0, 0)))
            out.append(info)
        return out

    def _targets(self, device_ids: list[str] | None) -> list[Any]:
        if device_ids:
            return [self.devices[d] for d in device_ids if d in self.devices]
        return [d for d in self.devices.values() if isinstance(d, SimulatorDevice) or d.is_open]

    async def flash(self, color: str, duration: float = 5.0,
                    effect: str = "strobe:4", device_ids: list[str] | None = None,
                    restore_state: tuple[str, str] | None = None) -> bool:
        """Temporary notification effect; restores the previous state afterwards."""
        targets = self._targets(device_ids)
        if not targets:
            return False
        rgb = parse_color(color)
        restore = restore_state or self._current_state_string()
        for dev in targets:
            cmd = self._effect_command(effect, rgb)
            if cmd:
                dev.write(cmd)
        token = "+".join(d.device_id for d in targets)

        async def _restore() -> None:
            try:
                await asyncio.sleep(max(0.5, duration))
                # state engine value wins; here we only restore the visual backup
                if restore != ("#000000", "solid"):
                    self.apply_state(restore[0], restore[1])
                else:
                    self.apply_off()
                self._flash_tasks.pop(token, None)
            except asyncio.CancelledError:
                pass

        old = self._flash_tasks.get(token)
        if old:
            old.cancel()
        self._flash_tasks[token] = asyncio.create_task(_restore())
        return True

    def _current_state_string(self) -> tuple[str, str]:
        return self._last_state

    def test_device(self, device_id: str | None = None) -> bool:
        """Hardware smoke test: red → green → blue → off."""
        dids = [device_id] if device_id else None
        seq = [(0xFF, 0x00, 0x00), (0x00, 0xFF, 0x00), (0x00, 0x00, 0xFF)]
        ok = True
        for rgb in seq:
            ok = self.apply_color(rgb, Led.ALL, dids) and ok
        self.apply_off(dids)
        return ok

    def zone_names(self) -> list[str]:
        return ["all", "front", "back", "1", "2", "3", "4", "5", "6"]