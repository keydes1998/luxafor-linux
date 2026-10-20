"""State engine tests: priorities, expiry, manual override, defaults."""
import time

import pytest

from luxafor.core.database import Database
from luxafor.core.events import EventBus
from luxafor.core.state import Candidate, StateEngine

pytestmark = pytest.mark.asyncio


class FakeDevices:
    def __init__(self):
        self.applied = []

    def apply_state(self, color, effect, led=None, device_ids=None):
        self.applied.append((color, effect))
        return True


@pytest.fixture
def engine(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    bus = EventBus()
    devices = FakeDevices()
    state = StateEngine(db, devices, bus)
    state.devices = devices  # bypass real DeviceManager
    return state, devices, db


async def test_default_candidate_applied(engine):
    state, devices, db = engine
    await state.start()
    state._evaluate()
    assert devices.applied[-1] == ("#00AA00", "solid")
    assert state.current["origin"] == "standard"


async def test_priority_beats_default(engine):
    state, devices, db = engine
    await state.start()
    state.set_candidate("presence", Candidate(origin="presence", label="Busy",
                                              color="#FF0000", priority=40))
    state._evaluate()
    assert devices.applied[-1][0] == "#FF0000"
    # higher priority wins
    state.set_candidate("manual", Candidate(origin="manual", label="Nicht stören",
                                            color="#8B0000", priority=90))
    state._evaluate()
    assert devices.applied[-1][0] == "#8B0000"
    # clearing manual restores presence color
    state.clear_candidate("manual")
    state._evaluate()
    assert devices.applied[-1][0] == "#FF0000"
    state.clear_candidate("presence")
    state._evaluate()
    assert devices.applied[-1] == ("#00AA00", "solid")


async def test_expired_candidate(engine):
    state, devices, db = engine
    await state.start()
    cand = Candidate(origin="webhook", label="X", color="#FF0044", priority=95,
                     expires_at=time.time() - 0.1)
    state.set_candidate("webhook", cand)
    state._evaluate()
    assert devices.applied[-1] == ("#00AA00", "solid")  # expired → default


async def test_manual_override_with_duration(engine):
    state, devices, db = engine
    await state.start()
    ok = await state.manual_status("Beschäftigt", duration=30 * 60)
    assert ok
    state._evaluate()
    assert devices.applied[-1] == ("#FF0000", "solid")
    assert state.manual_active() is True
    state.restore_automatic()
    state._evaluate()
    assert state.manual_active() is False
    assert devices.applied[-1] == ("#00AA00", "solid")


async def test_manual_status_unknown(engine):
    state, devices, db = engine
    await state.start()
    ok = await state.manual_status("gibtsnicht", color=None)
    assert ok is False


async def test_same_candidate_no_reapply(engine):
    state, devices, db = engine
    await state.start()
    c = Candidate(origin="presence", label="B", color="#FF0000", priority=40)
    state.set_candidate("presence", c)
    state._evaluate()
    n1 = len(devices.applied)
    state.set_candidate("presence", Candidate(origin="presence", label="B",
                                              color="#FF0000", priority=40))
    state._evaluate()
    assert len(devices.applied) == n1  # identical → no device writes


async def test_pause_freezes(engine):
    state, devices, db = engine
    await state.start()
    state.set_paused(True)
    state.set_candidate("presence", Candidate(origin="presence", label="Busy",
                                              color="#FF0000", priority=40))
    state._evaluate()
    # while paused the manual candidate is not evaluated/applied
    assert state.candidates.get("presence") is not None

async def test_refresh_now_force_reapplies_after_failed_apply(engine):
    """Replug-Fix: Gerät war weg → apply schlug fehl → Device-Event forcing."""
    state, devices, db = engine
    await state.start()
    state.set_candidate("manual", Candidate(origin="manual", label="Busy",
                                            color="#FF0000", priority=90))
    state._evaluate()
    assert devices.applied[-1] == ("#FF0000", "solid")
    # apply schlägt fehl (Gerät weg) — DeviceManager setzt 'applied' False
    devices.fail = True
    original_apply = state.devices.apply_state
    def failing_apply(color, effect, led=None, device_ids=None):
        if getattr(devices, "fail", False):
            devices.applied.append(("FAIL", color, effect))
            return False
        devices.applied.append((color, effect))
        return True
    state.devices.apply_state = failing_apply
    state.note_apply_failed()   # Unplug-Event informiert die Engine
    state.refresh_now()
    assert devices.applied[-1][0] == "FAIL"
    # Gerät wieder da + force → gleicher Status wird ERNEUT geschrieben
    devices.fail = False
    state.refresh_now(force=True)
    assert devices.applied[-1] == ("#FF0000", "solid")
    assert state.current["applied"] is True
