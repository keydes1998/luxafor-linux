"""HID driver for the Luxafor Flag (VID 0x04D2, PID 0xBADA)."""
from __future__ import annotations

import struct
from typing import Any

from luxafor.core.logging_setup import get_logger
from luxafor.hardware.base import (
    KNOWN_MODELS,
    FLAG_GEN2_PRODUCT_ID,
    FLAG_PRODUCT_ID,
    LUXAFOR_VENDOR_ID,
    Led,
    LedCommand,
)

log = get_logger("hardware.flag")

try:
    import hid as _hid
except ImportError:
    _hid = None


class FlagHidDevice:
    """Driver of the Luxafor Flag. Talks to one hidraw device.

    The hidapi module is injected so tests can run without hardware.
    """

    hid: Any = _hid  # module reference; replaceable in tests

    def __init__(self, path: str | None = None, vendor_id: int = LUXAFOR_VENDOR_ID,
                 product_id: int = FLAG_PRODUCT_ID, serial: str = "",
                 hid_module: Any = None) -> None:
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.serial = serial or ""
        self.path = path
        self.hid = hid_module or FlagHidDevice.hid
        self._device: Any = None
        self.last_error: str | None = None
        self._id = self._make_id()

    def _make_id(self) -> str:
        if self.serial:
            return f"flag:{self.serial}"
        if self.path:
            return "flag:" + (self.path.hex() if isinstance(self.path, bytes) else str(self.path))
        return f"flag:{self.product_id:04x}"

    # -- LuxaforDevice interface ------------------------------------------
    @property
    def device_id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return KNOWN_MODELS.get(self.product_id, f"Luxafor device ({self.product_id:04x})")

    @property
    def model(self) -> str:
        return self.name

    @property
    def is_open(self) -> bool:
        return self._device is not None

    def open(self) -> None:
        if self._device is not None:
            return
        if self.hid is None:
            raise RuntimeError("hidapi module not available")
        dev = self.hid.device()
        if self.path:
            dev.open_path(self.path if isinstance(self.path, bytes) else bytes(self.path, "utf-8"))
        else:
            dev.open(self.vendor_id, self.product_id)
        if not bool(getattr(dev, "is_opened", True)):
            raise OSError("failed to open Luxafor HID device")
        self._device = dev
        self.last_error = None
        log.info("opened Luxafor HID device %s (serial=%s)", self._id, self.serial)

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
            log.info("closed Luxafor device %s", self._id)

    def write(self, command: LedCommand) -> bool:
        if self._device is None:
            self.last_error = "device not open"
            return False
        try:
            # hidapi expects the report id as first byte; report id 0 is implicit
            protocol = "gen2" if self.product_id == FLAG_GEN2_PRODUCT_ID else "gen1"
            buf = bytes([0x00]) + struct.pack("8B", *command.encode(protocol))
            n = self._device.write(buf)
            if n <= 0:
                self.last_error = "write failed (device error)"
                return False
            self.last_error = None
            return True
        except Exception as exc:  # OSError/ValueError from hidapi
            self.last_error = str(exc)
            log.warning("write failed on %s: %s", self._id, exc)
            return False

    # -- convenience -------------------------------------------------------
    def set_color(self, rgb: tuple[int, int, int], led: Led = Led.ALL) -> bool:
        return self.write(LedCommand(kind="color", rgb=rgb, led=led))

    def off(self) -> bool:
        return self.write(LedCommand(kind="off"))

    def info(self) -> dict:
        return {
            "id": self.device_id,
            "name": self.name,
            "model": self.model,
            "path": self._hexpath(),
            "open": self.is_open,
            "error": self.last_error,
            "simulated": False,
            "serial": self.serial,
        }

    def _hexpath(self) -> str:
        if not self.path:
            return ""
        p = self.path if isinstance(self.path, bytes) else str(self.path).encode()
        return p.hex()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<FlagHidDevice id={self._id} open={self.is_open}>"