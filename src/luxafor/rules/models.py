"""Rule model + parsing helpers for the automation rules."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

RULE_TYPES = ("presence", "calendar", "schedule", "idle", "lock", "webhook")

VALID_EFFECTS = {"solid", "off", "wave", "pattern", "strobe"}


@dataclass
class Rule:
    id: int
    name: str
    type: str
    color: str = "#FF0000"
    effect: str = "solid"
    priority: int = 40
    enabled: bool = True
    params: dict = field(default_factory=dict)

    @staticmethod
    def from_row(row: dict) -> "Rule":
        try:
            params = json.loads(row.get("params") or "{}")
        except json.JSONDecodeError:
            params = {}
        return Rule(
            id=row["id"], name=row["name"], type=row["type"],
            color=row.get("color", "#FF0000"), effect=row.get("effect", "solid"),
            priority=row.get("priority", 40), enabled=bool(row.get("enabled", 1)),
            params=params,
        )

    @staticmethod
    def validate(data: dict) -> tuple[dict, list[str]]:
        """Validates and normalizes a rule submission; returns (clean, errors)."""
        errors: list[str] = []
        clean: dict = {}
        for key in ("name", "type", "color", "effect", "priority", "enabled", "params"):
            if key not in data:
                continue
            value = data[key]
            if key == "name":
                if not isinstance(value, str) or not value.strip():
                    errors.append("name must be a non-empty string")
                else:
                    clean["name"] = value.strip()
            elif key == "type":
                if value not in RULE_TYPES:
                    errors.append(f"type must be one of {RULE_TYPES}")
                else:
                    clean["type"] = value
            elif key == "color":
                try:
                    from luxafor.hardware.base import parse_color, format_color
                    clean["color"] = format_color(parse_color(value))
                except ValueError:
                    errors.append(f"invalid color: {value!r}")
            elif key == "effect":
                base = str(value).split(":")[0]
                if base not in VALID_EFFECTS:
                    errors.append(f"effect must start with one of {sorted(VALID_EFFECTS)}")
                else:
                    clean["effect"] = str(value)
            elif key == "priority":
                try:
                    clean["priority"] = max(0, min(100, int(value)))
                except (TypeError, ValueError):
                    errors.append("priority must be an integer 0..100")
            elif key == "enabled":
                clean["enabled"] = bool(value)
            elif key == "params":
                if not isinstance(value, dict):
                    errors.append("params must be an object")
                else:
                    clean["params"] = value
        return clean, errors

    def matches_presence(self, availability: str, activity: str) -> bool:
        """Checks the presence rule params against Graph availability/activity."""
        def param_in(key: str, value: str) -> bool:
            values = self.params.get(key) or []
            return bool(value) and value in values

        act_ok = param_in("activity_in", activity)
        avail_ok = param_in("availability_in", availability)
        want_act = bool(self.params.get("activity_in"))
        want_avail = bool(self.params.get("availability_in"))
        if want_act and want_avail:
            return act_ok and avail_ok
        if want_act:
            return act_ok
        if want_avail:
            return avail_ok
        return False

    def to_public(self) -> dict:
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "color": self.color, "effect": self.effect,
            "priority": self.priority, "enabled": self.enabled,
            "params": self.params,
        }