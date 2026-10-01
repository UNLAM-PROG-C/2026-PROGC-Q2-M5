"""Utilidades comunes de las pruebas."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fdc import protocol as P  # noqa: E402
from fdc.config import PHYSICS_DT  # noqa: E402
from fdc.sim.match import Match  # noqa: E402


def playing_match(seed=1, spawn_powers=False):
    """Partido ya en juego efectivo (sin cuenta regresiva)."""
    m = Match(1, seed=seed)
    m.phase = P.PHASE_PLAYING
    m.phase_left = 0.0
    if not spawn_powers:
        m.powers.spawn_timer = 1e9
    return m


def run(m, seconds, inputs=None):
    """Avanza 'seconds' de simulación y devuelve todos los eventos."""
    events = []
    for i in range(int(round(seconds / PHYSICS_DT))):
        if inputs:
            inputs(m, i)
        events += m.step(PHYSICS_DT)
    return events


def count(events, etype):
    return sum(1 for e in events if e[0] == etype)
