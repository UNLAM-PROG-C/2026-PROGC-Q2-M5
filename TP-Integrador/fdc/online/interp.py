"""Interpolación de estados en el cliente online.

El servidor manda unas 30 fotos por segundo y la pantalla dibuja 60: sin
suavizar, el movimiento se vería a saltos (y peor con la variación de la red).
El cliente dibuja "un poquito en el pasado", entre las dos últimas fotos.

Es sólo presentación: la simulación del servidor sigue decidiendo todo.
"""
from ..config import Online

TELEPORT = 160.0     # px: un salto mayor (saque del medio, gol) no se suaviza
HALF_TURN = 180.0    # grados
FULL_TURN = 360.0    # grados
MIN_GAP = 0.005      # s: se ignoran intervalos menores entre estados (llegaron juntos)
MAX_GAP = 0.2        # s: y mayores (una traba de la red no debe frenar el suavizado)
GAP_SMOOTHING = 0.2  # peso de cada intervalo nuevo en el promedio del ritmo de llegada


def _lerp(a, b, k):
    return a + (b - a) * k


def _lerp_angle(a, b, k):
    """Ángulos en grados (la pelota gira sin límite: se toma el camino corto)."""
    d = (b - a + HALF_TURN) % FULL_TURN - HALF_TURN
    return a + d * k


class Interpolator:
    def __init__(self):
        self.prev = None
        self.cur = None
        self.t_cur = 0.0
        self.interval = 1 / Online.STATE_HZ       # ritmo esperado hasta medir el real

    def reset(self):
        self.prev = self.cur = None

    def push(self, state, now):
        if self.cur is not None and state.get("seq", 0) <= self.cur.get("seq", 0):
            return False
        if self.cur is not None:
            gap = min(MAX_GAP, max(MIN_GAP, now - self.t_cur))
            self.interval += (gap - self.interval) * GAP_SMOOTHING     # promedio suave del ritmo real
        self.prev, self.cur = self.cur, state
        self.t_cur = now
        return True

    def sample(self, now):
        a, b = self.prev, self.cur
        if b is None or a is None or b.get("paused") or a.get("phase") != b.get("phase"):
            return b
        k = min(1.0, max(0.0, (now - self.t_cur) / self.interval))
        if k >= 1.0:
            return b
        out = dict(b)
        players = []
        for pa, pb in zip(a["players"], b["players"]):
            if abs(pa["x"] - pb["x"]) > TELEPORT or abs(pa["y"] - pb["y"]) > TELEPORT:
                players.append(pb)
                continue
            p = dict(pb)
            p["x"] = _lerp(pa["x"], pb["x"], k)
            p["y"] = _lerp(pa["y"], pb["y"], k)
            players.append(p)
        out["players"] = players
        ba, bb = a["ball"], b["ball"]
        if abs(ba["x"] - bb["x"]) <= TELEPORT and abs(ba["y"] - bb["y"]) <= TELEPORT:
            ball = dict(bb)
            ball["x"] = _lerp(ba["x"], bb["x"], k)
            ball["y"] = _lerp(ba["y"], bb["y"], k)
            ball["angle"] = _lerp_angle(ba["angle"], bb["angle"], k)
            out["ball"] = ball
        return out
