"""Enumeration of Luxafor HID devices via hidapi."""
from __future__ import annotations

from typing import Any

from luxafor.core.logging_setup import get_logger
from luxafor.hardware.base import (
    FLAG_PRODUCT_ID,
    KNOWN_MODELS,
    LUXAFOR_VENDOR_ID,
    LuxaforDevice,
    looks_like_luxafor,
)
from luxafor.hardware.flag import FlagHidDevice

log = get_logger("hardware.discovery")

try:
    import hid as _hid  # python-hid / hidapi binding
    hid_import_error = None
except Exception as _hid_exc:  # ImportError or runtime binding failure
    _hid = None
    hid_import_error = str(_hid_exc)
hid: Any = _hid  # used by DeviceManager; tests may replace it


def all_hid_devices() -> list[dict]:
    """Returns every HID device hidapi can see (any vendor) — used by the
    diagnostics to answer 'does the kernel see the Luxafor at all?'."""
    if hid is None:
        return []
    try:
        infos = hid.enumerate(0, 0)
    except Exception as exc:
        log.warning("full hid enumerate failed: %s", exc)
        return []
    out = []
    for info in infos:
        try:
            out.append({
                "vendor_id": f"0x{info.get('vendor_id', 0):04x}",
                "product_id": f"0x{info.get('product_id', 0):04x}",
                "serial": (info.get("serial_number") or "")[:16],
                "product": (info.get("product_string") or "")[:40],
            })
        except Exception:
            continue
    return out


def enumerate_luxafor(hid_module: Any) -> list[FlagHidDevice]:
    """Returns all Luxafor devices currently visible to hidapi.

    Only PID 0xBADA (Flag) is officially verified; other Luxafor PIDs are
    surfaced as detected-but-untested devices and driven with the Flag driver.
    """
    found: list[FlagHidDevice] = []
    try:
        # enumerate all vendors — Gen2 devices carry the Microchip VID (0x04d8)
        infos = hid_module.enumerate(0, 0)
    except Exception as exc:
        log.warning("hid enumerate failed: %s", exc)
        return found
    for info in infos:
        interface = info.get("interface_number", info.get("interface", -1))
        if isinstance(interface, int) and interface not in (-1, 0):
            continue  # keyboards/audio interfaces of BT variants
        vid = info.get("vendor_id", 0)
        pid = info.get("product_id", 0)
        product = info.get("product_string", "") or ""
        if not looks_like_luxafor(vid, pid, product):
            continue
        try:
            path = info["path"]
        except KeyError:
            log.debug("hid entry without path skipped: %r", info)
            continue
        # Gen2 devices carry the Microchip VID — bind by path so the open()
        # call targets exactly this hidraw node (VID/PID open would also hit
        # other Microchip devices with matching PID, e.g. none).
        dev = FlagHidDevice(
            path=path,
            vendor_id=vid,
            product_id=pid,
            serial=info.get("serial_number", "") or "",
            hid_module=hid_module,
        )
        if pid not in KNOWN_MODELS:
            log.info("detected Luxafor device vid=0x%04x pid=0x%04x product=%r",
                     vid, pid, product)
        found.append(dev)
    return found


def supported_device_doc() -> dict:
    """Machine-readable summary of supported hardware for the UI/diagnostics."""
    return {
        "verified": [
            {"vendor_id": "0x04d2", "product_id": "0xbada", "model": "Luxafor Flag (Gen1)",
             "leds": 6, "zones": ["front", "back", "all", "1..6"],
             "effects": ["solid", "wave 1-5", "pattern 1-7", "strobe"]},
            {"vendor_id": "0x04d8", "product_id": "0xf372", "model": "Luxafor Flag (Gen2, Microchip)",
             "leds": 6, "zones": ["front", "back", "all", "1..6"],
             "effects": ["solid", "wave 1-5", "pattern 1-7", "strobe"],
             "note": "erkannt über HID-Produktstring 'LUXAFOR FLAG'; "
                     "Protokoll-Verifikation via scripts/probe_flag_protocol.py"},
        ],
        "untested": ["andere Luxafor-Modelle mit Produktstring 'Luxafor' werden mit dem Flag-Treiber angesprochen"],
        "notes": [
            "Das dokumentierte Flag-Protokoll enthält keinen Helligkeitsbefehl; "
            "Helligkeit wird per Software-Dämpfung umgesetzt.",
            "Wave-/Pattern-/Strobe-Effekte sind gerätefirmwareseitig vordefiniert.",
        ],
    }