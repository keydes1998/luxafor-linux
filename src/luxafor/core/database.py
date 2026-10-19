"""SQLite persistence: settings, rules, profiles, statuses, webhook triggers, activity log."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from luxafor.core import config
from luxafor.core.logging_setup import get_logger

log = get_logger("db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rules (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    type      TEXT NOT NULL,          -- presence | calendar | schedule | idle | lock | webhook | manual
    color     TEXT NOT NULL DEFAULT '#FF0000',
    effect    TEXT NOT NULL DEFAULT 'solid',
    priority  INTEGER NOT NULL DEFAULT 40,
    enabled   INTEGER NOT NULL DEFAULT 1,
    params    TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT UNIQUE NOT NULL,
    data    TEXT NOT NULL DEFAULT '{}',
    active  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS statuses (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT UNIQUE NOT NULL,
    color    TEXT NOT NULL,
    effect   TEXT NOT NULL DEFAULT 'solid',
    priority INTEGER NOT NULL DEFAULT 90,
    duration INTEGER DEFAULT 0,
    builtin  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS webhook_triggers (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT UNIQUE NOT NULL,
    token    TEXT NOT NULL UNIQUE,
    color    TEXT NOT NULL DEFAULT '#FF0044',
    effect   TEXT NOT NULL DEFAULT 'solid',
    duration INTEGER NOT NULL DEFAULT 60,
    enabled  INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS activity (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    kind    TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity(ts DESC);
"""


class Database:
    def __init__(self, path: str | None = None) -> None:
        config.ensure_dirs()
        self.path = str(path or config.DB_PATH)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self.seed_defaults()

    # -- generic helpers -----------------------------------------------------
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()

    # -- settings ------------------------------------------------------------
    def get_all_settings(self) -> dict[str, str]:
        rows = self.query("SELECT key, value FROM settings")
        merged = dict(config.DEFAULT_SETTINGS)
        merged.update({r["key"]: r["value"] for r in rows})
        return merged

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )

    def set_settings(self, values: dict[str, str]) -> None:
        for k, v in values.items():
            self.set_setting(k, v)

    # -- rules ---------------------------------------------------------------
    def rules(self) -> list[dict]:
        return [dict(r) for r in self.query("SELECT * FROM rules ORDER BY priority DESC")]

    def rule(self, rule_id: int) -> dict | None:
        rows = self.query("SELECT * FROM rules WHERE id=?", (rule_id,))
        return dict(rows[0]) if rows else None

    def add_rule(self, name: str, type_: str, color: str, effect: str,
                 priority: int, params: dict, enabled: bool = True) -> int:
        cur = self.execute(
            "INSERT INTO rules(name,type,color,effect,priority,enabled,params,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (name, type_, color, effect, priority,
             int(enabled), json.dumps(params), time.time()),
        )
        return int(cur.lastrowid or 0)

    def update_rule(self, rule_id: int, updates: dict) -> bool:
        allowed = {"name", "type", "color", "effect", "priority", "enabled"}
        sets, vals = [], []
        for k, v in updates.items():
            if k == "params":
                sets.append("params=?"); vals.append(json.dumps(v))
            elif k in allowed:
                sets.append(f"{k}=?"); vals.append(v)
        if not sets:
            return False
        sets.append("updated_at=?"); vals.append(time.time())
        vals.append(rule_id)
        self.execute(f"UPDATE rules SET {', '.join(sets)} WHERE id=?", tuple(vals))
        return True

    def delete_rule(self, rule_id: int) -> None:
        self.execute("DELETE FROM rules WHERE id=?", (rule_id,))

    # -- profiles ------------------------------------------------------------
    def profiles(self) -> list[dict]:
        out = []
        for r in self.query("SELECT * FROM profiles ORDER BY id"):
            d = dict(r)
            d["data"] = json.loads(d["data"] or "{}")
            d["active"] = bool(d["active"])
            out.append(d)
        return out

    def add_profile(self, name: str, data: dict) -> int:
        cur = self.execute(
            "INSERT OR IGNORE INTO profiles(name, data) VALUES(?,?)",
            (name, json.dumps(data)),
        )
        return int(cur.lastrowid or 0)

    def update_profile(self, prof_id: int, data: dict) -> bool:
        self.execute("UPDATE profiles SET data=? WHERE id=?", (json.dumps(data), prof_id))
        return True

    def activate_profile(self, prof_id: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE profiles SET active=0")
            self._conn.execute("UPDATE profiles SET active=1 WHERE id=?", (prof_id,))
            self._conn.commit()

    def active_profile(self) -> dict | None:
        rows = self.query("SELECT * FROM profiles WHERE active=1")
        if not rows:
            return None
        d = dict(rows[0])
        d["data"] = json.loads(d["data"] or "{}")
        d["active"] = True
        return d

    # -- statuses ------------------------------------------------------------
    def statuses(self) -> list[dict]:
        return [dict(r) for r in self.query("SELECT * FROM statuses ORDER BY priority DESC, name")]

    def add_status(self, name: str, color: str, effect: str = "solid",
                   priority: int = 90, duration: int = 0) -> int:
        cur = self.execute(
            "INSERT OR IGNORE INTO statuses(name,color,effect,priority,duration)"
            " VALUES(?,?,?,?,?)",
            (name, color, effect, priority, duration),
        )
        return int(cur.lastrowid or 0)

    def delete_status(self, status_id: int) -> None:
        self.execute("DELETE FROM statuses WHERE builtin=0 AND id=?", (status_id,))

    # -- webhook triggers ----------------------------------------------------
    def webhooks(self) -> list[dict]:
        return [dict(r) for r in self.query("SELECT * FROM webhook_triggers ORDER BY id")]

    def add_webhook(self, name: str, token: str, color: str, effect: str, duration: int) -> int:
        cur = self.execute(
            "INSERT OR IGNORE INTO webhook_triggers(name,token,color,effect,duration)"
            " VALUES(?,?,?,?,?)",
            (name, token, color, effect, duration),
        )
        return int(cur.lastrowid or 0)

    def delete_webhook(self, hook_id: int) -> None:
        self.execute("DELETE FROM webhook_triggers WHERE id=?", (hook_id,))

    # -- activity log --------------------------------------------------------
    def log_activity(self, kind: str, payload: dict) -> None:
        try:
            self.execute(
                "INSERT INTO activity(ts, kind, payload) VALUES(?,?,?)",
                (time.time(), kind, json.dumps(payload)),
            )
            # keep the log bounded
            self.execute("DELETE FROM activity WHERE id < (SELECT IFNULL(MAX(id),0)-500 FROM activity)")
        except sqlite3.Error:
            log.debug("activity write failed", exc_info=True)

    def activity(self, limit: int = 100) -> list[dict]:
        rows = self.query("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d["payload"])
            except Exception:
                d["payload"] = {}
            out.append(d)
        return out

    # -- seed ----------------------------------------------------------------
    def seed_defaults(self) -> None:
        existing = self.query("SELECT COUNT(*) c FROM statuses")
        if existing and existing[0]["c"] == 0:
            for name, color, effect, prio, dur in [
                ("Verfügbar", "#00B030", "solid", 90, 0),
                ("Beschäftigt", "#FF0000", "solid", 90, 0),
                ("Nicht stören", "#8B0000", "solid", 90, 0),
                ("In Besprechung", "#FF2200", "solid", 85, 0),
                ("Pause", "#FFD75E", "solid", 85, 0),
                ("Abwesend", "#FFA500", "solid", 85, 0),
                ("Fokuszeit", "#660011", "solid", 85, 0),
            ]:
                self.add_status(name, color, effect, prio, dur)
        hooks = self.query("SELECT COUNT(*) c FROM webhook_triggers")
        if hooks and hooks[0]["c"] == 0:
            self.add_webhook("critical", "luxafor-hook-critical-1", "#FF0044", "strobe", 60)