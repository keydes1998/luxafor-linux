"""DeviceManager tests with a fake hidapi module and the real simulator logic."""
import asyncio

import pytest

from luxafor.core.database import Database
from luxafor.core.events import EventBus
from luxafor.core.devices import DeviceManager
from luxafor.hardware import discovery

pytestmark = pytest.mark.asyncio


class FakeHidEntry(dict):
    pass


class FakeHidModule:
    """Pretends one Luxafor Flag is connected."""

    def __init__(self):
        self.written = []
        self.devices = [{"path": b"abc", "serial_number": "SER42",
                         "product_id": 0xBADA, "vendor_id": 0x04D2,
                         "interface_number": 0}]
        self.open_should_fail = False

    def enumerate(self, vendor_id=0, product_id=0):
        return [d for d in self.devices
                if vendor_id in (0, d["vendor_id"]) and product_id in (0, d["product_id"])]

    def device(self):
        return FakeHidDevice(should_fail=self.open_should_fail)


class FakeHidDevice:
    def __init__(self, should_fail: bool = False):
        self.opened = False
        self.written: list[bytes] = []
        self.should_fail = should_fail

    def open_path(self, path):
        if self.should_fail:
            raise OSError("permission denied (fake)")
        self.opened = True

    def open(self, vid, pid):
        if self.should_fail:
            raise OSError("permission denied (fake)")
        self.opened = True

    @property
    def is_opened(self):
        return True

    def write(self, data: bytes):
        self.written.append(data)
        return len(data)

    def close(self):
        self.opened = False


@pytest.fixture
def isolated_sysfs(tmp_path, monkeypatch):
    """Schirmt die reale /sys+hidraw-Umgebung ab (Maschine kann einen echten
    Luxafor am Bus haben!)."""
    sysfs = tmp_path / "sysclass"
    sysfs.mkdir()
    monkeypatch.setenv("LUXAFOR_HIDRAW_SYSFS", str(sysfs))
    monkeypatch.setenv("LUXAFOR_HIDRAW_DEV_ROOT", str(tmp_path / "dev"))
    (tmp_path / "dev").mkdir()
    return sysfs


@pytest.fixture
def manager(tmp_path, isolated_sysfs):
    db = Database(tmp_path / "d.sqlite3")
    db.set_setting("hardware.simulator", "off")
    bus = EventBus()
    dm = DeviceManager(db, bus)
    return dm, db


async def test_real_flag_discovered_and_written(manager):
    dm, db = manager
    fake = FakeHidModule()
    discovery.hid = fake
    dm._scan_now()
    assert "flag:SER42" in dm.devices
    ok = dm.apply_color((10, 200, 30))
    assert ok
    dev = dm.devices["flag:SER42"]
    assert any(w == bytes([0x00, 0xFF, 0xFF, 10, 200, 30, 0, 0, 0]) for w in _all_writes(dev))
    dm.apply_off()
    assert any(w == bytes([0x00, 0xFF, 0xFF, 0, 0, 0, 0, 0, 0]) for w in _all_writes(dev))
    discovery.hid = None


def _all_writes(dev):
    out = []
    # FlagHidDevice wraps a fake hid 'device' object
    out += dev._device.written if hasattr(dev, "_device") else []
    return out


async def test_dimming_applied(manager):
    dm, db = manager
    db.set_setting("hardware.brightness", "50")
    fake = FakeHidModule()
    discovery.hid = fake
    dm._scan_now()
    dm.apply_color((100, 100, 100))
    dev = dm.devices["flag:SER42"]
    assert any(w == bytes([0x00, 0xFF, 0xFF, 50, 50, 50, 0, 0, 0]) for w in _all_writes(dev))
    discovery.hid = None


async def test_simulator_auto_when_no_hw(manager):
    dm, db = manager
    db.set_setting("hardware.simulator", "auto")
    fake = FakeHidModule()
    fake.devices = []  # nothing connected
    discovery.hid = fake
    dm._scan_now(allow_sim_add=True)   # boot scan erstellt den Simulator
    assert "sim:0" in dm.devices
    # Folge-Scans ohne Hardware: Simulator bleibt (kein neues, kein Entfernen)
    dm._scan_now()
    assert "sim:0" in dm.devices
    assert dm.apply_state("#FF0000", "solid")
    sim = dm.devices["sim:0"]
    assert sim.current() == (255, (255, 0, 0)) and sim.history()
    # now a real device appears → simulator retires
    fake.devices = [{"path": b"zz", "serial_number": "S1", "product_id": 0xBADA,
                     "vendor_id": 0x04D2, "interface_number": 0}]
    dm._scan_now()
    assert "flag:S1" in dm.devices and "sim:0" not in dm.devices
    discovery.hid = None
    dm.apply_off()


async def test_per_device_selective_write(manager):
    dm, db = manager
    db.set_setting("hardware.simulator", "off")
    fake = FakeHidModule()
    fake.devices.append({"path": b"q", "serial_number": "S2", "product_id": 0xBADA,
                         "vendor_id": 0x04D2, "interface_number": 0})
    discovery.hid = fake
    dm._scan_now()
    ok = dm.apply_color((1, 2, 3), device_ids=["flag:SER42"])
    assert ok
    dev1 = dm.devices["flag:SER42"]
    dev2 = dm.devices["flag:S2"]
    assert _all_writes(dev1) and not _all_writes(dev2)
    discovery.hid = None


async def test_flash_restores(manager):
    dm, db = manager
    fake = FakeHidModule()
    discovery.hid = fake
    dm._scan_now()
    dm.apply_state("#00AA00", "solid")
    dev = dm.devices["flag:SER42"]
    base_count = len(_all_writes(dev))
    ok = await dm.flash("#FF2200", duration=0.6, effect="strobe:4")
    assert ok
    await asyncio.sleep(1.2)
    dm2 = dm._current_state_string()
    assert dm2 == ("#00AA00", "solid")
    discovery.hid = None

async def test_detected_but_unopenable_stays_visible_without_simulator(manager):
    """Permission failure: real device must stay in the list (closed) and the
    simulator must NOT silently take over (that would hide hardware problems)."""
    dm, db = manager
    fake = FakeHidModule()
    fake.open_should_fail = True
    discovery.hid = fake
    try:
        dm._scan_now()
        assert "flag:SER42" in dm.devices
        dev = dm.devices["flag:SER42"]
        assert not dev.is_open
        assert dev.last_error and "permission denied" in dev.last_error
        assert "sim:0" not in dm.devices
        info = dev.info()
        assert info["open"] is False and info["error"]
        # writes fail gracefully
        assert dm.apply_color((5, 5, 5)) is False
    finally:
        discovery.hid = None


def test_gen2_detection_by_product_string_or_vid():
    from luxafor.hardware.base import looks_like_luxafor
    assert looks_like_luxafor(0x04D2, 0xBADA, "")
    assert looks_like_luxafor(0x04D8, 0xF372, "LUXAFOR FLAG")
    assert looks_like_luxafor(0x999A, 0x9999, "Luxafor Orb")  # Produktstring-Match
    assert not looks_like_luxafor(0x04D8, 0x003C, "Logic3 Controller")
    assert not looks_like_luxafor(0x04D8, 0x1234, "Weit weg")


def test_gen2_enumeration_picks_microchip_flag():
    from luxafor.hardware import discovery

    class FakeHid:
        @staticmethod
        def enumerate(vid=0, pid=0):
            entries = [
                {"path": b"g1", "vendor_id": 0x04D2, "product_id": 0xBADA,
                 "serial_number": "OLD", "interface_number": 0, "product_string": "Luxafor Flag"},
                {"path": b"g2", "vendor_id": 0x04D8, "product_id": 0xF372,
                 "serial_number": "GEN2", "interface_number": 0,
                 "product_string": "LUXAFOR FLAG"},
                {"path": b"x", "vendor_id": 0x04D8, "product_id": 0x003C,
                 "serial_number": "", "interface_number": 0, "product_string": "Other"},
                {"path": b"z", "vendor_id": 0x046D, "product_id": 0xC52B,
                 "serial_number": "", "interface_number": 0, "product_string": "USB Receiver"},
            ]
            return [d for d in entries
                    if vid in (0, d["vendor_id"]) and pid in (0, d["product_id"])]

    dm_mod = discovery
    dm_mod.hid = FakeHid()
    try:
        found = discovery.enumerate_luxafor(FakeHid)
        ids = [(d.vendor_id, d.product_id) for d in found]
        assert (0x04D2, 0xBADA) in ids
        assert (0x04D8, 0xF372) in ids
        # keine anderen Geräte (Microchip-Andere, Logitech)
        assert (0x04D8, 0x003C) not in ids and (0x046D, 0xC52B) not in ids
    finally:
        dm_mod.hid = None
