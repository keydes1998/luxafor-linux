"""Webhook integration: external services can trigger LED states via HTTP."""
from __future__ import annotations

import time
import uuid

from luxafor.core.state import Candidate
from luxafor.integrations.base import Integration


class WebhookIntegration(Integration):
    name = "webhooks"
    title = "Webhooks"
    description = "Eingehende HTTP-Trigger setzen temporäre LED-Zustände."

    def __init__(self, context) -> None:
        super().__init__(context)
        self.last_trigger: dict | None = None

    def trigger(self, token_or_name: str) -> tuple[bool, str]:
        """Activates the webhook trigger with the given token; returns (ok, message)."""
        hooks = [h for h in self.ctx.db.webhooks() if h["token"] == token_or_name or h["name"] == token_or_name]
        if not hooks:
            return False, "unknown webhook token"
        hook = hooks[0]
        if not hook["enabled"]:
            return False, "webhook disabled"
        settings = self.ctx.db.get_all_settings()
        try:
            priority = int(settings.get("webhook.priority", "95"))
        except (TypeError, ValueError):
            priority = 95
        expires = time.time() + max(5, int(hook["duration"]))
        self.ctx.state.set_candidate(
            f"webhook:{hook['id']}",
            Candidate(origin="webhook", label=f"Webhook: {hook['name']}",
                      color=hook["color"], effect=hook["effect"],
                      priority=priority, expires_at=expires),
        )
        self.last_trigger = {"hook": hook["name"], "ts": time.time()}
        self.ctx.bus.publish("webhook", {"hook": hook["name"], "color": hook["color"]})
        return True, f"triggered {hook['name']} for {max(5, int(hook['duration']))}s"

    def create_token(self, name: str, color: str, effect: str, duration: int) -> dict:
        import secrets
        token = "luxafor-hook-" + secrets.token_urlsafe(12)
        wid = self.ctx.db.add_webhook(name, token, color, effect, duration)
        return {"id": wid, "token": token}

    def status(self) -> dict:
        return {"triggers": len(self.ctx.db.webhooks()), "last_trigger": self.last_trigger}