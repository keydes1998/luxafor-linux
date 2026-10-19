"""Microsoft Graph REST client with throttling and exponential backoff."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from typing import Any

import aiohttp

from luxafor.core.logging_setup import get_logger

log = get_logger("graph")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphError(Exception):
    def __init__(self, message: str, status: int = 0, hint: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.hint = hint


class GraphClient:
    def __init__(self, token_getter, retry_delay: float = 2.0) -> None:
        """token_getter: callable returning a bearer token or None."""
        self._get_token = token_getter
        self._session: aiohttp.ClientSession | None = None
        self._retry_delay = retry_delay

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Accept": "application/json",
                         "SdkVersion": "luxafor-linux-1.0.0-graph"},
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def get(self, path: str, params: dict | None = None, max_retries: int = 4) -> dict:
        """GET with 429 (Retry-After) handling and exponential backoff."""
        url = path if path.startswith("http") else GRAPH_BASE + path
        delay = self._retry_delay
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            token = await asyncio.to_thread(self._get_token)
            if not token:
                raise GraphError("Nicht bei Microsoft angemeldet", status=401,
                                 hint="Bitte bei Teams/Graph anmelden.")
            session = await self._ensure_session()
            headers = {"Authorization": f"Bearer {token}"}
            try:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", "0") or "0")
                        wait = max(retry_after, delay)
                        log.warning("graph throttled (429), retry in %.1fs", wait)
                        await asyncio.sleep(wait)
                        delay = min(delay * 2, 120)
                        continue
                    if resp.status >= 500:
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 60)
                        continue
                    body = await resp.text()
                    if resp.status < 200 or resp.status >= 300:
                        raise self._from_response(resp.status, body)
                    return json.loads(body) if body else {}
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_err = exc
                log.warning("graph network error (%s), retry in %.1fs", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
        raise GraphError(f"Graph nicht erreichbar: {last_err}", status=504,
                         hint="Netzwerk/Proxy prüfen.")

    @staticmethod
    def _from_response(status: int, body: str) -> GraphError:
        msg = body[:400]
        hint = None
        if status == 403:
            hint = ("Die Organisation verweigert die Berechtigung (delegierte Graph-"
                    "Berechtigungen). Der Administrator muss die App-Registrierung "
                    "freigeben: Presence.Read und ggf. Calendars.Read delegiert erteilen "
                    "oder Tenant-Restrikeinschränkungen der 'Microsoft Graph Command Line "
                    "Tools'-artigen Apps prüfen.")
        elif status == 401:
            hint = "Anmeldetoken ungültig – bitte neu anmelden."
        elif status == 404:
            hint = ("Ressource nicht gefunden. Bei tenant-spezifischen Apps muss ggf. "
                    "Presence.Read aktiviert sein; prüfe auch die App-Registrierung.")
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", msg) or msg
        except Exception:
            pass
        return GraphError(f"Graph HTTP {status}: {msg}", status=status, hint=hint)

    # -- endpoints -----------------------------------------------------------------
    async def me(self) -> dict:
        return await self.get("/me")

    async def presence(self) -> dict:
        data = await self.get("/me/presence")
        return {
            "availability": data.get("availability", ""),
            "activity": data.get("activity", ""),
            "ts": dt.datetime.now().isoformat(timespec="seconds"),
        }

    async def calendarview(self, minutes_ahead: int = 1440, look_back: int = 0) -> list[dict]:
        start = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=look_back)
        end = start + dt.timedelta(minutes=max(15, minutes_ahead))
        params = {
            "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "$select": "subject,start,end,showAs,isAllDay,sensitivity,responseStatus",
            "$orderby": "start/dateTime",
            "$top": "50",
        }
        data = await self.get("/me/calendarview", params=params)
        return data.get("value", [])