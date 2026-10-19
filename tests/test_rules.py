"""Rule engine tests: presence mapping, calendar, schedule windows, validation."""
import datetime as dt

from luxafor.core.database import Database
from luxafor.rules.engine import RuleEngine
from luxafor.rules.models import Rule


def make_rule(type_, params, color="#FF0000", effect="solid", priority=40):
    return Rule(id=1, name="t", type=type_, color=color, effect=effect,
                priority=priority, params=params)


def test_presence_matching():
    r = make_rule("presence", {"availability_in": ["Busy", "DoNotDisturb"]})
    assert r.matches_presence("Busy", "")
    assert r.matches_presence("DoNotDisturb", "")
    assert not r.matches_presence("Available", "")

    r2 = make_rule("presence", {"activity_in": ["InACall", "Presenting"]})
    assert r2.matches_presence("", "InACall")
    assert r2.matches_presence("Available", "Presenting")
    assert not r2.matches_presence("Available", "Available")

    r3 = make_rule("presence", {"availability_in": ["Busy"], "activity_in": ["Presenting"]})
    assert r3.matches_presence("Busy", "Presenting")
    assert not r3.matches_presence("Available", "Presenting")


def test_schedule_window_midnight_split():
    now = dt.datetime(2026, 10, 19, 6, 0)  # Monday 06:00 inside 18:00-08:00 window (pre-noon side)
    assert RuleEngine._window_matches(now, {"start": "18:00", "end": "08:00"})
    now2 = dt.datetime(2026, 10, 19, 12, 0)  # noon outside
    assert not RuleEngine._window_matches(now2, {"start": "18:00", "end": "08:00"})
    now3 = dt.datetime(2026, 10, 19, 19, 30)
    assert RuleEngine._window_matches(now3, {"start": "18:00", "end": "23:59"})


def test_schedule_days():
    monday = dt.datetime(2026, 10, 19, 19, 30)   # ISO 1
    saturday = dt.datetime(2026, 10, 24, 19, 30)  # ISO 6
    p = {"start": "18:00", "end": "20:00", "days": "1-5"}
    assert RuleEngine._window_matches(monday, p)
    assert not RuleEngine._window_matches(saturday, p)
    p2 = {"start": "18:00", "end": "20:00", "days": "1-5,6"}
    assert RuleEngine._window_matches(saturday, p2)


def test_rule_validation():
    clean, errors = Rule.validate({"name": "X", "type": "presence", "color": "#ABCDEF",
                                   "effect": "strobe:5", "priority": 55, "enabled": True,
                                   "params": {"availability_in": ["Busy"]}})
    assert not errors and clean["color"] == "#ABCDEF" and clean["effect"] == "strobe:5"
    _, errors2 = Rule.validate({"type": "nope", "color": "xx", "effect": "rainbow",
                                "priority": "high"})
    assert len(errors2) == 4


def test_rule_engine_presence(tmp_path):
    db = Database(tmp_path / "r.sqlite3")
    engine = RuleEngine(db)
    engine.seed_defaults()
    out = engine.evaluate({"presence": {"availability": "Busy", "activity": ""}})
    assert "presence" in out
    assert out["presence"].color == "#FF0000"
    out2 = engine.evaluate({"presence": {"availability": "Available", "activity": "Presenting"}})
    assert out2["presence"].effect.startswith("strobe")
    out3 = engine.evaluate({"presence": {"availability": "Offline", "activity": ""}})
    assert out3["presence"].effect == "off"
    out4 = engine.evaluate({"presence": {"availability": "", "activity": ""}})
    assert out4["presence"].origin == "presence"  # unknown fallback color


def test_rule_engine_calendar(tmp_path):
    db = Database(tmp_path / "r.sqlite3")
    engine = RuleEngine(db)
    engine.seed_defaults()
    meeting = engine.evaluate({"calendar": {"meeting": True, "meeting_title": "Sprint"}})
    assert "calendar:meeting" in meeting
    assert meeting["calendar:meeting"].color == "#FF0000"
    assert "Sprint" in meeting["calendar:meeting"].label
    buffer_ = engine.evaluate({"calendar": {"meeting": False, "buffer": True, "next_time": "10:00"}})
    assert "calendar:buffer" in buffer_
    assert buffer_["calendar:buffer"].priority == 55


def test_rule_engine_schedule(tmp_path):
    db = Database(tmp_path / "r.sqlite3")
    engine = RuleEngine(db)
    engine.seed_defaults()
    out = engine.evaluate({})  # only schedule rules are time based
    for key, cand in out.items():
        assert key.startswith("schedule:")
        assert cand.origin == "schedule"