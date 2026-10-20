"""Core daemon wiring: devices, state engine, rule engine, integrations, API.

Runs headless (systemd user service or manually). The PySide6 GUI/CLI talk to
it through the local REST API.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import signal
import socket
import time
from dataclasses import replace

from luxafor import __version__
from luxafor.core import config
from luxafor.core.database import Database
from luxafor.core.devices import DeviceManager
from luxafor.core.events import EventBus
from luxafor.core.logging_setup import get_logger
from luxafor.core.state import Candidate, StateEngine
from luxafor.rules.engine import RuleEngine
from luxafor.api.server import ApiServer
from luxafor.integrations.base import Integration, IntegrationRegistry
from luxafor.integrations.idle import IdleLockWatcher
from luxafor.integrations.webhooks import WebhookIntegration
from luxafor.integrations.msgraph import auth as msgraph_auth
from luxafor.integrations.msgraph.auth import AuthManager
from luxafor.integrations.msgraph.client import GraphClient
from luxafor.integrations.msgraph.presence import PresenceSyncer
from luxafor.integrations.msgraph.calendar import CalendarSyncer
from luxafor import hardware
from luxafor.hardware.base import LUXAFOR_VENDOR_ID, LUXAFOR_GEN2_VENDOR_ID

log = get_logger("core")

# keys managed by each apply_context category in the state engine
CATEGORY_KEYS = {
    "presence": ["presence"],
    "meeting": ["calendar:meeting", "calendar:buffer"],
    "lock": ["lock"],
    "idle": ["idle"],
}


class CoreApp:
    """Owns every subsystem. Also the 'ctx' object used by integrations."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db = Database(db_path) if db_path else Database()
        self.bus = EventBus()
        self.rules = RuleEngine(self.db)
        self.devices = DeviceManager(self.db, self.bus)
        self.state = StateEngine(self.db, self.devices, self.bus)
        self.auth = AuthManager(self.db.get_all_settings)
        self.graph_client = GraphClient(self.auth.get_token)
        self.presence_integration = PresenceSyncer(self)
        self.calendar_integration = CalendarSyncer(self)
        self.idlelock_integration = IdleLockWatcher(self)
        self.webhooks_integration = WebhookIntegration(self)
        self.registry = IntegrationRegistry()
        self.registry.register(self.presence_integration)
        self.registry.register(self.calendar_integration)
        self.registry.register(self.idlelock_integration)
        self.registry.register(self.webhooks_integration)
        self.api_server = ApiServer(self)
        self.api_port = config.DEFAULT_API_PORT
        self.api_host = "127.0.0.1"
        self.port_conflict = False
        self._tasks: list[asyncio.Task] = []
        self._started = time.time()
        self._stop_event: asyncio.Event | None = None
        self._schedule_task: asyncio.Task | None = None
        self.rules.seed_defaults()

    # -- lifecycle ---------------------------------------------------------------
    def request_shutdown(self) -> None:
        """Sauberer Shutdown (z. B. GUI 'Beenden' oder systemd stop)."""
        if self._stop_event is not None:
            self._stop_event.set()

    async def start(self) -> None:
        self._stop_event = asyncio.Event()
        await self.devices.start()
        await self.state.start()
        await self.api_server.start()
        settings = self.db.get_all_settings()
        # integrations with user-controlled enable flag
        if config.safe_get(settings, "sync.enabled", "true") == "true":
            await self.presence_integration.start()
        if config.safe_get(settings, "calendar.enabled", "false") == "true":
            await self.calendar_integration.start()
        await self.idlelock_integration.start()  # self-guards internally (D-Bus presence)
        await self.webhooks_integration.start()
        self._schedule_task = asyncio.create_task(self._schedule_loop())
        log.info("core started v%s", __version__)

    async def run(self) -> None:
        stop = self._stop_event or asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                pass
        await stop.wait()

    async def stop(self) -> None:
        for integ in self.registry.all():
            try:
                await integ.stop()
            except Exception:
                log.exception("integration stop failed: %s", integ.name)
        if self._schedule_task:
            self._schedule_task.cancel()
        await self.api_server.stop()
        await self.state.stop()
        await self.devices.stop()
        await self.graph_client.close()
        self.db.close()
        log.info("core stopped")

    # -- candidate bridge ----------------------------------------------------------
    async def apply_context(self, category: str, context: dict,
                            expires: dict[str, float] | None = None) -> dict[str, Candidate]:
        """Evaluates a context against the rule engine and updates the state
        engine's candidates for that category (set + clear)."""
        candidates = self.rules.evaluate(context)
        if expires:
            for key, ts in expires.items():
                if key in candidates:
                    candidates[key] = replace(candidates[key], expires_at=ts)
        keys = CATEGORY_KEYS.get(category, [category])
        for key in keys:
            if key in candidates:
                self.state.set_candidate(key, candidates[key])
            elif key in self.state.candidates:
                self.state.clear_candidate(key)
        return candidates

    async def _schedule_loop(self) -> None:
        """Re-evaluates time-based rules every minute and applies changes."""
        try:
            await asyncio.sleep(2)
            last_minute = -1
            while True:
                now = dt.datetime.now()
                if now.minute != last_minute:
                    last_minute = now.minute
                    cands = self.rules.evaluate({})
                    sched = {k: v for k, v in cands.items() if k.startswith("schedule:")}
                    old = [k for k in list(self.state.candidates) if k.startswith("schedule:")]
                    for k in old:
                        if k not in sched:
                            self.state.clear_candidate(k)
                    for k, v in sched.items():
                        self.state.set_candidate(k, v)
                settings = self.db.get_all_settings()
                # idle candidates need re-evaluation too (expiry fallback)
                await asyncio.sleep(max(5, 60 - now.second))
        except asyncio.CancelledError:
            pass

    # -- settings hooks ----------------------------------------------------------------
    def on_settings_changed(self, keys: list[str]) -> None:
        try:
            settings = self.db.get_all_settings()
            if "sync.interval_seconds" in keys or "ms.client_id" in keys or "ms.tenant" in keys:
                self.presence_integration.sync_now()
            if "sync.enabled" in keys:
                if config.safe_get(settings, "sync.enabled", "true") == "true":
                    asyncio.get_event_loop().create_task(self.presence_integration.start())
                else:
                    asyncio.get_event_loop().create_task(self.presence_integration.stop())
                    self.state.clear_candidate("presence")
            if "calendar.enabled" in keys:
                if config.safe_get(settings, "calendar.enabled", "false") == "true":
                    asyncio.get_event_loop().create_task(self.calendar_integration.start())
                else:
                    asyncio.get_event_loop().create_task(self.calendar_integration.stop())
                    self.state.clear_candidate("calendar:meeting")
                    self.state.clear_candidate("calendar:buffer")
            if "active_profile" in keys or "default_color" in keys:
                self.state.request_recompute()
            if "hardware.simulator" in keys:
                asyncio.get_event_loop().create_task(self._rescan_devices())
            if "hardware.reconnect_interval" in keys:
                asyncio.get_event_loop().create_task(self._rescan_devices())
        except RuntimeError:
            pass

    async def _rescan_devices(self) -> None:
        await self.devices.stop()
        self.devices._stopping = False
        await self.devices.start()

    async def start_integration(self, integ: Integration) -> None:
        await integ.start()

    # -- diagnostics ---------------------------------------------------------------------
    async def run_diagnostics(self) -> dict:
        checks: list[dict] = []
        device_list = self.devices.device_infos()
        real = [d for d in device_list if not d.get("simulated")]
        connected = bool(real)
        open_devs = [d for d in device_list if d.get("open")]
        hid_ok = all(not d.get("error") for d in open_devs)

        def add(name: str, ok: bool | None, message: str, hint: str | None = None):
            checks.append({"check": name, "ok": ok, "message": message, "hint": hint})

        add("luxafor-geschlossen",
            connected,
            f"{len(real)} Luxafor-Gerät(e) erkannt" if connected
            else "Kein Luxafor-Gerät angeschlossen.",
            "Gerät anstecken und ein paar Sekunden warten. Ohne Hardware kann der "
            "Simulationsmodus (hardware.simulator) genutzt werden.")
        add("geraet-offen", bool(open_devs),
            "HID-Gerät geöffnet" if open_devs else "Kein Gerät geöffnet",
            "udev-Regel installiert? scripts/install.sh richtet uaccess ein.")
        add("usb-berechtigungen", hid_ok if connected else None,
            "HID-Zugriff OK" if hid_ok else "Fehler beim HID-Zugriff",
            "/install.sh ausführen (richtet die udev-Regel ein und triggert sie).")
        from luxafor.hardware.hidraw_native import discover_native
        perm_hint = None
        real_infos = [d for d in device_list if not d.get("simulated")]
        if real_infos and not any(d.get("open") for d in real_infos):
            # exakte Node-Rechte anzeigen
            for node in [d.get("path") for d in real_infos if d.get("path")]:
                try:
                    import os as _os
                    st = _os.stat(node)
                    add("node-rechte", False,
                        f"{node}: mode={oct(st.st_mode)[-4:]} uid={st.st_uid}",
                        "Reparatur: sudo install -m 0644 packaging/udev/90-luxafor.rules "
                        "/etc/udev/rules.d/ && sudo udevadm trigger --subsystem-match=hidraw")
                except OSError as exc:
                    add("node-rechte", False, f"{node}: {exc}", None)
            perm_hint = "Geräte erkannt, aber nicht geöffnet (Rechte) — Hinweis oben."
        elif not real_infos:
            add("node-rechte", None, "ohne Hardware nicht prüfbar")

        net_ok = await self._check_internet()
        add("internet", net_ok, "Internet erreichbar" if net_ok else "Kein Internet")
        presence = self.presence_integration
        auth_st = self.auth.status()
        add("ms-anmeldung", auth_st.get("logged_in", False),
            f"angemeldet als {auth_st.get('user')}" if auth_st.get("logged_in") else "nicht angemeldet",
            "Teams-Einrichtung ausführen (Integrationen → Microsoft Teams).")
        graph_ok = presence.presence is not None
        add("graph-erreichbar", graph_ok,
            "Presence API OK" if graph_ok else (presence._last_error or "nicht geprüft"),
            presence._last_err_hint)
        last_sync = self.state._last_sync_ok or presence._last_ok
        add("letzte-synchronisierung", True,
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_sync)) if last_sync
            else "noch nie")
        cur = self.state.current
        add("aktive-regel", True, f"{cur.get('label')} ({cur.get('origin')})")
        add("hintergrunddienst", True,
            f"läuft {int(time.time() - self._started)} s, {presence.poll_count} Presence-Poll(s)")
        sim_mode = config.safe_get(self.db.get_all_settings(), "hardware.simulator", "auto")
        if sim_mode == "force" or any(d.get("simulated") for d in device_list):
            add("simulationsmodus", True,
                "aktiv – keine echte LED steuerbar",
                "Zum Deaktivieren: Einstellungen → hardware.simulator = auto/off.")

        # hidapi selbst verfügbar? (fehlt -> keine Hardware-Erkennung möglich)
        from luxafor.hardware import discovery
        if discovery.hid is None:
            add("hidapi", False,
                f"hidapi-Binding nicht geladen: {discovery.hid_import_error or 'unbekannt'}",
                "Installation reparieren: cd <Projekt> && ~/.local/share/luxafor/venv/bin/"
                "pip install --force-reinstall hidapi  oder ./scripts/install.sh erneut.")
        else:
            all_devices = discovery.all_hid_devices()
            known_vids = (f"0x{LUXAFOR_VENDOR_ID:04x}", f"0x{LUXAFOR_GEN2_VENDOR_ID:04x}")
            luxafor_present = [d for d in all_devices if d["vendor_id"].lower() in known_vids]
            add("hidapi", True, f"geladen; {len(all_devices)} HID-Geräte gesamt, "
                f"{len(luxafor_present)} mit Luxafor-Vendor-ID")
            if not connected and luxafor_present:
                add("luxafor-sichtbar", True,
                    "Kernel sieht Luxafor-Gerät(e): "
                    + ", ".join(f"{d['vendor_id']}:{d['product_id']}" for d in luxafor_present))
            if not connected and not luxafor_present:
                add("luxafor-sichtbar", False, "Kein Gerät mit Vendor-ID 0x04d2 sichtbar",
                    "lsusb prüfen (lsusb | grep -i luxafor oder 04d2). Hängt der Stick "
                    "z. B. an einer Bluetooth-Docking-Variante oder nutzt eine andere VID/PID?")
            elif all_devices:
                import json as _json
                add("hid-gerateliste", True, _json.dumps(all_devices))

        if getattr(self, "port_conflict", False):
            add("api-port", False,
                "Anderer Prozess belegt den Standard-Port 17800 – GUI/CLI sprechen "
                "momentan evtl. einen veralteten Kern an.",
                "Behebung: pkill -f lx-core && systemctl --user restart luxafor-core")
        return {"checks": checks, "version": __version__,
                "devices": device_list,
                "supported": hardware.discovery.supported_device_doc()}

    @staticmethod
    async def _check_internet() -> bool:
        try:
            loop = asyncio.get_running_loop()
            info = await asyncio.wait_for(
                loop.getaddrinfo("login.microsoftonline.com", 443), timeout=5)
            if not info:
                return False
            _, _, _, _, sockaddr = info[0]
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(sockaddr[0], sockaddr[1]), timeout=5)
            writer.close()
            return True
        except Exception:
            return False


def run_core() -> None:
    from luxafor.core import logging_setup
    settings = None
    try:
        settings = Database().get_all_settings()
    except Exception:
        pass
    logging_setup.setup_logging(
        (settings or {}).get("log.level", "INFO"), console=True)
    app = CoreApp()

    async def _main() -> None:
        await app.start()
        try:
            await app.run()
        finally:
            await app.stop()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass