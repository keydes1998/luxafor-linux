"""Graph client tests: throttling, backoff, presence/calendar parsing with a mock server."""
import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient

from luxafor.integrations.msgraph.client import GraphClient, GraphError

pytestmark = pytest.mark.asyncio


class MockGraphApp:
    """Serves Graph-like endpoints on a local test server."""

    def __init__(self):
        self.calls = 0
        self.throttles = 0
        self.errors = 0

    async def presence(self, request):
        self.calls += 1
        return web.json_response({"availability": "Busy", "activity": "InAMeeting"})

    async def throttled_then_ok(self, request):
        self.calls += 1
        if self.throttles < 1:
            self.throttles += 1
            return web.Response(status=429, headers={"Retry-After": "1"})
        return web.json_response({"availability": "Available", "activity": "Available"})

    async def calendarview(self, request):
        self.calls += 1
        val = {
            "value": [
                {"subject": "Sprint Review", "start": {"dateTime": "2026-10-20T10:00:00.0000000Z"},
                 "end": {"dateTime": "2026-10-20T11:00:00.0000000Z"},
                 "showAs": "busy", "sensitivity": "normal", "isAllDay": False},
                {"subject": "Privates", "start": {"dateTime": "2026-10-20T12:00:00.0000000Z"},
                 "end": {"dateTime": "2026-10-20T12:30:00.0000000Z"},
                 "showAs": "busy", "sensitivity": "private", "isAllDay": False},
                {"subject": "Mittag", "start": {"dateTime": "2026-10-20T13:00:00.0000000Z"},
                 "end": {"dateTime": "2026-10-20T14:00:00.0000000Z"},
                 "showAs": "free", "sensitivity": "normal", "isAllDay": False},
            ]
        }
        return web.json_response(val)

    async def forbidden(self, request):
        self.calls += 1
        return web.Response(status=403, text='{"error":{"message":"Access denied"}}')

    async def server_error(self, request):
        self.calls += 1
        if self.errors < 1:
            self.errors += 1
            return web.Response(status=503, text="oops")
        return web.json_response({"availability": "Available", "activity": ""})


@pytest.fixture
async def graph_url():
    mock = MockGraphApp()
    app = web.Application()
    app.router.add_get("/v1.0/me/presence", mock.presence)
    app.router.add_get("/v1.0/throttled", mock.throttled_then_ok)
    app.router.add_get("/v1.0/me/calendarview", mock.calendarview)
    app.router.add_get("/v1.0/me/forbidden", mock.forbidden)
    app.router.add_get("/v1.0/flaky", mock.server_error)
    srv = TestServer(app)
    client = TestClient(srv)
    await client.start_server()
    yield f"http://{srv.host}:{srv.port}", mock
    await client.close()


def token_ok():
    return "t0k"


async def test_error_translation():
    err = GraphClient._from_response(403, '{"error":{"message":"denied"}}')
    assert err.hint and "Administrator" in err.hint
    err2 = GraphClient._from_response(401, "{}")
    assert err2.hint


async def test_presence_and_calendar(graph_url):
    base, mock = graph_url
    gc = GraphClient(token_ok)
    pres = await gc.get(f"{base}/v1.0/me/presence")
    assert pres["availability"] == "Busy"
    assert pres["activity"] == "InAMeeting"
    await gc.close()


async def test_throttled_request_retries(graph_url):
    base, mock = graph_url
    gc = GraphClient(token_ok, retry_delay=0.2)
    data = await gc.get(f"{base}/v1.0/throttled")
    assert data["availability"] == "Available"
    assert mock.calls == 2  # one 429 + one success
    await gc.close()


async def test_5xx_backoff(graph_url):
    base, mock = graph_url
    gc = GraphClient(token_ok, retry_delay=0.2)
    data = await gc.get(f"{base}/v1.0/flaky")
    assert data["activity"] == ""
    assert await gc.get(f"{base}/v1.0/flaky") == data
    await gc.close()


async def test_no_token_raises():
    gc = GraphClient(lambda: None)
    with pytest.raises(GraphError):
        await gc.get("/v1.0/me/presence")
    await gc.close()


async def test_permission_denied_hint(graph_url):
    base, mock = graph_url
    gc = GraphClient(token_ok)
    with pytest.raises(GraphError) as exc:
        await gc.get(f"{base}/v1.0/me/forbidden")
    assert exc.value.status == 403 and "Administrator" in (exc.value.hint or "")
    await gc.close()


async def test_calendarview_normalization(graph_url):
    base, mock = graph_url
    from luxafor.integrations.msgraph.calendar import CalendarSyncer

    class PatchedGC(GraphClient):
        async def get(self, path, params=None, max_retries=4):
            url = path if path.startswith("http") else f"{base}/v1.0{path}"
            return await GraphClient.get(self, url, params, max_retries)

    p = PatchedGC(token_ok)
    events = await p.calendarview()
    await p.close()
    syncer = CalendarSyncer(None)
    norm = syncer._normalize(events, {"calendar.hide_private": "true"})
    titles = [e["title"] for e in norm]
    assert len(norm) == 2  # free event filtered out
    assert "Sprint Review" in titles and "Termin (privat)" in titles
    assert norm[0]["private"] is False and norm[1]["private"] is True