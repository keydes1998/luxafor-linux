"""Native Linux hidraw access for Luxafor devices.

Reads /sys/class/hidraw/*/device/uevent (HID_ID = bus:vid:pid, HID_NAME) and
talks to /dev/hidrawN directly with os.open/os.write. Advantages over hidapi:
- truthful errno (EPERM/EACCES/ENODEV) instead of hidapi's generic 'open failed'
- uaccess ACLs of logind are honored the same way
- no libusb/kernel-driver-detach ambiguity; no extra dependency
"""
from __future__ import annotations

import glob
import os
import struct
from typing import Any

from luxafor.core.logging_setup import get_logger
from luxafor.hardware.base import GEN1, GEN2, Led, LedCommand, looks_like_luxafor

log = get_logger("hardware.hidraw")


def sysfs_base() -> str:
    return os.environ.get("LUXAFOR_HIDRAW_SYSFS", "/sys/class/hidraw")


def dev_base() -> str:
    """Root of /dev (overridable in tests to point at a temp dir)."""
    return os.environ.get("LUXAFOR_HIDRAW_DEV_ROOT", "/dev")


def discover_native(base: str | None = None) -> NativeNode_list:
    """Returns NativeNode tuples of Luxafor hidraw nodes."""
    base = base or sysfs_base()
    out: list[tuple[str, int, int, str, str]] = []
    for sysfs_path in sorted(glob.glob(os.path.join(base, "hidraw*"))):
        name = os.path.basename(sysfs_path)
        try:
            with open(os.path.join(sysfs_path, "device", "uevent")) as fh:
                content = fh.read()
        except OSError:
            continue
        vid = pid = ""
        hid_name = ""
        for line in content.splitlines():
            if line.startswith("HID_ID="):
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    vid, pid = parts[1].lower(), parts[2].lower()
            elif line.startswith("HID_NAME="):
                hid_name = line.split("=", 1)[1]
        if not vid or not pid:
            continue
        try:
            vid_i = int(vid, 16)
            pid_i = int(pid, 16)
        except ValueError:
            continue
        if not looks_like_luxafor(vid_i, pid_i, hid_name):
            continue
        node = os.path.join(dev_base(), name)
        # USB topology path, used as stable id (e.g. "3-1:1.0")
        topology = ""
        try:
            resolved = os.path.realpath(os.path.join(sysfs_path, "device"))
            ue2 = ""
            for candidate in (resolved, os.path.dirname(resolved)):
                try:
                    with open(os.path.join(candidate, "uevent")) as fh:
                        ue2 = fh.read()
                except OSError:
                    continue
                for line in ue2.splitlines():
                    if line.startswith("DEVTYPE=usb_interface") and "DEVPATH=" in line:
                        topology = line.split("=", 1)[1].split("/")[-1]
                        break
                if topology:
                    break
        except OSError:
            pass
        out.append((node, vid_i, pid_i, hid_name or "Luxafor device", topology))
    log.info("hidraw discovery: %d Luxafor-Kandidat(en)", len(out))
    return out


NativeNode = tuple[str, int, int, str, str]
NativeNode_list = list[NativeNode]


class HidrawDevice:
    """Echte Luxafor-Gerät über /dev/hidrawN (kein hidapi)."""

    def __init__(self, node: str, vid: int, pid: int, name: str = "",
                 topology: str = "") -> None:
        self._node = node
        self.vendor_id = vid
        self.product_id = pid
        self.serial = ""
        self.topology = topology or ""
        self.path = node
        self._fd: int | None = None
        self.last_error: str | None = None
        protocol = GEN2 if pid == 0xF372 else GEN1
        self.protocol = protocol
        self._id = (f"flag:{self.topology}" if self.topology
                    else f"flag:{self._node.replace('/dev/', '')}")
        self.name = name or ("Luxafor Flag (Gen2)" if protocol == GEN2
                              else "Luxafor Flag")

    @property
    def device_id(self) -> str:
        return self._id

    @property
    def model(self) -> str:
        return self.name

    @property
    def is_open(self) -> bool:
        return self._fd is not None

    def open(self) -> None:
        if self._fd is not None:
            return
        try:
            self._fd = os.open(self._node, os.O_RDWR)
            self.last_error = None
            log.info("opened %s (%s, protocol %s)", self._node, self.model, self.protocol)
        except OSError as exc:
            self.last_error = f"open {self._node} failed: errno {exc.errno} " \
                              f"({os.strerror(exc.errno)})"
            raise OSError(self.last_error)

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            log.info("closed %s", self._node)

    def write(self, command: LedCommand) -> bool:
        if self._fd is None:
            self.last_error = "device not open"
            return False
        try:
            buf = command.as_bytes(self.protocol)
            n = os.write(self._fd, buf)
            self.last_error = None
            return n == len(buf)
        except OSError as exc:
            self.last_error = f"write failed: errno {exc.errno} ({os.strerror(exc.errno)})"
            log.warning("%s: %s", self._id, self.last_error)
            return False

    def set_color(self, rgb: tuple[int, int, int], led: Led = Led.ALL) -> bool:
        return self.write(LedCommand(kind="color", rgb=rgb, led=led))

    def off(self) -> bool:
        return self.write(LedCommand(kind="off"))

    def info(self) -> dict:
        return {
            "id": self.device_id,
            "name": self.name,
            "model": self.model,
            "path": self._node,
            "open": self.is_open,
            "error": self.last_error,
            "simulated": False,
            "serial": self.serial,
            "protocol": self.protocol,
        }

    def __repr__(self) -> str:
        return f"<HidrawDevice {self._id} {self._node} open={self.is_open}>"