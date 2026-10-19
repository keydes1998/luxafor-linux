"""Configuration paths and defaults for Luxafor Linux."""
from __future__ import annotations

import os
from pathlib import Path

from luxafor import APP_NAME, APP_ID, DEFAULT_API_HOST, DEFAULT_API_PORT  # noqa: F401

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "luxafor"
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "luxafor"
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "luxafor"

DB_PATH = STATE_HOME / "luxafor.sqlite3"
LOG_PATH = STATE_HOME / "luxafor.log"
TOKEN_CACHE_FILE = STATE_HOME / "msal_cache.bin"  # encrypted fallback if no Secret Service

API_HOST = "127.0.0.1"
API_PORT = 17800
API_TOKEN_FILE = CONFIG_HOME / "api-token"  # shared secret between GUI/CLI and core

DEFAULT_SETTINGS: dict[str, str] = {
    "api.host": "127.0.0.1",
    "api.port": "17800",
    "api.expose_lan": "false",          # if true, auth (Bearer token) is mandatory
    "api.lan_auth_token": "",           # token for LAN access, generated when exposing
    "sync.interval_seconds": "60",      # Teams presence polling interval
    "sync.fallback_fast_interval": "0", # extra fast poll right after activity change
    "sync.enabled": "true",
    "presence.conflict_policy": "teams_after_meeting",  # teams_wins | meeting_wins | teams_after_meeting
    "presence.activity_boost": "true",  # use Graph 'activity' field for call/meeting distinction
    "calendar.enabled": "false",
    "calendar.scope_minutes": "1440",   # look-ahead window
    "calendar.buffer_before": "5",
    "calendar.buffer_after": "0",
    "calendar.hide_private": "true",    # datensparsam: private events rendered as busy only
    "calendar.priority_meeting": "70",
    "calendar.priority_buffer": "55",
    "hardware.simulator": "auto",       # auto | force | off
    "hardware.reconnect_interval": "5",
    "hardware.brightness": "100",       # software dimming 10..100 %
    "idle.enabled": "false",
    "idle.threshold_minutes": "10",
    "idle.color": "#FFD75E",
    "idle.effect": "solid",
    "idle.priority": "30",
    "lock.enabled": "true",
    "lock.color": "#FFD75E",
    "lock.effect": "solid",
    "lock.priority": "85",
    "lock.timeout_minutes": "60",       # auto-clear lock state
    "schedule.enabled": "false",
    "schedule.rules": "[]",             # list of {start:"18:00", end:"08:00", color:"#000000", effect:"solid", days:"1-5", priority:20}
    "webhook.enabled": "false",
    "webhook.priority": "95",
    "teams.mapping": "",                # JSON overrides for default presence mapping
    "teams.unknown_color": "#FF8800",   # replacement color for PresenceUnknown
    "ms.client_id": "",                 # Entra ID app registration client id
    "ms.tenant": "common",
    "ms.scopes": "User.Read,Presence.Read,Calendars.Read",
    "ui.theme": "dark",
    "ui.language": "de",
    "ui.close_to_tray": "true",
    "ui.start_minimized": "false",
    "ui.notify_on_change": "true",
    "log.level": "INFO",
    "log.redact": "true",
    "active_profile": "",
    "default_color": "#00AA00",
    "default_effect": "solid",
    "default_priority": "10",
    "off_when_presence_offline": "true",
}


def ensure_dirs() -> None:
    for p in (CONFIG_HOME, STATE_HOME, DATA_HOME):
        p.mkdir(mode=0o700, parents=True, exist_ok=True)


def safe_get(settings: dict, key: str, default: str = "") -> str:
    val = settings.get(key, "")
    return val if val not in (None, "") else default