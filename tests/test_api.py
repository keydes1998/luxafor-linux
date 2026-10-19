"""REST API tests with an in-memory core context (no hardware, no network)."""
import asyncio
import time

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient

from luxafor.api.server import ApiServer
from luxafor.core.database import Database
from luxafor.core.events import EventBus
from luxafor.core.state import Candidate, StateEngine
from luxafor.rules.engine import RuleEngine

pytestmark = pytest.mark.asyncio


class FakeDevices:
    def __init__(self):
        self._last = None
        self.applied = []

    def apply_color(self, rgb, led=None, device_ids=None):
        name = getattr(led, "name", str(led))
        self._last = ("color", rgb, name)
        self.applied.append(self._last)
        return True

    def apply_off(self, device_ids=None):
        self._last = ("off",)
        self.applied.append(self._last)
        return True

    def apply_state(self, color, effect, led=None, device_ids=None):
        self._last = ("state", color, effect)
        self.applied.append(self._last)
        return True

    async def flash(self, color, duration=5, effect="strobe:4", device_ids=None,
                    restore_state=None):
        self._last = ("flash", color, effect)
        self.applied.append(self._last)
        return True

    def test_device(self, device_id=None):
        self._last = ("test",)
        return True

    def device_infos(self):
        return [{"id": "dev-1", "name": "Luxafor Flag", "model": "Luxafor Flag",
                 "open": True, "simulated": False, "error": None, "color": "#FF0000"}]

    def known_effects(self):
        return [{"id": "solid", "name": "Dauerlicht"}]


class FakePresence:
    presence = {"availability": "Available", "activity": "Available",
                "ts": time.strftime("%H:%M")}
    _last_error = None
    _last_err_hint = None
    poll_count = 1

    def _interval_seconds(self):
        return 60

    def sync_now(self):
        pass


class FakeCalendar:
    upcoming = []
    _last_error = None

    def status(self):
        return {"upcoming": [], "next": None, "last_error": None}


class FakeAuth:
    def status(self):
        return {"configured": True, "logged_in": False, "user": None,
                "scopes": ["Presence.Read"]}

    def logout(self):
        pass

    async def login(self, on_url=None):
        pass

    def configured(self):
        return True


class FakeRegistry:
    def all(self):
        return []

    def get(self, name):
        return None


class FakeWebhooks:
    def trigger(self, token):
        return False, "unknown webhook token"

    def create_token(self, name, color, effect, duration):
        return {"id": 1, "token": "t"}


class FakeCtx:
    """Mimics CoreApp surface used by the API layer."""

    def __init__(self, tmp_path):
        self.db = Database(tmp_path / "api.sqlite3")
        self.bus = EventBus()
        self.devices = FakeDevices()
        self.state = StateEngine(self.db, self.devices, self.bus)
        self.rules = RuleEngine(self.db)
        self.rules.seed_defaults()
        self.presence_integration = FakePresence()
        self.calendar_integration = FakeCalendar()
        self.auth = FakeAuth()
        self.registry = FakeRegistry()
        self.webhooks_integration = FakeWebhooks()
        self.api_host = "127.0.0.1"
        self.api_port = 17800

    def on_settings_changed(self, keys):
        pass

    async def run_diagnostics(self):
        return {"checks": []}


@pytest.fixture
async def client(tmp_path):
    ctx = FakeCtx(tmp_path)
    await ctx.state.start()
    server = ApiServer(ctx)
    app = server._build_app()
    server._server = TestServer(app)
    tc = TestClient(server._server)
    await tc.start_server()
    yield tc, ctx
    await tc.close()
    await ctx.state.stop()


async def test_health(client):
    tc, _ = client
    resp = await tc.get("/api/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True and "version" in data


async def test_get_status(client):
    tc, ctx = client
    resp = await tc.get("/api/status")
    assert resp.status == 200
    data = await resp.json()
    assert "current" in data and "candidates" in data
    assert data["presence"]["availability"] == "Available"


async def test_post_manual_status_by_name(client):
    tc, ctx = client
    resp = await tc.post("/api/status", json={"status": "Nicht stören", "duration": 30})
    assert resp.status == 200
    assert ctx.devices.applied[-1] == ("state", "#8B0000", "solid")
    data = await resp.json()
    assert data["ok"] is True


async def test_post_manual_status_color_only(client):
    tc, ctx = client
    resp = await tc.post("/api/status", json={"color": "#123456", "effect": "solid"})
    assert resp.status == 200
    assert ctx.devices.applied[-1] == ("state", "#123456", "solid")


async def test_post_manual_status_invalid(client):
    tc, ctx = client
    resp = await tc.post("/api/status", json={"status": "unbekannt"})
    assert resp.status == 400


async def test_restore(client):
    tc, ctx = client
    await tc.post("/api/status", json={"status": "Beschäftigt"})
    resp = await tc.post("/api/status/restore", json={})
    assert resp.status == 200
    assert ctx.state.manual_active() is False


async def test_device_color_endpoint(client):
    tc, ctx = client
    resp = await tc.post("/api/device/color", json={"color": "#FF8800", "led": "front"})
    assert resp.status == 200
    assert ("color", (255, 136, 0), "FRONT") in ctx.devices.applied
    resp = await tc.post("/api/device/color", json={"color": "bogus"})
    assert resp.status == 400


async def test_device_off_effect_flash_test(client):
    tc, ctx = client
    assert (await tc.post("/api/device/off", json={})).status == 200
    resp = await tc.post("/api/device/effect", json={"effect": "strobe:6", "color": "#00FF00"})
    assert resp.status == 200
    resp = await tc.post("/api/device/effect", json={"effect": "rainbow"})
    assert resp.status == 400
    resp = await tc.post("/api/device/flash", json={"color": "#FF0000", "duration": 3})
    assert resp.status == 200
    resp = await tc.post("/api/device/test", json={})
    assert resp.status == 200


async def test_settings_roundtrip_and_token_hidden(client):
    tc, ctx = client
    resp = await tc.get("/api/settings")
    assert resp.status == 200
    data = await resp.json()
    assert "api.lan_auth_token" not in data
    assert "sync.interval_seconds" in data
    resp = await tc.put("/api/settings", json={"sync.interval_seconds": "45", "unknown.key": "x"})
    assert resp.status == 200
    assert ctx.db.get_all_settings()["sync.interval_seconds"] == "45"
    assert "unknown.key" not in ctx.db.get_all_settings()


async def test_rules_crud(client):
    tc, ctx = client
    resp = await tc.get("/api/rules")
    rules = (await resp.json())["rules"]
    assert len(rules) >= 10
    resp = await tc.post("/api/rules", json={
        "name": "Testregel", "type": "schedule", "color": "#00FF00", "effect": "solid",
        "priority": 33, "params": {"start": "09:00", "end": "17:00"}})
    assert resp.status == 201
    rid = (await resp.json())["id"]
    resp = await tc.put(f"/api/rules/{rid}", json={"priority": 21})
    assert resp.status == 200
    assert ctx.db.rule(rid)["priority"] == 21
    resp = await tc.delete(f"/api/rules/{rid}")
    assert resp.status == 200
    assert ctx.db.rule(rid) is None


async def test_rule_validation_error(client):
    tc, _ = client
    resp = await tc.post("/api/rules", json={"name": "x", "type": "presence",
                                             "color": "nope", "effect": "solid"})
    assert resp.status == 400


async def test_statuses_and_profiles(client):
    tc, ctx = client
    resp = await tc.get("/api/statuses")
    assert resp.status == 200
    resp = await tc.post("/api/statuses", json={"name": "Fokus 2", "color": "#660011"})
    assert resp.status == 201
    resp = await tc.get("/api/profiles")
    assert resp.status == 200
    resp = await tc.post("/api/profiles", json={"name": "Büro", "data": {"default_color": "#22AA44"}})
    assert resp.status == 201
    pid = (await resp.json())["id"]
    resp = await tc.post("/api/profile/activate", json={"id": pid})
    assert resp.status == 200
    assert ctx.db.active_profile()["name"] == "Büro"


async def test_webhook_trigger_404_unknown(client):
    tc, _ = client
    resp = await tc.post("/api/webhook/trigger/does-not-exist")
    assert resp.status == 404


async def test_auth_status_and_logout_login_missing(client):
    tc, _ = client
    resp = await tc.get("/api/auth/status")
    assert resp.status == 200
    resp = await tc.post("/api/auth/login")
    assert resp.status == 200  # FakeAuth.login returns OK


async def test_sse_stream_receives_state(client):
    tc, ctx = client
    resp = await tc.get("/api/events")
    assert resp.status == 200
    # SSE is a chunked stream: readany returns whatever is buffered
    chunk = await asyncio.wait_for(resp.content.readany(), timeout=3)
    assert chunk.startswith(b"event: ")
    # trigger a state change and receive it
    ctx.bus.publish("state", {"test": 1})
    chunk2 = await asyncio.wait_for(resp.content.readany(), timeout=3)
    assert b"event: state" in chunk2


async def test_diagnostics_and_logs(client):
    tc, _ = client
    resp = await tc.get("/api/diagnostics")
    assert resp.status == 200
    resp = await tc.get("/api/logs?lines=5")
    assert resp.status == 200
    assert "lines" in await resp.json()
    resp = await tc.get("/api/logs/export")
    assert resp.status == 200