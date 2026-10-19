"""Protocol-encoding tests for the Luxafor Flag driver (documented commands)."""
import pytest

from luxafor.hardware.base import (
    Led, LedCommand, dim_rgb, format_color, parse_color, clamp8,
)


def test_color_all():
    cmd = LedCommand(kind="color", rgb=(255, 0, 17), led=Led.ALL)
    assert cmd.encode() == (0xFF, 0xFF, 255, 0, 17, 0, 0, 0)
    assert cmd.as_bytes() == bytes([0x00, 0xFF, 0xFF, 255, 0, 17, 0, 0, 0])


def test_color_front_back():
    assert LedCommand(kind="color", rgb=(1, 2, 3), led=Led.FRONT).encode()[:2] == (0xFF, 0x41)
    assert LedCommand(kind="color", rgb=(1, 2, 3), led=Led.BACK).encode()[:2] == (0xFF, 0x42)
    assert LedCommand(kind="color", rgb=(9, 9, 9), led=Led.LED_3).encode()[:2] == (0xFF, 0x03)


def test_off():
    assert LedCommand(kind="off").encode() == (0xFF, 0xFF, 0, 0, 0, 0, 0, 0)


def test_wave():
    cmd = LedCommand(kind="wave", rgb=(10, 20, 30), wave_type=2, wave_delay=3, repeat=1)
    assert cmd.encode() == (0x03, 2, 10, 20, 30, 3, 1, 0)
    with pytest.raises(AssertionError):
        LedCommand(kind="wave", rgb=(0, 0, 0), wave_type=9).encode()
    with pytest.raises(AssertionError):
        LedCommand(kind="wave", rgb=(0, 0, 0), wave_type=0).encode()


def test_pattern():
    cmd = LedCommand(kind="pattern", pattern_id=4, repeat=2)
    assert cmd.encode() == (0x04, 4, 2, 0, 0, 0, 0, 0)
    with pytest.raises(AssertionError):
        LedCommand(kind="pattern", pattern_id=8).encode()


def test_strobe():
    cmd = LedCommand(kind="strobe", rgb=(0, 255, 0), led=Led.ALL, speed=8, repeat=3)
    assert cmd.encode() == (0x05, 0xFF, 0, 255, 0, 8, 3, 0)


def test_parse_color():
    assert parse_color("#FF8000") == (255, 128, 0)
    assert parse_color("FF8000") == (255, 128, 0)
    assert parse_color("#F80") == (255, 136, 0)
    assert parse_color((0, 300, -5)) == (0, 255, 0)
    with pytest.raises(ValueError):
        parse_color("#GGGGGG")
    with pytest.raises(ValueError):
        parse_color("12")
    assert format_color((255, 128, 0)) == "#FF8000"


def test_dim_rgb():
    assert dim_rgb((255, 0, 0), 100) == (255, 0, 0)
    assert dim_rgb((255, 255, 255), 50) == (128, 128, 128)
    assert dim_rgb((200, 200, 200), 10) == (20, 20, 20)
    assert dim_rgb((255, 255, 255), 5) == (13, 13, 13)  # floor at 5 %


def test_clamp():
    assert clamp8(0) == 0 and clamp8(255) == 255 and clamp8(300) == 255 and clamp8(-1) == 0


def test_led_from_value_or_name():
    assert Led.from_value_or_name("all") is Led.ALL
    assert Led.from_value_or_name(0) is Led.ALL
    assert Led.from_value_or_name("front") is Led.FRONT
    assert Led.from_value_or_name("back") is Led.BACK
    assert Led.from_value_or_name(3) is Led.LED_3
    assert Led.from_value_or_name("led_5") is Led.LED_5
    assert Led.from_value_or_name(0x41) is Led.FRONT
    with pytest.raises(ValueError):
        Led.from_value_or_name("middle")
    with pytest.raises(ValueError):
        Led.from_value_or_name(99)


def test_simulator_records():
    from luxafor.hardware.simulator import SimulatorDevice
    sim = SimulatorDevice("sim:x")
    sim.open()
    assert sim.is_open
    assert sim.write(LedCommand(kind="color", rgb=(1, 2, 3), led=Led.ALL))
    assert sim.current() == (int(Led.ALL), (1, 2, 3))
    assert sim.write(LedCommand(kind="off"))
    assert sim.current() == (int(Led.ALL), (0, 0, 0))
    assert len(sim.history()) == 2
    info = sim.info()
    assert info["simulated"] is True and info["open"] is True

def test_gen2_solid_color():
    cmd = LedCommand(kind="color", rgb=(255, 0, 17), led=Led.ALL)
    assert cmd.encode("gen2") == (0x01, 0xFF, 255, 0, 17, 0, 0, 0)
    assert cmd.as_bytes("gen2") == bytes([0x00, 0x01, 0xFF, 255, 0, 17, 0, 0, 0])


def test_gen2_front_back_are_swapped():
    gen2 = LedCommand(kind="color", rgb=(1, 2, 3), led=Led.FRONT)
    assert gen2.encode("gen2")[:2] == (0x01, 0x42)
    gen2b = LedCommand(kind="color", rgb=(1, 2, 3), led=Led.BACK)
    assert gen2b.encode("gen2")[:2] == (0x01, 0x41)
    # gen1 bleibt: front=0x41, back=0x42
    g1 = LedCommand(kind="color", rgb=(1, 2, 3), led=Led.FRONT)
    assert g1.encode("gen1")[:2] == (0xFF, 0x41)


def test_gen2_strobe_layout():
    cmd = LedCommand(kind="strobe", rgb=(0, 255, 0), led=Led.ALL, speed=4, repeat=6)
    assert cmd.encode("gen2") == (0x03, 0xFF, 0, 255, 0, 4, 0, 6)


def test_gen2_wave_layout():
    cmd = LedCommand(kind="wave", rgb=(10, 20, 30), wave_type=2, wave_delay=3, repeat=1)
    assert cmd.encode("gen2") == (0x04, 2, 10, 20, 30, 0, 1, 3)


def test_gen2_pattern_and_off():
    assert LedCommand(kind="pattern", pattern_id=5, repeat=2).encode("gen2") == (0x06, 5, 2, 0, 0, 0, 0, 0)
    assert LedCommand(kind="off").encode("gen2") == (0x00, 0x4F, 0, 0, 0, 0, 0, 0)  # 'O' = off


def test_protocol_for():
    from luxafor.hardware.base import protocol_for, GEN2, GEN1
    assert protocol_for(0x04D8, 0xF372) == GEN2
    assert protocol_for(0x04D2, 0xBADA) == GEN1
    assert protocol_for(0x999A, 0x1111) == GEN1  # unbekannt → klassisch'
