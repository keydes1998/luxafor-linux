"""Microsoft Entra ID authentication (MSAL, authorization code flow + PKCE).

Tokens are stored preferably in the Secret Service (GNOME Keyring / KDE Wallet
via libsecret-compatible providers). If no Secret Service is available, an
encrypted fallback file inside the XDG state directory is used. Passwords are
never used or stored — only OAuth tokens.
"""
from __future__ import annotations

import asyncio
import base64
import os
import time
import uuid
from typing import Any

from luxafor.core import config
from luxafor.core.logging_setup import get_logger

log = get_logger("msauth")

try:
    import keyring  # type: ignore
    _HAS_KEYRING = True
except Exception:  # pragma: no cover
    keyring = None
    _HAS_KEYRING = False

TOKEN_CACHE_KEY = "luxafor-linux/msal-token-cache"
SCOPE_SEPARATOR = " "


class AuthError(Exception):
    """Authentication flow failed with a user-visible message."""


class PermissionError403(AuthError):
    """The organization does not grant the required Graph permission."""


class TokenStore:
    """Stores the serialized MSAL token cache."""

    def __init__(self, use_secret_service: bool = True) -> None:
        self.use_keyring = use_secret_service and _HAS_KEYRING
        self.keyring_ok = False

    def load(self) -> str:
        if self.use_keyring:
            try:
                data = keyring.get_password(TOKEN_CACHE_KEY, "cache")
                if data:
                    self.keyring_ok = True
                    log.info("token cache loaded from Secret Service")
                    return data
            except Exception as exc:
                log.warning("Secret Service unavailable (%s); using encrypted file fallback", exc)
        return self._load_file()

    def save(self, data: str) -> None:
        if self.use_keyring:
            try:
                keyring.set_password(TOKEN_CACHE_KEY, "cache", data)
                self.keyring_ok = True
                self._remove_file_fallback()
                return
            except Exception as exc:
                log.warning("Secret Service write failed (%s); falling back to file", exc)
        self._save_file(data)

    def clear(self) -> None:
        if self.use_keyring:
            try:
                keyring.delete_password(TOKEN_CACHE_KEY, "cache")
            except Exception:
                pass
        self._remove_file_fallback()

    # -- encrypted file fallback ------------------------------------------
    def _key_from_machine(self) -> bytes:
        """Local-only obfuscation key (not a password store!). The file fallback
        protects against casual disk readers; the Secret Service is preferred."""
        seed = (f"{os.getuid()}:{config.STATE_HOME}:" + os.uname().nodename + ":luxafor")
        return base64.b64encode(seed.encode())[:43] + b"="

    def _load_file(self) -> str:
        from cryptography.fernet import Fernet
        path = config.TOKEN_CACHE_FILE
        if not path.exists():
            return ""
        try:
            return Fernet(self._key_from_machine()).decrypt(path.read_bytes()).decode()
        except Exception:
            log.warning("cannot decrypt token cache file; ignoring it")
            return ""

    def _save_file(self, data: str) -> None:
        from cryptography.fernet import Fernet
        path = config.TOKEN_CACHE_FILE
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        token = Fernet(self._key_from_machine()).encrypt(data.encode())
        path.write_bytes(token)
        os.chmod(path, 0o600)
        self.keyring_ok = False

    def _remove_file_fallback(self) -> None:
        try:
            config.TOKEN_CACHE_FILE.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass


class AuthManager:
    """Manages MSAL PublicClientApplication, login (loopback + PKCE) and silent
    token acquisition."""

    LOOPBACK_TEMPLATE = "http://localhost:{port}"

    def __init__(self, settings_getter) -> None:
        """settings_getter: callable returning the merged settings dict."""
        self._settings = settings_getter
        self.store = TokenStore()
        import msal
        self._msal = msal
        self._cache = msal.SerializableTokenCache()
        cache_data = self.store.load()
        if cache_data:
            self._cache.deserialize(cache_data)
        self._app: Any = None
        self._account: dict | None = None
        self._login_task: asyncio.Task | None = None

    # -- configuration ------------------------------------------------------
    def client_id(self) -> str:
        return (self._settings().get("ms.client_id") or "").strip()

    def tenant(self) -> str:
        return (self._settings().get("ms.tenant") or "common").strip() or "common"

    def scopes(self) -> list[str]:
        raw = self._settings().get("ms.scopes", "User.Read,Presence.Read,Calendars.Read")
        return [s.strip() for s in raw.split(",") if s.strip()]

    def configured(self) -> bool:
        return bool(self.client_id())

    # -- app / cache ----------------------------------------------------------
    def app(self):
        if not self.configured():
            raise AuthError(
                "Keine Entra-ID-App konfiguriert. Trage unter Einstellungen eine "
                "App-Registrierungs-Client-ID ein (ms.client_id)."
            )
        if self._app is None:
            authority = f"https://login.microsoftonline.com/{self.tenant()}"
            self._app = self._msal.PublicClientApplication(
                self.client_id(), authority=authority, token_cache=self._cache
            )
        accounts = self._app.get_accounts()
        self._account = accounts[0] if accounts else None
        return self._app

    def persist_cache(self) -> None:
        if self._cache.has_state_changed:
            self.store.save(self._cache.serialize())
            self._cache.has_state_changed = False

    # -- interactive login ------------------------------------------------------
    async def login(self, loopback_port: int = 0, on_url=None) -> dict:
        """Runs the full browser login flow. Long-running; call from the API
        server task. Returns the logged-in account info."""
        app = self.app()
        port = await self._free_port(loopback_port or 0)
        redirect_uri = self.LOOPBACK_TEMPLATE.format(port=port)
        flow = app.initiate_auth_code_flow(self.scopes(), redirect_uri=redirect_uri, prompt="select_account")
        url = flow["auth_uri"]
        # Der Kern öffnet NIEMALS selbst einen Browser (systemd-Sandbox!).
        # Die Clients (GUI/CLI) horchen auf das SSE-Event 'auth_url' und öffnen
        # den Browser aus der Desktop-Sitzung heraus.
        if on_url:
            on_url(url)

        auth_response = await self._wait_for_redirect(redirect_uri, port, flow["state"])
        result = await asyncio.to_thread(
            app.acquire_token_by_auth_code_flow, flow, auth_response
        )
        self.persist_cache()
        if "error" in result:
            err = result.get("error_description") or result.get("error")
            raise self._translate_error(str(err))
        account = (result.get("account") or {})
        claims = result.get("id_token_claims") or {}
        info = {
            "user": account.get("username") or claims.get("preferred_username") or claims.get("upn"),
            "name": account.get("name") or claims.get("name"),
            "tenant": account.get("tenant_environment") or claims.get("tid"),
            "scopes": result.get("scope", "").split(),
        }
        log.info("login success: %s", info.get("user"))
        return info

    async def _wait_for_redirect(self, redirect_uri: str, port: int, expected_state: str) -> dict:
        """Starts a temporary loopback HTTP server to catch the OAuth redirect."""
        from aiohttp import web
        holder: dict[str, Any] = {}
        done = asyncio.Event()
        err: list[str] = []

        async def handler(request):
            if request.rel_url.path != "/":
                return web.Response(status=404, text="luxafor")
            # validate state to prevent CSRF (documented PKCE flow requirement)
            if request.query.get("state") != expected_state:
                err.append("OAuth state mismatch")
                done.set()
                return web.Response(text="Login fehlgeschlagen (state).", status=400)
            holder["response"] = {k: v for k, v in request.query.items()}
            done.set()
            return web.Response(text="<html><body><h2>Luxafor</h2>"
                                     "<p>Anmeldung erfolgreich. Du kannst das Fenster schließen.</p>"
                                     "</body></html>", content_type="text/html")

        app = web.Application()
        app.router.add_get("/", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        try:
            try:
                await asyncio.wait_for(done.wait(), timeout=180)
            except asyncio.TimeoutError:
                raise AuthError("Timeout beim Warten auf die Microsoft-Anmeldung.")
            if err:
                raise AuthError(err[0])
            return holder.get("response", {})
        finally:
            await runner.cleanup()

    @staticmethod
    async def _free_port(suggested: int) -> int:
        import socket
        if suggested:
            return suggested
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    # -- tokens ----------------------------------------------------------------
    SCOPE_FALLBACKS: list[list[str]] = [
        None,                                  # komplette konfigurierte Liste
        ["User.Read", "Presence.Read"],        # für Kernfunktion Teams-Präsenz
        ["User.Read", "Presence.Read", "offline_access"],
        ["User.Read"],
    ]

    def get_token(self, scopes: list[str] | None = None) -> str | None:
        """Silent token acquisition. Falls die vollständige Scope-Liste nicht
        konsentiert wurde (z. B. Calendars.Read fehlt), reduziert die
        Methode schrittweise, solange User.Read/Presence.Read verfügbar sind.
        Returns None only when not even the minimal set works."""
        if not self.configured():
            return None
        try:
            app = self.app()
        except AuthError:
            return None
        attempts: list[list[str]] = []
        if scopes:
            attempts.append(list(scopes))
        else:
            attempts += [f for f in self.SCOPE_FALLBACKS if f is not None]
        for wanted in attempts:
            result = None
            if self._account:
                result = app.acquire_token_silent(wanted, account=self._account)
            if not result:
                result = app.acquire_token_silent(wanted, account=None)
            if result and "access_token" in result:
                self.persist_cache()
                return result["access_token"]
            if result and result.get("error"):
                log.debug("silent token (%s) failed: %s", wanted,
                          result.get("error_description", result.get("error")))
        return None

    def probe_scopes(self) -> dict[str, bool]:
        """Berechtigungs-Matrix für den Assistenten: pro Scope, ob ein Token
        stillschweigend beschafft werden kann."""
        out = {}
        for scope in self.scopes():
            try:
                app = self.app()
            except AuthError:
                out[scope] = False
                continue
            res = (app.acquire_token_silent([scope], account=self._account)
                   if self._account else None)
            if not res:
                res = app.acquire_token_silent([scope], account=None)
            out[scope] = bool(res and res.get("access_token"))
        return out

    def logout(self) -> None:
        try:
            app = self.app()
            for a in app.get_accounts():
                app.remove_account(a)
        except AuthError:
            pass
        self._cache = self._msal.SerializableTokenCache()
        self._app = None
        self._account = None
        self.store.clear()
        log.info("logout complete")

    # -- status -----------------------------------------------------------------
    def status(self) -> dict:
        st = {
            "configured": self.configured(),
            "logged_in": False,
            "user": None,
            "keyring": self.store.use_keyring and self.store.keyring_ok,
            "scopes": self.scopes(),
        }
        if not self.configured():
            return st
        try:
            app = self.app()
            accounts = app.get_accounts()
            if accounts:
                st["logged_in"] = True
                st["user"] = accounts[0].get("username")
                st["name"] = accounts[0].get("name")
        except AuthError as exc:
            st["error"] = str(exc)
        return st

    @staticmethod
    def _translate_error(err: str) -> AuthError:
        low = err.lower()
        if "aadsts500113" in low or "no reply address" in low:
            return AuthError(
                "Es ist kein Redirect URI hinterlegt. In Entra → App-Registrierung → "
                "Deine App → 'Authentifizierung': Hinzufügen einer Plattform → "
                "'Mobilgerät und Desktop wählen' → Redirect URI 'http://localhost' "
                "eintragen → 'Konfigurieren'. (Nicht die Plattform 'Web' verwenden.)")
        if "aadsts7000218" in low or "client_assertion" in low or "client_secret" in low:
            return AuthError(
                "Die App-Registrierung behandelt die Anmeldung als vertraulichen Client "
                "(Web-Plattform). Entferne unter 'Authentifizierung' die Redirect-URI aus "
                "der Plattform 'Web' und lege sie unter 'Mobilgerät und Desktop' an "
                "('http://localhost'). Setze 'Öffentliche Clientflows zulassen' auf 'Ja'. "
                "Desktop-Apps nutzen niemals einen Client-Secret.")
        if "aadsts900232" in low or "redirect uri" in low:
            return AuthError(
                "Redirect-URI nicht erlaubt: In der App-Registrierung muss "
                "'http://localhost' (Plattform 'Mobilgerät und Desktop') hinterlegt sein.")
        if "aadsts6500" in low or "consent" in low:
            return PermissionError403(
                "Erforderliche Berechtigungen wurden nicht erteilt. Bitte Administrator, "
                "die delegierten Berechtigungen (User.Read, Presence.Read, Calendars.Read) "
                "für die App-Registrierung freizugeben bzw. Admin-Zustimmung zu erteilen.")
        if "interactionrequired" in low or "aadsts65005" in low:
            return AuthError("Microsoft verlangt eine erneute Anmeldung – bitte erneut versuchen.")
        return AuthError(err)