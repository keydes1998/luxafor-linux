"""Rule engine: evaluates rules against integration context and emits candidates.

Rule types and their params:
  presence : {"activity_in": [...], "availability_in": [...]}  -> color/effect
  calendar : {"mode": "meeting" | "buffer"}
  schedule : {"start": "HH:MM", "end": "HH:MM", "days": "1-5,6", "mode": "solid"|"off"}
  idle     : {}   (driven by the idle watcher)
  lock     : {}   (driven by the lock watcher)
"""
from __future__ import annotations

import datetime as dt
import re

from luxafor.core.database import Database
from luxafor.core.logging_setup import get_logger
from luxafor.core.state import Candidate
from luxafor.rules.models import Rule

log = get_logger("rules")


class RuleEngine:
    def __init__(self, db: Database) -> None:
        self.db = db

    # -- helpers ---------------------------------------------------------------
    def enabled_rules(self, type_: str | None = None) -> list[Rule]:
        rows = [Rule.from_row(r) for r in self.db.rules()]
        rules = [r for r in rows if r.enabled]
        if type_:
            rules = [r for r in rules if r.type == type_]
        return sorted(rules, key=lambda r: -r.priority)

    # -- evaluation --------------------------------------------------------------
    def evaluate(self, context: dict) -> dict[str, Candidate]:
        """Evaluates the current context and returns candidates keyed for the
        state engine. Empty values simply produce no candidate."""
        out: dict[str, Candidate] = {}
        presence = context.get("presence")
        if presence:
            cand = self._evaluate_presence(presence)
            if cand:
                out["presence"] = cand
        calendar = context.get("calendar")
        if calendar:
            meeting = self._evaluate_calendar(calendar)
            out.update(meeting)
        schedule = self._evaluate_schedule()
        if schedule:
            out.update(schedule)
        if context.get("lock"):
            cand = self._evaluate_simple("lock")
            if cand:
                out["lock"] = cand
        if context.get("idle"):
            cand = self._evaluate_simple("idle")
            if cand:
                out["idle"] = cand
        return out

    # -- presence ---------------------------------------------------------------
    def _evaluate_presence(self, presence: dict) -> Candidate | None:
        availability = presence.get("availability") or ""
        activity = presence.get("activity") or ""
        for rule in self.enabled_rules("presence"):
            if rule.matches_presence(availability, activity):
                return Candidate(
                    origin="presence", label=rule.name, color=rule.color,
                    effect=rule.effect, priority=rule.priority,
                )
        # documented fallback: PresenceUnknown -> configurable replacement color
        if availability in ("PresenceUnknown", ""):
            settings = self.db.get_all_settings()
            from luxafor.core import config as cfg
            return Candidate(
                origin="presence", label="PresenceUnknown",
                color=cfg.safe_get(settings, "teams.unknown_color", "#FF8800"),
                effect="solid", priority=40,
            )
        return None

    # -- calendar -----------------------------------------------------------------
    def _evaluate_calendar(self, calendar: dict) -> dict[str, Candidate]:
        out = {}
        for rule in self.enabled_rules("calendar"):
            mode = rule.params.get("mode", "meeting")
            if mode == "meeting" and calendar.get("meeting"):
                out["calendar:meeting"] = Candidate(
                    origin="meeting", label=rule.name +
                        (f" ({calendar['meeting_title']})" if calendar.get("meeting_title") else ""),
                    color=rule.color, effect=rule.effect, priority=rule.priority)
            if mode == "buffer" and calendar.get("buffer"):
                out["calendar:buffer"] = Candidate(
                    origin="buffer", label=rule.name + (f" → {calendar['next_time']}" if calendar.get("next_time") else ""),
                    color=rule.color, effect=rule.effect, priority=rule.priority)
        return out

    # -- schedule -----------------------------------------------------------------
    def _evaluate_schedule(self) -> dict[str, Candidate]:
        now = dt.datetime.now()
        out = {}
        for i, rule in enumerate(self.enabled_rules("schedule")):
            p = rule.params
            if not RuleEngine._window_matches(now, p):
                continue
            mode = p.get("mode", "solid")
            if mode == "off":
                cand = Candidate(origin="schedule", label=rule.name, color="#000000",
                                 effect="off", priority=rule.priority)
            else:
                cand = Candidate(origin="schedule", label=rule.name, color=rule.color,
                                 effect=rule.effect, priority=rule.priority)
            out.setdefault(f"schedule:{rule.id}", cand)
        return out

    @staticmethod
    def _window_matches(now: dt.datetime, p: dict) -> bool:
        days_spec = str(p.get("days", "1-7") or "1-7")
        # python weekday(): Mon=0; ISO: Mon=1 -> convert
        iso_day = now.isoweekday()
        allowed = False
        for part in re.split(r"[,;]", days_spec):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                allowed = allowed or (int(a) <= iso_day <= int(b))
            else:
                allowed = allowed or (int(part) == iso_day)
        if not allowed:
            return False
        start_s = str(p.get("start", "00:00"))
        end_s = str(p.get("end", "23:59"))
        cur = now.hour * 60 + now.minute

        def parse_hm(s: str) -> int:
            h, m = s.split(":")[:2]
            return int(h) * 60 + int(m)

        try:
            start, end = parse_hm(start_s), parse_hm(end_s)
        except (ValueError, TypeError):
            return False
        if start <= end:
            return start <= cur <= end
        # window spanning midnight
        return cur >= start or cur <= end

    # -- simple types ---------------------------------------------------------------
    def _evaluate_simple(self, type_: str) -> Candidate | None:
        rules = self.enabled_rules(type_)
        if not rules:
            settings = self.db.get_all_settings()
            from luxafor.core import config as cfg
            prefix = type_
            color = cfg.safe_get(settings, f"{prefix}.color", "#FFD75E")
            effect = cfg.safe_get(settings, f"{prefix}.effect", "solid")
            prio = int(cfg.safe_get(settings, f"{prefix}.priority", "40" if type_ == "idle" else "85"))
            names = {"lock": "Bildschirm gesperrt", "idle": "Benutzer abwesend"}
            return Candidate(origin=type_, label=names.get(type_, type_),
                             color=color, effect=effect, priority=prio)
        r = rules[0]
        return Candidate(origin=type_, label=r.name, color=r.color,
                         effect=r.effect, priority=r.priority)

    # -- seed ------------------------------------------------------------------------
    def seed_defaults(self) -> None:
        existing = self.db.query("SELECT COUNT(*) c FROM rules")
        if existing and existing[0]["c"] > 0:
            return
        seeds = [
            ("Teams: Anruf/Präsentation", "presence", "#FF0000", "solid", 80,
             {"activity_in": ["InACall", "InAConferenceCall"]}),
            ("Teams: Präsentation (blinkend)", "presence", "#FF0000", "strobe:4", 81,
             {"activity_in": ["Presenting"]}),
            ("Teams: Besprechung", "presence", "#FF0000", "solid", 71,
             {"activity_in": ["InAMeeting"], "availability_in": ["Busy"]}),
            ("Teams: Nicht stören", "presence", "#8B0000", "solid", 72,
             {"availability_in": ["DoNotDisturb"]}),
            ("Teams: Beschäftigt", "presence", "#FF0000", "solid", 73,
             {"availability_in": ["Busy"]}),
            ("Teams: Abwesend", "presence", "#FFD75E", "solid", 40,
             {"availability_in": ["Away"]}),
            ("Teams: Kurz weg", "presence", "#FFA500", "solid", 40,
             {"availability_in": ["BeRightBack"]}),
            ("Teams: Verfügbar", "presence", "#00B030", "solid", 40,
             {"availability_in": ["Available"]}),
            ("Teams: Offline", "presence", "#000000", "off", 40,
             {"availability_in": ["Offline"]}),
            ("Kalender: Besprechung", "calendar", "#FF0000", "solid", 70, {"mode": "meeting"}),
            ("Kalender: Termin naht", "calendar", "#FFD75E", "solid", 55, {"mode": "buffer"}),
            ("Bildschirm gesperrt", "lock", "#FFD75E", "solid", 85, {}),
            ("Benutzer abwesend", "idle", "#FFD75E", "solid", 30, {}),
            ("Feierabend: LED aus", "schedule", "#000000", "off", 68,
             {"start": "18:00", "end": "23:59", "days": "1-7", "mode": "off"}),
        ]
        for name, type_, color, effect, prio, params in seeds:
            self.db.add_rule(name, type_, color, effect, prio, params, enabled=True)
        log.info("seeded %d default rules", len(seeds))