"""Common helpers of the tests."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# pylint: disable=wrong-import-position
from fdc import config  # noqa: E402
from fdc import protocol  # noqa: E402
from fdc.sim import match  # noqa: E402

NO_SPAWN = 1e9      # s: a power spawn timer that never fires


def playing_match(seed=1, spawn_powers=False):
    """Match already in play (no countdown)."""
    m = match.Match(1, seed=seed)
    m.phase = protocol.PHASE_PLAYING
    m.phase_left = 0.0
    if not spawn_powers:
        m.powers.spawn_timer = NO_SPAWN
    return m


def run(m, seconds, inputs=None):
    """Advances 'seconds' of simulation and returns all the events."""
    events = []
    for i in range(int(round(seconds / config.PHYSICS_DT))):
        if inputs:
            inputs(m, i)
        events += m.step(config.PHYSICS_DT)
    return events


def count(events, etype):
    """How many events of that type."""
    return sum(1 for e in events if e[0] == etype)
