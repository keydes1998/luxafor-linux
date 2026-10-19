"""Local REST API (aiohttp). Loopback-only by default; LAN exposure requires
a Bearer token. Implements the documented endpoints for the GUI, CLI and
integrations:

  GET  /api/status                 current engine status
  POST /api/status                 manual status {"status","color","effect","duration"}
  POST /api/status/restore         'Automatischen Status wiederherstellen'
  GET  /api/devices                device list
  POST /api/device/color           {"led","color","device"}
  POST /api/device/off             {"device"}
  POST /api/device/effect          {"effect","color","device"}
  POST /api/device/flash           {"color","duration","effect","device"}
  POST /api/device/test            {"device"}
  POST /api/profile/activate       {"id"|"name"}
  ... plus settings, rules, profiles, statuses, webhooks, auth, SSE events
"""
from __future__ import annotations

import asyncio
import json
import secrets
import socket
import time
from typing import Any, Awaitable, Callable

from aiohttp import web

from luxafor import __version__
from luxafor.core import config
from luxafor.core.logging_setup import get_logger
from luxafor.core.state import Candidate

log = get_logger("api")

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def json_response(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


class ApiServer:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.started_at = time.time()
        self.runner: web.AppRunner | None = None
        self._port: int | None = None

    # -- lifecycle -----------------------------------------------------------------
    async def start(self) -> None:
        settings = self.ctx.db.get_all_settings()
        host = config.safe_get(settings, "api.host", "127.0.0.1")
        try:
            port = int(config.safe_get(settings, "api.port", str(config.DEFAULT_API_PORT)))
        except ValueError:
            port = config.DEFAULT_API_PORT
        # generate a LAN token as soon as (or in case) non-loopback access is enabled
        if not settings.get("api.lan_auth_token"):
            self.ctx.db.set_setting("api.lan_auth_token", secrets.token_urlsafe(24))
        app = self._build_app()
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, host, port)
        try:
            await site.start()
        except OSError as exc:
            log.error("cannot bind API on %s:%s: %s", host, port, exc)
            log.error("Wahrscheinlich läuft noch ein alter Luxafor-Kern. "
                      "Behebung: pkill -f lx-core && systemctl --user restart luxafor-core")
            self.ctx.port_conflict = True
            if (host, port) != ("127.0.0.1", config.DEFAULT_API_PORT):
                site2 = web.TCPSite(self.runner, "127.0.0.1", config.DEFAULT_API_PORT)
                await site2.start()
                host, port = "127.0.0.1", config.DEFAULT_API_PORT
            else:
                site2 = web.TCPSite(self.runner, host, 0)
                await site2.start()
                port = self.runner.addresses[0][1]
        self.ctx.port_conflict = getattr(self.ctx, "port_conflict", False)
        self._port = port
        self.ctx.api_port = port
        self.ctx.api_host = host
        log.info("REST API listening on %s:%d", host, port)

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    # -- auth -----------------------------------------------------------------------
    @property
    def lan_exposed(self) -> bool:
        host = config.safe_get(self.ctx.db.get_all_settings(), "api.host", "127.0.0.1")
        expose = config.safe_get(self.ctx.db.get_all_settings(), "api.expose_lan", "false") == "true"
        return expose or host not in ("127.0.0.1", "localhost", "::1")

    def _authorized(self, request: web.Request, token_key: str = "api.lan_auth_token") -> bool:
        if not self.lan_exposed and request.remote in ("127.0.0.1", "::1", "localhost"):
            return True
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            expected = self.ctx.db.get_all_settings().get(token_key, "")
            return bool(expected) and secrets.compare_digest(token, expected)
        return False

    @web.middleware
    async def auth_middleware(self, request: web.Request, handler: Handler) -> web.StreamResponse:
        if request.path.startswith("/api/") and not self._authorized(request):
            return json_response({"error": "unauthorized"}, status=401)
        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except Exception:
            log.exception("api error on %s %s", request.method, request.path)
            return json_response({"error": "internal error"}, status=500)

    # -- routes ---------------------------------------------------------------------
    def _build_app(self) -> web.Application:
        app = web.Application(middlewares=[self.auth_middleware])
        routes = [
            web.get("/api/health", self.health),
            web.get("/api/status", self.get_status),
            web.post("/api/status", self.post_manual_status),
            web.post("/api/status/restore", self.post_restore),
            web.post("/api/sync/pause", self.post_pause),
            web.get("/api/devices", self.get_devices),
            web.get("/api/devices/supported", self.get_supported_devices),
            web.post("/api/device/color", self.post_device_color),
            web.post("/api/device/off", self.post_device_off),
            web.post("/api/device/effect", self.post_device_effect),
            web.post("/api/device/flash", self.post_device_flash),
            web.post("/api/device/test", self.post_device_test),
            web.post("/api/profile/activate", self.post_profile_activate),
            web.get("/api/settings", self.get_settings),
            web.put("/api/settings", self.put_settings),
            web.get("/api/rules", self.get_rules),
            web.post("/api/rules", self.post_rule),
            web.put("/api/rules/{id}", self.put_rule),
            web.delete("/api/rules/{id}", self.delete_rule),
            web.get("/api/profiles", self.get_profiles),
            web.post("/api/profiles", self.post_profile),
            web.put("/api/profiles/{id}", self.put_profile),
            web.delete("/api/profiles/{id}", self.delete_profile),
            web.get("/api/statuses", self.get_statuses),
            web.post("/api/statuses", self.post_status),
            web.delete("/api/statuses/{id}", self.delete_status),
            web.get("/api/webhooks", self.get_webhooks),
            web.post("/api/webhooks", self.post_webhook),
            web.delete("/api/webhooks/{id}", self.delete_webhook),
            web.post("/api/webhook/trigger/{token}", self.post_webhook_trigger),
            web.get("/api/integrations", self.get_integrations),
            web.post("/api/integrations/{name}/start", self.post_integration_start),
            web.post("/api/integrations/{name}/stop", self.post_integration_stop),
            web.get("/api/auth/status", self.get_auth_status),
            web.post("/api/auth/verify", self.post_auth_verify),
            web.post("/api/auth/login", self.post_auth_login),
            web.post("/api/auth/logout", self.post_auth_logout),
            web.get("/api/presence", self.get_presence),
            web.get("/api/calendar/upcoming", self.get_calendar_upcoming),
            web.get("/api/diagnostics", self.get_diagnostics),
            web.get("/api/activity", self.get_activity),
            web.get("/api/logs", self.get_logs),
            web.get("/api/logs/export", self.get_logs_export),
            web.get("/api/events", self.get_events),
        ]
        app.add_routes(routes)
        return app

    # -- helpers --------------------------------------------------------------------
    async def _body(self, request: web.Request) -> dict:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # -- endpoint implementations ------------------------------------------------------
    async def health(self, request: web.Request) -> web.Response:
        return json_response({
            "ok": True,
            "version": __version__,
            "uptime": time.time() - self.started_at,
            "port": self._port,
        })

    async def get_status(self, request: web.Request) -> web.Response:
        snap = self.ctx.state.snapshot()
        snap["presence"] = self.ctx.presence_integration.presence
        snap["presence_last_error"] = self.ctx.presence_integration._last_error
        cal = self.ctx.calendar_integration
        snap["calendar_next"] = (cal.upcoming[0]["start"].isoformat() if cal.upcoming else None)
        snap["devices"] = self.ctx.devices.device_infos()
        snap["uptime"] = time.time() - self.started_at
        return json_response(snap)

    async def post_manual_status(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        if self.ctx.state.paused:
            self.ctx.state.set_paused(False)
        duration = 0
        try:
            duration = int(body.get("duration", 0) or 0)
        except (TypeError, ValueError):
            return json_response({"error": "duration must be an integer (seconds)"}, status=400)
        ok = await self.ctx.state.manual_status(
            body.get("status"), body.get("color"), body.get("effect"), duration)
        if not ok:
            return json_response(
                {"error": "unknown status or missing color", "statuses": self.ctx.db.statuses()},
                status=400)
        self.ctx.state.recompute_now()
        return json_response({"ok": True, "current": self.ctx.state.current})

    async def post_restore(self, request: web.Request) -> web.Response:
        self.ctx.state.restore_automatic()
        self.ctx.state.recompute_now()
        return json_response({"ok": True, "current": self.ctx.state.current})

    async def post_pause(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        self.ctx.state.set_paused(bool(body.get("paused", True)))
        return json_response({"ok": True, "paused": self.ctx.state.paused})

    async def get_devices(self, request: web.Request) -> web.Response:
        return json_response({"devices": self.ctx.devices.device_infos(),
                              "effects": self.ctx.devices.known_effects()})

    async def get_supported_devices(self, request: web.Request) -> web.Response:
        from luxafor.hardware.discovery import supported_device_doc
        return json_response(supported_device_doc())

    async def post_device_color(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        from luxafor.hardware.base import Led, parse_color, format_color
        try:
            led = Led.from_value_or_name(body.get("led", "all"))
            rgb = parse_color(body.get("color", "#00AA00"))
        except ValueError as exc:
            return json_response({"error": str(exc)}, status=400)
        device = body.get("device")
        dids = [device] if device else None
        ok = self.ctx.devices.apply_color(rgb, led, dids)
        if ok:
            # Direct device colors count as manual override so the rule engine
            # does not immediately overwrite them.
            duration = float(body.get("duration") or 0)
            self.ctx.state.set_candidate(
                "manual_color",
                Candidate(origin="manual", label="Direkt (Gerätefarbe)",
                          color=format_color(rgb), effect="solid", priority=90,
                          expires_at=time.time() + duration if duration > 0 else None),
            )
            self.ctx.state.recompute_now()
        return json_response({"ok": ok})

    async def post_device_off(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        device = body.get("device")
        ok = self.ctx.devices.apply_off([device] if device else None)
        return json_response({"ok": ok})

    async def post_device_effect(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        from luxafor.hardware.base import Led, parse_color
        try:
            led = Led.from_value_or_name(body.get("led", "all"))
            rgb = parse_color(body.get("color", "#FF0000"))
        except ValueError as exc:
            return json_response({"error": str(exc)}, status=400)
        effect = str(body.get("effect", "solid"))
        # validate against the documented protocol before touching hardware
        from luxafor.core.devices import DeviceManager
        if effect not in ("solid", "off") and DeviceManager._effect_command(effect, rgb) is None:
            return json_response({"error": f"unsupported effect: {effect!r}"}, status=400)
        device = body.get("device")
        ok = self.ctx.devices.apply_state(body.get("color", "#FF0000"), effect, led,
                                         [device] if device else None)
        if not ok:
            return json_response({"error": "effect not supported or write failed"}, status=400)
        return json_response({"ok": True})

    async def post_device_flash(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        try:
            duration = float(body.get("duration", 5))
        except (TypeError, ValueError):
            duration = 5.0
        device = body.get("device")
        ok = await self.ctx.devices.flash(
            body.get("color", "#FF2200"), duration,
            str(body.get("effect", "strobe:4")),
            [device] if device else None)
        return json_response({"ok": ok})

    async def post_device_test(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        device = body.get("device")
        ok = self.ctx.devices.test_device(device)
        return json_response({"ok": ok})

    async def post_profile_activate(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        pid = body.get("id")
        name = body.get("name")
        profiles = self.ctx.db.profiles()
        target = None
        for p in profiles:
            if (pid is not None and p["id"] == pid) or (name and p["name"] == name):
                target = p
                break
        if not target:
            return json_response({"error": "profile not found"}, status=404)
        if target.get("active"):
            return json_response({"ok": True, "profile": target["name"]})
        self.ctx.db.activate_profile(target["id"])
        self.ctx.db.set_setting("active_profile", target["name"])
        self.ctx.state.request_recompute()
        self.ctx.bus.publish("profile", {"active": target["name"]})
        return json_response({"ok": True, "profile": target["name"]})

    async def get_settings(self, request: web.Request) -> web.Response:
        settings = self.ctx.db.get_all_settings()
        settings.pop("api.lan_auth_token", None)  # never expose the LAN token via GET
        return json_response(settings)

    async def put_settings(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        changed = {}
        for key, value in body.items():
            if key not in config.DEFAULT_SETTINGS:
                continue  # ignore unknown keys
            if key == "api.lan_auth_token":
                continue
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            # profile changes need engine refresh
            changed[key] = value
        self.ctx.db.set_settings(changed)
        self.ctx.on_settings_changed(list(changed))
        return json_response(self.ctx.db.get_all_settings())

    # rules ---------------------------------------------------------------
    async def get_rules(self, request: web.Request) -> web.Response:
        return json_response({"rules": [RulePublic(r) for r in self.ctx.db.rules()]})

    async def post_rule(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        from luxafor.rules.models import Rule
        clean, errors = Rule.validate(body)
        if errors:
            return json_response({"errors": errors}, status=400)
        rid = self.ctx.db.add_rule(clean.get("name", "Regel"), clean.get("type", "schedule"),
                                   clean.get("color", "#FF0000"), clean.get("effect", "solid"),
                                   clean.get("priority", 40), clean.get("params", {}),
                                   clean.get("enabled", True))
        self.ctx.state.request_recompute()
        return json_response({"id": rid}, status=201)

    async def put_rule(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        rid = int(request.match_info["id"])
        from luxafor.rules.models import Rule
        clean, errors = Rule.validate(body)
        if errors:
            return json_response({"errors": errors}, status=400)
        self.ctx.db.update_rule(rid, clean)
        self.ctx.state.request_recompute()
        return json_response({"ok": True, "rule": self.ctx.db.rule(rid)})

    async def delete_rule(self, request: web.Request) -> web.Response:
        self.ctx.db.delete_rule(int(request.match_info["id"]))
        self.ctx.state.request_recompute()
        return json_response({"ok": True})

    # profiles -------------------------------------------------------------
    async def get_profiles(self, request: web.Request) -> web.Response:
        return json_response({"profiles": self.ctx.db.profiles()})

    async def post_profile(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        name = (body.get("name") or "").strip()
        if not name:
            return json_response({"error": "name required"}, status=400)
        data = body.get("data") or {}
        pid = self.ctx.db.add_profile(name, data)
        return json_response({"id": pid}, status=201)

    async def put_profile(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        self.ctx.db.update_profile(int(request.match_info["id"]), body.get("data", {}))
        return json_response({"ok": True})

    async def delete_profile(self, request: web.Request) -> web.Response:
        self.ctx.db.execute("DELETE FROM profiles WHERE id=?", (int(request.match_info["id"]),))
        return json_response({"ok": True})

    # statuses (manual presets) ------------------------------------------------
    async def get_statuses(self, request: web.Request) -> web.Response:
        return json_response({"statuses": self.ctx.db.statuses()})

    async def post_status(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        name = (body.get("name") or "").strip()
        if not name:
            return json_response({"error": "name required"}, status=400)
        sid = self.ctx.db.add_status(name, body.get("color", "#FF0000"),
                                     body.get("effect", "solid"),
                                     int(body.get("priority", 90) or 90),
                                     int(body.get("duration", 0) or 0))
        return json_response({"id": sid}, status=201)

    async def delete_status(self, request: web.Request) -> web.Response:
        self.ctx.db.delete_status(int(request.match_info["id"]))
        return json_response({"ok": True})

    # webhooks ------------------------------------------------------------------
    async def get_webhooks(self, request: web.Request) -> web.Response:
        hooks = self.ctx.db.webhooks()
        return json_response({"webhooks": hooks,
                              "url": f"http://{self.ctx.api_host}:{self.ctx.api_port}/api/webhook/trigger/<token>"})

    async def post_webhook(self, request: web.Request) -> web.Response:
        body = await self._body(request)
        name = (body.get("name") or "").strip()
        if not name:
            return json_response({"error": "name required"}, status=400)
        created = self.ctx.webhooks_integration.create_token(
            name, body.get("color", "#FF0044"), str(body.get("effect", "solid")),
            int(body.get("duration", 60) or 60))
        return json_response(created, status=201)

    async def delete_webhook(self, request: web.Request) -> web.Response:
        self.ctx.db.delete_webhook(int(request.match_info["id"]))
        return json_response({"ok": True})

    async def post_webhook_trigger(self, request: web.Request) -> web.Response:
        token = request.match_info["token"]
        # webhook triggers authorized by their unique token even without Bearer
        if not (request.remote in ("127.0.0.1", "::1") or self._authorized(request)):
            return json_response({"error": "unauthorized"}, status=401)
        ok, msg = self.ctx.webhooks_integration.trigger(token)
        return json_response({"ok": ok, "message": msg}, status=200 if ok else 404)

    # integrations --------------------------------------------------------------
    async def get_integrations(self, request: web.Request) -> web.Response:
        return json_response({"integrations": [i.public() for i in self.ctx.registry.all()]})

    async def post_integration_start(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        integ = self.ctx.registry.get(name)
        if not integ:
            return json_response({"error": "unknown integration"}, status=404)
        await self.ctx.start_integration(integ)
        return json_response({"ok": True})

    async def post_integration_stop(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        integ = self.ctx.registry.get(name)
        if not integ:
            return json_response({"error": "unknown integration"}, status=404)
        await integ.stop()
        return json_response({"ok": True})

    # auth -------------------------------------------------------------------------
    async def get_auth_status(self, request: web.Request) -> web.Response:
        return json_response(self.ctx.auth.status())

    async def post_auth_login(self, request: web.Request) -> web.Response:
        if not self.ctx.auth.configured():
            return json_response({
                "error": "client-id-missing",
                "message": "Es ist keine Entra-ID-App-Registrierung hinterlegt. Unter "
                           "'Integrationen → Microsoft Teams' die Client-ID eintragen.",
            }, status=400)
        try:
            info = await self.ctx.auth.login(on_url=lambda url: self.ctx.bus.publish(
                "auth_url", {"url": url}))
            self.ctx.presence_integration.sync_now()
            return json_response({"ok": True, "account": info})
        except Exception as exc:
            hint = getattr(exc, "hint", None)
            return json_response({
                "error": "login-failed",
                "message": str(exc),
                "hint": hint,
            }, status=400)

    async def post_auth_verify(self, request: web.Request) -> web.Response:
        """Schritt 3/4 des Einrichtungsassistenten: Berechtigungen + Verbindungstest."""
        if not self.ctx.auth.configured():
            return json_response({"ok": False, "stage": "config",
                                  "message": "Erst die Client-ID speichern."}, status=400)
        st = self.ctx.auth.status()
        if not st.get("logged_in"):
            return json_response({"ok": False, "stage": "login",
                                  "message": "Noch nicht angemeldet — bitte anmelden."}, status=200)
        try:
            me = await self.ctx.graph_client.me()
            presence = {"ok": False, "error": None}
            cal = {"ok": False, "error": None}
            try:
                p = await self.ctx.graph_client.presence()
                presence = {"ok": True, "value": p}
            except Exception as exc:
                presence = {"ok": False, "error": str(exc), "hint": getattr(exc, "hint", None)}
            settings = self.ctx.db.get_all_settings()
            try:
                events = await self.ctx.graph_client.calendarview(minutes_ahead=60)
                cal = {"ok": True, "count": len(events)}
            except Exception as exc:
                cal = {"ok": False, "error": str(exc), "hint": getattr(exc, "hint", None)}
            return json_response({
                "ok": presence["ok"],
                "user": me.get("userPrincipalName") or me.get("mail"),
                "name": me.get("displayName"),
                "scopes_requested": self.ctx.auth.scopes(),
                "scopes_available": await asyncio.to_thread(self.ctx.auth.probe_scopes),
                "presence": presence,
                "calendar": cal,
                "next_step": "sync" if presence["ok"] else "permissions",
            })
        except Exception as exc:
            return json_response({"ok": False, "stage": "graph", "message": str(exc),
                                  "hint": getattr(exc, "hint", None)})

    async def post_auth_logout(self, request: web.Request) -> web.Response:
        self.ctx.auth.logout()
        self.ctx.presence_integration.presence = None
        self.ctx.state.clear_candidate("presence")
        return json_response({"ok": True})

    # presence / calendar ---------------------------------------------------------------
    async def get_presence(self, request: web.Request) -> web.Response:
        integ = self.ctx.presence_integration
        return json_response({
            "presence": integ.presence,
            "last_error": integ._last_error,
            "hint": integ._last_err_hint,
            "interval": integ._interval_seconds(),
        })

    async def get_calendar_upcoming(self, request: web.Request) -> web.Response:
        integ = self.ctx.calendar_integration
        return json_response({
            "upcoming": integ.status()["upcoming"],
            "next": integ.status()["next"],
            "last_error": integ._last_error,
        })

    # diagnostics ----------------------------------------------------------------------------
    async def get_diagnostics(self, request: web.Request) -> web.Response:
        checks = await self.ctx.run_diagnostics()
        return json_response(checks)

    async def get_activity(self, request: web.Request) -> web.Response:
        return json_response({"activity": self.ctx.db.activity(150)})

    async def get_logs(self, request: web.Request) -> web.Response:
        try:
            n = max(10, min(2000, int(request.query.get("lines", "120"))))
        except ValueError:
            n = 120
        try:
            with open(config.LOG_PATH, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()[-n:]
        except OSError:
            lines = []
        return web.json_response({"lines": [ln.rstrip("\n") for ln in lines]})

    async def get_logs_export(self, request: web.Request) -> web.Response:
        """Exported diagnostics log with secrets redacted."""
        from luxafor.core.logging_setup import RedactingFilter
        text = ""
        try:
            with open(config.LOG_PATH, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            pass
        if config.safe_get(self.ctx.db.get_all_settings(), "log.redact", "true") == "true":
            filt = RedactingFilter()
            import logging
            rec = logging.LogRecord("export", logging.INFO, __file__, 0, text, None, None)
            filt.filter(rec)
            text = rec.getMessage()
        return json_response({"exported_at": time.time(), "version": __version__,
                              "diagnostics": await self.ctx.run_diagnostics(),
                              "log": text})

    # SSE events --------------------------------------------------------------------------
    async def get_events(self, request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(status=200, headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        })
        await resp.prepare(request)
        queue = self.ctx.bus.subscribe()
        try:
            await resp.write(b"event: hello\ndata: {}\n\n")
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    await resp.write(b": keepalive\n\n")
                    continue
                data = json.dumps(ev.data, default=str)
                await resp.write(f"event: {ev.kind}\ndata: {data}\n\n".encode())
        except (asyncio.CancelledError, ConnectionResetError, RuntimeError):
            pass
        finally:
            self.ctx.bus.unsubscribe(queue)
        return resp


def RulePublic(row: dict) -> dict:
    from luxafor.rules.models import Rule
    return Rule.from_row(row).to_public()