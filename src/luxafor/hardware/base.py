"""Hardware abstraction for Luxafor devices.

Only documented Luxafor HID protocol commands are used. Two documented
protocol generations exist (byte 0 of every HID report is the report id 0x00):

Gen1 (Flag "classic", VID 0x04D2, PID 0xBADA):
    Color  : 0xFF  LED  R   G   B
    Wave   : 0x03  WaveType  R  G  B  Delay  Repeat
    Pattern: 0x04  PatternID  Repeat
    Strobe : 0x05  LED  R  G  B  Speed  Repeat
    Off    : Color command with R=G=B=0
    LED codes: 1..6 individual, 0x41 front, 0x42 back, 0xFF all

Gen2 (Flag 2 / Microchip hardware, VID 0x04D8, PID 0xF372; also official
spec of the luxafor-cli / luxafor Rust crate):
    Simple/Off: 0x00  COLOR      (color letters; 'O' = off)
    Solid     : 0x01  LED  R  G  B
    Fade      : 0x02  LED  R  G  B  Time
    Strobe    : 0x03  LED  R  G  B  Speed  0x00  Repeat
    Wave      : 0x04  WaveType  R  G  B  0x00  Repeat  Speed
    Pattern   : 0x06  PatternType  Repeat
    Productivity: 0x0A  COLOR
    Version   : 0x80 (responses 0x80, fw, serial-hi, serial-lo)
    LED codes: 1..3 front bottom..top, 4..6 back bottom..top,
               0x41 all back, 0x42 all front, 0xFF all
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum

# USB ids. Verified instances (see README "Unterstützte Geräte"):
#   Luxafor Flag (Gen1, "classic"):  VID 0x04D2, PID 0xBADA
#   Luxafor Flag (Gen2, Microchip):  VID 0x04D8, PID 0xF372  ("LUXAFOR FLAG" product string)
# The Gen2 device reports VID of Microchip Technology; the reliable marker is
# the HID product string, so detection matches on it as well.
LUXAFOR_VENDOR_ID = 0x04D2
FLAG_PRODUCT_ID = 0xBADA
LUXAFOR_GEN2_VENDOR_ID = 0x04D8
FLAG_GEN2_PRODUCT_ID = 0xF372

KNOWN_MODELS: dict[int, str] = {
    FLAG_PRODUCT_ID: "Luxafor Flag",
    FLAG_GEN2_PRODUCT_ID: "Luxafor Flag (Gen2)",
}

GEN1 = "gen1"
GEN2 = "gen2"

# Gen2 pattern ids (documented): 1 traffic lights, 2..4 random, 5 police,
# 6..7 random. Gen1: 1 traffic, 2..3 random, 4 police, 5 rainbow, 6 sea, 7 white wave.
GEN2_PATTERN_RANGE = range(1, 8)


def protocol_for(vid: int, pid: int) -> str:
    """Determines the documented command layout of a device."""
    if pid == FLAG_GEN2_PRODUCT_ID or (vid == LUXAFOR_GEN2_VENDOR_ID and pid):
        return GEN2
    return GEN1


def looks_like_luxafor(vendor_id: int, product_id: int, product_string: str = "") -> bool:
    """Recognition of all known Luxafor hardware generations."""
    if vendor_id == LUXAFOR_VENDOR_ID:
        return True
    if vendor_id == LUXAFOR_GEN2_VENDOR_ID and product_id == FLAG_GEN2_PRODUCT_ID:
        return True
    return "luxafor" in (product_string or "").lower()


class Led(IntEnum):
    LED_1 = 0x01
    LED_2 = 0x02
    LED_3 = 0x03
    LED_4 = 0x04
    LED_5 = 0x05
    LED_6 = 0x06
    FRONT = 0x41    # all LEDs on the front side
    BACK = 0x42     # all LEDs on the back side
    ALL = 0xFF

    @staticmethod
    def from_value_or_name(value: int | str) -> "Led":
        if isinstance(value, str):
            value = value.strip().lower()
            names = {m.name.lower(): m for m in Led}
            if value in names:
                return names[value]
            if value in ("all", "alle"):
                return Led.ALL
            if value in ("front", "vorseite"):
                return Led.FRONT
            if value in ("back", "rückseite"):
                return Led.BACK
            try:
                return Led.from_value_or_name(int(value))
            except ValueError:
                raise ValueError(f"unknown LED zone: {value!r}")
        if 0 <= int(value) <= 6:
            return Led(int(value)) if value else Led.ALL
        return Led(value)


# --- color helpers -----------------------------------------------------------
def clamp8(v: int) -> int:
    return max(0, min(255, int(v)))


def parse_color(value: str | tuple[int, int, int] | list[int]) -> tuple[int, int, int]:
    """Accepts '#RRGGBB', 'RRGGBB', or an (r, g, b) triple."""
    if isinstance(value, (tuple, list)):
        r, g, b = value
        return clamp8(r), clamp8(g), clamp8(b)
    v = str(value).strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise ValueError(f"invalid color: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def format_color(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def dim_rgb(rgb: tuple[int, int, int], brightness_pct: int) -> tuple[int, int, int]:
    """Software dimming used because the Flag protocol has no brightness command."""
    if brightness_pct >= 100:
        return rgb[0], rgb[1], rgb[2]
    factor = max(5, min(100, brightness_pct)) / 100.0
    return (clamp8(round(rgb[0] * factor)),
            clamp8(round(rgb[1] * factor)),
            clamp8(round(rgb[2] * factor)))


# --- commands ---------------------------------------------------------------
WAVE_RANGE = range(1, 6)       # documented wave types 1..5
PATTERN_RANGE = range(1, 8)    # documented patterns 1..7


GEN2_COLOR_LETTERS = {
    "red": 0x52, "green": 0x47, "blue": 0x42, "cyan": 0x43,
    "magenta": 0x4D, "yellow": 0x59, "white": 0x57, "off": 0x4F,
}


def _gen2_color_byte(rgb: tuple[int, int, int]) -> int | None:
    """Gen2 'Simple'/'Productivity' commands take color letters, not RGB."""
    r, g, b = rgb
    if g >= 128 and r < 80 and b < 80:
        return GEN2_COLOR_LETTERS["green"]
    if r >= 128 and g < 80 and b < 80:
        return GEN2_COLOR_LETTERS["red"]
    if b >= 128 and r < 80 and g < 80:
        return GEN2_COLOR_LETTERS["blue"]
    if r >= 128 and g >= 128 and b < 80:
        return GEN2_COLOR_LETTERS["yellow"]
    if r >= 128 and g >= 128 and b >= 128:
        return GEN2_COLOR_LETTERS["white"]
    return None


@dataclass(frozen=True)
class LedCommand:
    kind: str                     # color | wave | pattern | strobe | off
    rgb: tuple[int, int, int] = (0, 0, 0)
    led: Led | None = None
    wave_type: int | None = None
    wave_delay: int = 1           # seconds per step (gen1) / cycle speed (gen2)
    repeat: int = 0               # 0 = infinite
    speed: int = 4                # strobe speed 0..255 (lower = faster)
    pattern_id: int | None = None

    def _led_codes(self, protocol: str) -> tuple[int, int, int]:
        """Returns (individual, front_all, back_all) codes per protocol.
        Gen1: front=0x41/back=0x42 — Gen2: front=0x42/back=0x41 (documented)."""
        front, back = (0x42, 0x41) if protocol == GEN2 else (0x41, 0x42)
        return (int(self.led), front, back)

    def encode(self, protocol: str = GEN1) -> tuple[int, int, int, int, int, int, int, int]:
        """Encodes into the documented 8-byte payload of the given protocol."""
        rgb = self.rgb
        if self.kind == "off":
            if protocol == GEN2:
                return (0x00, GEN2_COLOR_LETTERS["off"], 0, 0, 0, 0, 0, 0)
            return (0xFF, int(Led.ALL), 0, 0, 0, 0, 0, 0)
        if self.kind == "color":
            assert self.led is not None, "color command requires LED zone"
            individual, front, back = self._led_codes(protocol)
            led = int(Led.ALL) if self.led is Led.ALL else (
                front if self.led is Led.FRONT else
                back if self.led is Led.BACK else individual)
            if protocol == GEN2:
                return (0x01, led, rgb[0], rgb[1], rgb[2], 0, 0, 0)
            return (0xFF, led, rgb[0], rgb[1], rgb[2], 0, 0, 0)
        if self.kind == "wave":
            assert self.wave_type in WAVE_RANGE, "wave type must be 1..5 (0x05 undocumented)"
            if protocol == GEN2:
                return (0x04, self.wave_type, rgb[0], rgb[1], rgb[2], 0,
                        clamp8(self.repeat), clamp8(self.wave_delay))
            return (0x03, self.wave_type, rgb[0], rgb[1], rgb[2],
                    clamp8(self.wave_delay), clamp8(self.repeat), 0)
        if self.kind == "pattern":
            if protocol == GEN2:
                assert self.pattern_id in GEN2_PATTERN_RANGE, "pattern must be 1..7"
                return (0x06, self.pattern_id, clamp8(self.repeat), 0, 0, 0, 0, 0)
            assert self.pattern_id in PATTERN_RANGE, "pattern must be 1..7"
            return (0x04, self.pattern_id, clamp8(self.repeat), 0, 0, 0, 0, 0)
        if self.kind == "strobe":
            assert self.led is not None, "strobe command requires LED zone"
            individual, front, back = self._led_codes(protocol)
            led = int(Led.ALL) if self.led is Led.ALL else (
                front if self.led is Led.FRONT else
                back if self.led is Led.BACK else individual)
            if protocol == GEN2:
                return (0x03, led, rgb[0], rgb[1], rgb[2],
                        clamp8(self.speed), 0, clamp8(self.repeat))
            return (0x05, led, rgb[0], rgb[1], rgb[2],
                    clamp8(self.speed), clamp8(self.repeat), 0)
        raise ValueError(f"unknown command kind: {self.kind!r}")

    def as_bytes(self, protocol: str = GEN1) -> bytes:
        """Full HID write buffer (report id 0x00 + payload)."""
        return bytes([0x00] + list(self.encode(protocol)))


class LuxaforDevice(ABC):
    """Base class of the device abstraction. One instance represents one physical
    or simulated device identified by a stable id."""

    def __init__(self, device_id: str, name: str, model: str, path: str | None) -> None:
        self.device_id = device_id
        self.name = name
        self.model = model
        self.path = path
        self.last_error: str | None = None

    @property
    @abstractmethod
    def is_open(self) -> bool: ...

    @abstractmethod
    def open(self) -> None:
        """Establishes the connection. Raises OSError/HIDException on failure."""

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def write(self, command: LedCommand) -> bool:
        """Sends a command; returns True on success. Must not raise for runtime
        errors (return False and set last_error instead)."""

    def info(self) -> dict:
        return {
            "id": self.device_id,
            "name": self.name,
            "model": self.model,
            "path": self.path,
            "open": self.is_open,
            "error": self.last_error,
            "simulated": False,
        }