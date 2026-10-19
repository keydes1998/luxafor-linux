"""Integration base classes and registry (plugin system)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Integration(ABC):
    """Base class for background integrations. Implementations must be restart-
    safe: start() may be called again after stop()."""

    name: str = "integration"
    title: str = "Integration"
    description: str = ""

    def __init__(self, context: Any) -> None:
        self.ctx = context
        self.enabled = False

    async def start(self) -> None:
        self.enabled = True

    async def stop(self) -> None:
        self.enabled = False

    @abstractmethod
    def status(self) -> dict: ...

    def public(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "enabled": self.enabled,
            "status": self.status(),
        }


class IntegrationRegistry:
    def __init__(self) -> None:
        self._integrations: dict[str, Integration] = {}

    def register(self, integration: Integration) -> Integration:
        self._integrations[integration.name] = integration
        return integration

    def get(self, name: str) -> Integration | None:
        return self._integrations.get(name)

    def all(self) -> list[Integration]:
        return list(self._integrations.values())

    def names(self) -> list[str]:
        return list(self._integrations)