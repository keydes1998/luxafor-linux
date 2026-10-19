"""Simulation device for environments without Luxafor hardware.

Used by the explicit simulator mode (`hardware.simulator = force`) and by the
automated tests. It records all commands so tests and the UI can verify them.
"""
from __future__ import annotations

import threading

from luxafor.hardware.base import Led, LedCommand
from luxafor.core.logging_setup import get_logger

log = get_logger("hardware.sim")


class SimulatorDevice:
    """In-memory Luxafor Flag replacement. Thread-safe command history."""

    def __init__(self, device_id: str = "sim:0") -> None:
        self.device_id = device_id
        self.name = self.model = "Luxafor Flag (Simulator)"
        self.path = None
        self.last_error: str | None = None
        self._open = False
        self._lock = threading.Lock()
        self.commands: list[str] = []          # raw command reprs for debugging
        self.rgb: tuple[int, int, int] = (0, 0, 0)
        self.led: Led = Led.ALL

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True
        log.info("simulator device %s opened", self.device_id)

    def close(self) -> None:
        self._open = False

    def write(self, command: LedCommand) -> bool:
        with self._lock:
            self.commands.append(command.encode())
            if command.kind == "off":
                self.rgb = (0, 0, 0)
            elif command.led is not None:
                self.rgb = command.rgb
                self.led = command.led
        log.info("sim command: %s", command.encode())
        return True

    def history(self) -> list[tuple]:
        with self._lock:
            return list(self.commands)

    def current(self) -> tuple[int, tuple[int, int, int]]:
        with self._lock:
            return int(self.led), self.rgb

    def info(self) -> dict:
        return {
            "id": self.device_id,
            "name": self.name,
            "model": self.model,
            "path": None,
            "open": self.is_open,
            "error": self.last_error,
            "simulated": True,
            "serial": "simulated",
        }

    def __repr__(self) -> str:
        return f"<SimulatorDevice id={self.device_id}>"