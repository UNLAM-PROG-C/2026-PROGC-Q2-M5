"""Rival automático del Mundialito.

Juega "como una persona más": mira el último estado del partido (el mismo
diccionario que dibuja la interfaz) y produce las mismas pulsaciones que el
teclado (izquierda, derecha, saltar, patear). No toca la simulación ni tiene
ventajas físicas: la dificultad sale de cosas humanas (tiempo de reacción,
errores, puntería del salto y decisión de defender).

No depende de pygame ni de procesos: sirve también para un rival online.
"""
import math
import random

from .config import Arena, BallSpec, PlayerSpec

# Un nivel por etapa del Mundialito (0 = Fecha 1 ... 5 = Final)
LEVELS = (
    {"name": "Muy fácil", "reaction": 0.34, "error": 0.20, "jump": 0.30, "kick": 0.55, "defend": 0.25},
    {"name": "Fácil", "reaction": 0.27, "error": 0.15, "jump": 0.45, "kick": 0.70, "defend": 0.40},
    {"name": "Normal", "reaction": 0.21, "error": 0.11, "jump": 0.60, "kick": 0.80, "defend": 0.55},
    {"name": "Difícil", "reaction": 0.16, "error": 0.07, "jump": 0.75, "kick": 0.90, "defend": 0.70},
    {"name": "Muy difícil", "reaction": 0.12, "error": 0.04, "jump": 0.88, "kick": 0.97, "defend": 0.85},
    {"name": "Leyenda", "reaction": 0.09, "error": 0.02, "jump": 0.96, "kick": 1.00, "defend": 0.95},
)


class Bot:
    def __init__(self, slot, level, seed=None):
        self.slot = slot                       # 0 = izquierda, 1 = derecha
        self.cfg = LEVELS[max(0, min(level, len(LEVELS) - 1))]
        self.rng = random.Random(seed)
        self.timer = 0.0
        self.move = 0
        self.want_jump = False
        self.want_kick = False
        self.jumps = 0                         # contadores acumulados, como el teclado
        self.kicks = 0
        self._prev_jump = False
        self._prev_kick = False

    def controls(self, st, dt):
        """[izquierda, derecha, saltos, patadas] a partir del último estado."""
        if st is None or st.get("phase") != "playing" or st.get("paused"):
            self.move, self.want_jump, self.want_kick = 0, False, False
        else:
            self.timer -= dt
            if self.timer <= 0:
                # decide cada "tiempo de reacción" (con algo de variación)
                self.timer = self.cfg["reaction"] * self.rng.uniform(0.8, 1.25)
                self._think(st)
        if self.want_jump and not self._prev_jump:
            self.jumps += 1
        if self.want_kick and not self._prev_kick:
            self.kicks += 1
        self._prev_jump, self._prev_kick = self.want_jump, self.want_kick
        return [self.move < 0, self.move > 0, self.jumps, self.kicks]

    # ------------------------------------------------------------------ decisión
    def _think(self, st):
        cfg, rng = self.cfg, self.rng
        me = st["players"][self.slot]
        rival = st["players"][1 - self.slot]
        b = st["ball"]
        d = 1 if self.slot == 0 else -1         # hacia dónde ataca
        s = me["scale"]
        R = PlayerSpec.HEAD_RADIUS * s
        mouth = Arena.GOAL_DEPTH if self.slot == 0 else Arena.WIDTH - Arena.GOAL_DEPTH

        # --- dónde pararse
        bx = b["x"] + b["vx"] * 0.15
        behind = d * (me["x"] - b["x"]) > 8      # la pelota quedó entre yo y mi arco
        danger = (b["vx"] * d < -150 or
                  (d * (b["x"] - Arena.WIDTH / 2) < 0 and abs(rival["x"] - b["x"]) < abs(me["x"] - b["x"])))
        if behind:
            target = b["x"] - d * R * 1.9          # volver por detrás de la pelota
        elif danger and rng.random() < cfg["defend"]:
            target = mouth + d * (abs(b["x"] - mouth) * 0.35 + R * 0.6)   # cubrir el arco
        else:
            target = bx - d * R * 0.7              # atacar empujando hacia el arco rival
        dx = target - me["x"]
        self.move = 0 if abs(dx) < R * 0.2 else (1 if dx > 0 else -1)

        # --- saltar: calcula cuándo llega la pelota (con la puntería del nivel)
        self.want_jump = False
        head_top = me["y"] - PlayerSpec.HEIGHT * s
        low_ball = b["y"] > head_top + R * 0.3
        if behind and me["ground"] and not me["frozen"] and low_ball and abs(b["x"] - me["x"]) < R * 2.6:
            # hay que volver y la pelota está cerca y baja: saltarla por encima
            # en lugar de llevársela por delante hacia el propio arco
            self.want_jump = rng.random() < 0.5 + cfg["defend"] * 0.5
        elif me["ground"] and not me["frozen"]:
            coming = abs(b["vx"]) > 1 and (b["x"] - me["x"]) * b["vx"] < 0
            if coming:
                tt = abs(b["x"] - me["x"]) / abs(b["vx"])
                yy = b["y"] + b["vy"] * tt + 0.5 * BallSpec.GRAVITY * tt * tt
                need = head_top - yy + b["r"] * 0.5
                if 0 < need < R * 4.2 and yy < Arena.FLOOR_Y - b["r"]:
                    v, g = PlayerSpec.JUMP_SPEED, PlayerSpec.GRAVITY
                    disc = v * v - 2 * g * need
                    t_rise = (v - math.sqrt(disc)) / g if disc > 0 else v / g
                    if tt <= t_rise + 0.05 and rng.random() < cfg["jump"]:
                        self.want_jump = True
            elif (abs(b["x"] - me["x"]) < R * 1.2 and head_top - R * 4.2 < b["y"] < head_top
                  and b["vy"] > 0 and rng.random() < cfg["jump"]):
                self.want_jump = True              # pelota cayendo encima: cabecear

        # --- patear: sólo si mira hacia el arco rival y la tiene enfrente
        fx = me["x"] + d * PlayerSpec.KICK_REACH_X * s
        fy = me["y"] - PlayerSpec.KICK_REACH_Y * s
        reach = PlayerSpec.KICK_RADIUS * s + b["r"]
        self.want_kick = (me["facing"] == d and not me["no_kick"]
                          and abs(b["x"] - fx) < reach + R * 0.25 and abs(b["y"] - fy) < reach + R * 0.5
                          and rng.random() < cfg["kick"])

        # --- errores humanos
        if rng.random() < cfg["error"]:
            self.move = rng.choice((-1, 0, 1))
            self.want_jump = False
