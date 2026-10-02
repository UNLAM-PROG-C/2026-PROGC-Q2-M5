"""Dibujo del partido a partir del ÚLTIMO estado recibido de la simulación.

La interfaz no calcula posiciones, goles ni efectos: sólo decide cómo se ven
(qué ángulo tiene el botín, cuánto rebota la cabeza, partículas, textos).
Estilo retro: píxeles de 2x2, fuente pixel art, tablero LED.

Medidas en px de la pantalla lógica; las que dicen "x escala" se multiplican
por el tamaño del jugador (los poderes lo agrandan o achican).
"""
import math
from collections import deque

import pygame

from .. import protocol as P
from ..config import CATEGORY_COLORS, PLAYER_COLORS, POWERS_BY_ID, PlayerSpec, PowerRules
from . import palette as C
from . import pixelfont
from .assets import draw_text
from .characters import CHARACTERS_BY_ID, short_name
from .icons import power_icon
from .layout import (CENTER_X, FONT_BANNER, FONT_COUNTDOWN, FONT_GO, FONT_GOAL, FONT_SMALL, FONT_TEXT, FRAME_LINE,
                     SCREEN_W, SHADOW_OFFSET)
from .retro import PX, bevel_box, scale_px
from .sprites import celebrate_pose, idle_pose
from .stadium import FLOOR, draw_goal_back, draw_goal_front, draw_shadow

CLOCK_EPSILON = 1e-6               # s: margen para que 3,0000001 s se muestre como 0:03 y no 0:04
SECONDS_PER_MINUTE = 60            # para mostrar el reloj como minutos:segundos

# --- patada: el botín se carga atrás, barre hacia adelante, queda arriba y vuelve (fracciones de la patada)
KICK_WINDUP_END = 0.15             # fin de la carga
KICK_SWING_END = 0.45              # fin del barrido
KICK_SWING_TIME = 0.30             # duración del barrido (de 0,15 a 0,45)
KICK_HOLD_END = 0.70               # fin de la pierna arriba
KICK_RETURN_TIME = 0.30            # duración de la vuelta a reposo (de 0,70 a 1)
KICK_WINDUP_ANGLE = 25             # grados hacia atrás al cargar
KICK_SWING_ARC = 125               # grados que recorre al barrer (de +25 a -100)
KICK_FORWARD_ANGLE = -100          # grados hacia adelante en lo más alto

# --- barrita de tiempo restante
TIMER_BAR_H = 6                    # px: alto total
TIMER_BAR_BORDER = 2               # px: borde oscuro alrededor de la parte que se vacía

# --- jugador
TRAIL_LENGTH = 6                   # posiciones recientes de la pelota que forman la estela
BALL_SHADOW_SCALE = 2.4            # la sombra de la pelota mide 2,4 veces su radio
PLAYER_SHADOW_W = 84               # px x escala: ancho de la sombra del jugador
PLAYER_SHADOW_ALPHA = 110          # opacidad de la sombra del jugador
AIR_UP_ANGLE = -30                 # grados del botín mientras sube en el salto...
AIR_DOWN_ANGLE = 10                # ...y mientras baja
WALK_MIN_SPEED = 25                # px/s: más lento que esto, el jugador está quieto
STRIDE_PX = 14.0                   # px recorridos por cada radián del paso
WALK_SWING = 22                    # grados que va y viene el botín al caminar
WALK_BOB_AT = 0.8                  # la cabeza rebota en los extremos del paso (|cos| mayor que esto)
# cartel "sin patada": cuadrado blanco con una cruz roja junto al botín
NO_KICK_BEHIND = 8                 # px detrás del jugador
NO_KICK_HEIGHT = 14                # px sobre los pies
NO_KICK_SIZE = 16                  # px: lado del cartel
NO_KICK_BORDER = 2                 # px: borde oscuro
NO_KICK_CROSS = (8, 4)             # cruz: (largo, grosor)
# rayas de velocidad detrás del jugador rápido
SPEED_LINES_MIN = 60               # px/s: más lento que esto no se dibujan
SPEED_LINE_HEIGHTS = (24, 50, 76)  # px x escala sobre los pies
SPEED_LINE_BEHIND = 44             # px x escala detrás del centro del jugador
SPEED_LINE_STAGGER = 6             # px x escala que se corre cada raya respecto de la anterior
SPEED_LINE_LEN = 18                # px: largo de una raya...
SPEED_LINE_WOBBLE = 8              # ...que se estira y encoge hasta 8 px
SPEED_LINE_HZ = 20                 # ritmo de ese estirarse
# resorte bajo el jugador con súper salto
SPRING_W = 70                      # px x escala
SPRING_H = 14                      # px
SPRING_DROP = 2                    # px bajo el piso
SPRING_LINE = 4                    # px: grosor
# arco que muestra el alcance de la patada
KICK_ARC_FROM = 0.12               # se ve desde esta fracción de la patada...
KICK_ARC_TO = 0.75                 # ...hasta esta
KICK_ARC_GROW = 0.4                # fracción de la patada en la que el arco termina de abrirse
KICK_ARC_HEIGHT = 20               # px x escala: centro del arco sobre los pies
KICK_ARC_REACH_SHARE = 0.6         # el arco llega al alcance de la patada más 60 % del radio del botín
KICK_ARC_DOTS = 7                  # puntos del arco
KICK_ARC_START = -10               # grados del primer punto (apenas detrás de la vertical)
KICK_ARC_SPAN = 110                # grados que abarca el arco abierto
KICK_ARC_GROWTH = 3                # los puntos crecen hacia la punta: un píxel de arte cada 1,5 puntos
# flechita sobre la cabeza (color del jugador) y efectos activos
INDICATOR_GAP = 12                 # px entre la cabeza y la flechita
ARROW_OUTER = ((-12, -16), (12, -16), (0, 2))   # triángulo oscuro (relativo a la punta de la flecha)
ARROW_INNER = ((-8, -14), (8, -14), (0, -2))    # triángulo de color
LAST_TOUCH_BALL_R = 10             # px: radio de la pelotita del "último toque"
LAST_TOUCH_BALL_AT = (16, -8)      # dónde va esa pelotita respecto de la flecha
MINI_EFFECT_STEP = 30              # px entre los íconos de efectos sobre la cabeza
MINI_EFFECT_RAISE = 40             # px sobre la flechita
MINI_ICON = 28                     # px: ícono de un efecto activo
MINI_TIMER_GAP = 2                 # px entre el ícono y su barrita de tiempo
MIN_DURATION = 0.001               # s: evita dividir por cero en las barritas de tiempo
# bloque de hielo del jugador congelado
ICE_W = 96                         # px x escala
ICE_EXTRA_H = 12                   # px x escala sobre el alto del jugador
ICE_SINK = 4                       # px que se hunde bajo los pies
ICE_FILL = (170, 225, 255, 80)     # celeste translúcido
ICE_EDGE = (240, 250, 255, 230)    # borde blanco del bloque
ICE_EDGE_LINE = 4                  # px: grosor del borde
ICE_STREAKS = 3                    # reflejos diagonales
ICE_STREAK_FIRST = 0.2             # el primero, al 20 % del ancho...
ICE_STREAK_STEP = 0.25             # ...y los demás cada 25 %
ICE_STREAK_STEPS = 6               # escalones de cada reflejo
ICE_STREAK_TOP = 10                # px desde arriba del bloque
ICE_STREAK_COLOR = (255, 255, 255, 180)   # blanco casi opaco
# pelota
TRAIL_SPEED = 560                  # px/s: más rápido que esto la pelota deja estela
TRAIL_MIN_SHARE = 0.4              # la estela más vieja mide 40 % del radio...
TRAIL_EXTRA_SHARE = 0.6            # ...y la más nueva, 40 % + 60 %
TRAIL_ALPHA = 70                   # opacidad de la estela más vieja...
TRAIL_ALPHA_STEP = 20              # ...que sube de a 20 hacia la pelota
BALL_RING_GAP = 6                  # px entre la pelota y el aro del poder que tiene encima
EFFECT_RING_LINE = 2               # px: grosor de los aros de color (pelota y objeto de poder)
# objeto de poder en la cancha
PICKUP_BOB_HZ = 3.2                # ritmo con que flota (rad/s)
PICKUP_BLINK_TIME = 1.5            # s: en los últimos segundos parpadea...
PICKUP_BLINK_HZ = 8                # ...con este ritmo
PICKUP_RING_GAP = 6                # px entre el ícono y su aro
PICKUP_LABEL_GAP = 14              # px entre el objeto y su nombre
LABEL_SCALE = 2                    # escala de la fuente pixel art de los rótulos de la cancha
# bomba
BOMB_BLINK_HZ = 8                  # parpadeo de la mecha al empezar...
BOMB_BLINK_EXTRA = 16              # ...que se acelera hasta 8 + 16 al final
BLAST_DOTS = 40                    # puntos del círculo que marca el alcance de la explosión
BLAST_DOTS_HZ = 10                 # los puntos titilan alternados con este ritmo
BLAST_DOT = 4                      # px: lado de cada punto
BOMB_R = 20                        # px: radio de la bomba
BOMB_CORE_R = 16                   # px: radio del centro que parpadea
BOMB_SHINE = (-8, -8, 4, 4)        # brillo (relativo al centro: x, y, ancho, alto)
BOMB_FUSE = (6, -22, 6, 8)         # mecha
BOMB_SPARK = (10, -28, 6, 6)       # chispa de la mecha
BOMB_SPARK_ON = (255, 220, 90)     # chispa encendida (apagada: naranja)
BOMB_LABEL_GAP = 30                # px sobre el centro: segundos que faltan

# --- tablero de arriba
BOARD = (500, 92)                  # (ancho, alto)
BOARD_TOP = 4                      # px desde arriba de la pantalla
BOARD_INSET = 8                    # px entre el marco y la pantalla LED
PLATE = (56, 60)                   # recuadro con la cara de cada jugador (ancho, alto)
PLATE_INSET = 6                    # px desde el costado de la pantalla LED
PLATE_LINE = 2                     # px: borde del recuadro
SCORE_LED_SCALE = 7                # tamaño de los puntos LED de los goles
SCORE_X = 118                      # px a cada lado del centro donde van los goles
SCORE_RAISE = 4                    # px sobre el centro
CLOCK_WARNING = 10                 # s: en los últimos segundos el reloj parpadea en rojo...
CLOCK_BLINK_HZ = 4                 # ...con este ritmo
CLOCK_LED_SCALE = 6                # tamaño de los puntos LED del reloj
CLOCK_RAISE = 6                    # px sobre el centro
STATE_TEXT_COLOR = (180, 190, 200)  # gris claro: "EN JUEGO", "GOL", "EN PAUSA"
STATE_TEXT_BOTTOM = 10             # px desde abajo de la pantalla LED
NAME_GAP = 12                      # px entre el tablero y los carteles con los nombres
NAME_TOP = 8                       # px desde arriba del tablero
NAME_PAD = (14, 10)                # px que se agranda cada cartel alrededor del nombre (ancho, alto)
HUD_EFFECT = (210, 40)             # recuadro de un efecto activo (ancho, alto)
HUD_EFFECTS_TOP = 46               # primer efecto de cada jugador, desde arriba del tablero
HUD_EFFECT_STEP = 46               # px entre efectos
HUD_ICON = 28                      # px: ícono del efecto
HUD_ICON_INSET = 2                 # px desde la esquina del recuadro
HUD_TEXT_X = 36                    # a quién afecta, desde el borde izquierdo
HUD_TEXT_Y = 4                     # textos, desde arriba del recuadro
HUD_TIME_MARGIN = 4                # segundos que quedan, desde el borde derecho
HUD_TIMER_BOTTOM = 10              # barrita de tiempo, desde abajo del recuadro
CENTER_EFFECTS_GAP = 12            # px entre el tablero y los efectos de la pelota o del partido
NOTE_PADDING = 20                  # nota "X pidió la pausa": px que se suman al texto...
NOTE_H = 26                        # ...alto...
NOTE_GAP = 10                      # ...px bajo el tablero...
NOTE_BOTTOM_GAP = 8                # ...y px hasta lo que sigue debajo

# --- carteles del centro
COUNTDOWN_Y = 330                  # números de la cuenta regresiva y "¡YA!"
COUNTDOWN_GROWTH = 32              # el número arranca 32 puntos más grande y se achica en el segundo
FONT_STEP = 8                      # los tamaños de letra van de a 8 (una escala entera de la fuente)
GOLDEN_Y = 186                     # "¡GOL DE ORO!"
GOLDEN_NOTE_Y = 240                # "Empate: el próximo gol gana"
GOAL_BAND_TOP = 262                # franja del gol: borde superior...
GOAL_BAND_H = 132                  # ...y alto
GOAL_BAND_BORDER = 6               # px: borde oscuro arriba y abajo
GOAL_STRIPE = 6                    # px: franjas con el color del que hizo el gol
GOAL_WOBBLE_PX = 4                 # "¡GOOOL!" salta 4 px...
GOAL_WOBBLE_HZ = 8                 # ...con este ritmo
GOAL_TEXT_Y = 312                  # "¡GOOOL!"
GOAL_SCORER_Y = 368                # nombre de quien lo hizo


def fmt_clock(secs):
    secs = max(0, int(math.ceil(secs - CLOCK_EPSILON)))
    return f"{secs // SECONDS_PER_MINUTE:01d}:{secs % SECONDS_PER_MINUTE:02d}"


def kick_angle(prog):
    """Ángulo del botín durante la patada (0 = reposo; negativo = hacia adelante)."""
    if prog < KICK_WINDUP_END:
        return KICK_WINDUP_ANGLE * prog / KICK_WINDUP_END
    if prog < KICK_SWING_END:
        return KICK_WINDUP_ANGLE - KICK_SWING_ARC * (prog - KICK_WINDUP_END) / KICK_SWING_TIME
    if prog < KICK_HOLD_END:
        return KICK_FORWARD_ANGLE
    return KICK_FORWARD_ANGLE - KICK_FORWARD_ANGLE * (prog - KICK_HOLD_END) / KICK_RETURN_TIME


def timer_bar(surf, x, y, w, frac, color):
    """Barra de tiempo restante estilo retro."""
    b = TIMER_BAR_BORDER
    pygame.draw.rect(surf, C.INK, (x, y, w, TIMER_BAR_H))
    pygame.draw.rect(surf, C.CREAM_DARK, (x + b, y + b, w - 2 * b, TIMER_BAR_H - 2 * b))
    fill = int((w - 2 * b) * max(0.0, min(1.0, frac)))
    if fill > 0:
        pygame.draw.rect(surf, color, (x + b, y + b, fill, TIMER_BAR_H - 2 * b))


def snap(v):
    """Lleva una coordenada a la grilla de píxeles de arte."""
    return int(v) // PX * PX


def _around(x, y, rect):
    """Rectángulo (dx, dy, ancho, alto) relativo al punto (x, y)."""
    dx, dy, w, h = rect
    return x + dx, y + dy, w, h


class MatchRenderer:
    def __init__(self, app, characters):
        self.app = app
        self.sprites = app.sprites
        self.ball_sprite = app.ball_sprite
        self.background = app.background
        self.chars = list(characters)
        self.t = 0.0
        self.trail = deque(maxlen=TRAIL_LENGTH)
        self.kickoff_flash = 0.0
        self.goal_banner = None      # (tiempo restante, datos del gol)
        self.golden_flash = 0.0
        self.center_note = None      # texto chico debajo del marcador (online: "X pidió la pausa")

    def who(self, i, side_if_same=True):
        """Nombre del personaje (el lado y el color ya identifican a cada jugador).
        Si los dos eligieron el mismo, se aclara el lado."""
        name = short_name(CHARACTERS_BY_ID[self.chars[i]])
        if side_if_same and self.chars[0] == self.chars[1]:
            name += " (izq.)" if i == 0 else " (der.)"
        return name

    def reset(self):
        self.trail.clear()
        self.kickoff_flash = 0.0
        self.golden_flash = 0.0
        self.goal_banner = None

    def update(self, dt):
        self.t += dt
        self.kickoff_flash = max(0.0, self.kickoff_flash - dt)
        self.golden_flash = max(0.0, self.golden_flash - dt)
        if self.goal_banner:
            left, data = self.goal_banner
            self.goal_banner = (left - dt, data) if left - dt > 0 else None

    # ------------------------------------------------------------------ mundo
    def draw_world(self, surf, st, offset=(0, 0)):
        surf.blit(self.background, offset)
        goals = st["goals"]
        for side in (0, 1):
            draw_goal_back(surf, side, goals[side])
        for b in st.get("bombs", []):
            self._bomb(surf, b)
        if st.get("pickup"):
            self._pickup(surf, st["pickup"])
        ball = st["ball"]
        draw_shadow(surf, ball["x"], ball["r"] * BALL_SHADOW_SCALE, FLOOR - ball["y"] - ball["r"])
        for p in st["players"]:
            draw_shadow(surf, p["x"], PLAYER_SHADOW_W * p["scale"], FLOOR - p["y"], PLAYER_SHADOW_ALPHA)
        for i in sorted(range(2), key=lambda k: st["players"][k]["y"]):
            self._player(surf, i, st["players"][i], st)
        self._ball(surf, ball, st)
        for side in (0, 1):
            hl = None
            for e in st.get("effects", []):
                if e["target"] == f"goal{side}":
                    hl = CATEGORY_COLORS[POWERS_BY_ID[e["power"]].category]
            draw_goal_front(surf, side, goals[side], hl)

    def pose(self, i, p, phase):
        """(ángulo del botín, rebote de la cabeza en px nativos)."""
        t = self.t
        if p["frozen"]:
            return 0, 0
        if p["celebrate"] and phase in (P.PHASE_GOAL, P.PHASE_FINISHED):
            return celebrate_pose(t)
        if p["kick"] >= 0:
            return kick_angle(p["kick"]), 0
        if not p["ground"]:
            return (AIR_UP_ANGLE, 0) if p["vy"] < 0 else (AIR_DOWN_ANGLE, 0)
        if abs(p["vx"]) > WALK_MIN_SPEED:
            ph = p["stride"] / STRIDE_PX
            return WALK_SWING * math.sin(ph), (-1 if abs(math.cos(ph)) > WALK_BOB_AT else 0)
        return idle_pose(t, i)

    def _player(self, surf, i, p, st):
        f = 1 if p["facing"] >= 0 else -1
        ang, bob = self.pose(i, p, st["phase"])
        img, (fx, fy) = self.sprites.player(self.chars[i], f, ang, bob, PLAYER_COLORS[i],
                                            p["frozen"], p["scale"])
        surf.blit(img, (round(p["x"] - fx), round(p["y"] - fy)))
        s = p["scale"]
        mine = [e for e in st.get("effects", []) if e["target"] == f"p{i}"]
        props = {POWERS_BY_ID[e["power"]].prop: e for e in mine}
        if p["frozen"]:
            self._ice(surf, p)
        if "no_kick" in props:
            self._no_kick(surf, snap(p["x"] - f * NO_KICK_BEHIND), int(p["y"] - NO_KICK_HEIGHT))
        if "speed" in props and abs(p["vx"]) > SPEED_LINES_MIN:
            col = CATEGORY_COLORS[POWERS_BY_ID[props["speed"]["power"]].category]
            d = -1 if p["vx"] > 0 else 1
            for k, hh in enumerate(SPEED_LINE_HEIGHTS):
                x0 = p["x"] + d * (SPEED_LINE_BEHIND + k * SPEED_LINE_STAGGER) * s
                ln = snap(SPEED_LINE_LEN + SPEED_LINE_WOBBLE * math.sin(self.t * SPEED_LINE_HZ + k))
                pygame.draw.rect(surf, col, (min(x0, x0 + d * ln), p["y"] - hh * s, ln, 2 * PX))
        if "jump" in props:
            col = CATEGORY_COLORS[POWERS_BY_ID[props["jump"]["power"]].category]
            r = pygame.Rect(0, 0, int(SPRING_W * s), SPRING_H)
            r.center = (p["x"], FLOOR + SPRING_DROP)
            pygame.draw.ellipse(surf, col, r, SPRING_LINE)
        if KICK_ARC_FROM <= p["kick"] <= KICK_ARC_TO:
            self._kick_arc(surf, p, f)
        top = p["y"] - (PlayerSpec.HEAD_OFFSET_Y + PlayerSpec.HEAD_RADIUS) * s - INDICATOR_GAP
        self._indicator(surf, p["x"], top, i, st.get("last_touch") == i)
        for k, e in enumerate(mine):
            cx = p["x"] + (k - (len(mine) - 1) / 2) * MINI_EFFECT_STEP
            self._mini_effect(surf, e, (cx, top - MINI_EFFECT_RAISE))

    def _no_kick(self, surf, bx, by):
        """Cartel "sin patada": cuadrado blanco con borde y cruz roja, centrado en (bx, by)."""
        half = NO_KICK_SIZE // 2
        inner = half - NO_KICK_BORDER
        length, thick = NO_KICK_CROSS
        pygame.draw.rect(surf, C.INK, (bx - half, by - half, NO_KICK_SIZE, NO_KICK_SIZE))
        pygame.draw.rect(surf, C.WHITE, (bx - inner, by - inner, 2 * inner, 2 * inner))
        pygame.draw.rect(surf, C.RED, (bx - length // 2, by - thick // 2, length, thick))
        pygame.draw.rect(surf, C.RED, (bx - thick // 2, by - length // 2, thick, length))

    def _indicator(self, surf, x, y, i, last):
        col = PLAYER_COLORS[i]
        x = snap(x)
        pygame.draw.polygon(surf, C.INK, [(x + dx, y + dy) for dx, dy in ARROW_OUTER])
        pygame.draw.polygon(surf, col, [(x + dx, y + dy) for dx, dy in ARROW_INNER])
        if last:                                   # último toque: pelotita junto a la flecha
            ball = self.ball_sprite.frame(LAST_TOUCH_BALL_R, 0)
            dx, dy = LAST_TOUCH_BALL_AT
            surf.blit(ball, ball.get_rect(midleft=(x + dx, y + dy)))

    def _mini_effect(self, surf, e, center):
        icon = power_icon(e["power"], MINI_ICON)
        r = icon.get_rect(center=(round(center[0]), round(center[1])))
        surf.blit(icon, r)
        col = CATEGORY_COLORS[POWERS_BY_ID[e["power"]].category]
        timer_bar(surf, r.left, r.bottom + MINI_TIMER_GAP, r.width, e["left"] / max(MIN_DURATION, e["dur"]), col)

    def _ice(self, surf, p):
        s = p["scale"]
        r = pygame.Rect(0, 0, snap(ICE_W * s), snap((PlayerSpec.HEIGHT + ICE_EXTRA_H) * s))
        r.midbottom = (p["x"], p["y"] + ICE_SINK)
        ice = pygame.Surface(r.size, pygame.SRCALPHA)
        ice.fill(ICE_FILL)
        pygame.draw.rect(ice, ICE_EDGE, ice.get_rect(), ICE_EDGE_LINE)
        for k in range(ICE_STREAKS):
            x = snap(r.width * (ICE_STREAK_FIRST + ICE_STREAK_STEP * k))
            for j in range(ICE_STREAK_STEPS):
                ice.fill(ICE_STREAK_COLOR, (x - j * PX, ICE_STREAK_TOP + j * 2 * PX, PX, 2 * PX))
        surf.blit(ice, r)

    def _kick_arc(self, surf, p, f):
        """Alcance visible de la patada: arco de píxeles blancos."""
        s = p["scale"]
        cx, cy = p["x"], p["y"] - KICK_ARC_HEIGHT * s
        R = (PlayerSpec.KICK_REACH_X + PlayerSpec.KICK_RADIUS * KICK_ARC_REACH_SHARE) * s
        prog = min(1.0, (p["kick"] - KICK_ARC_FROM) / KICK_ARC_GROW)
        for k in range(KICK_ARC_DOTS):
            a = math.radians(KICK_ARC_START + KICK_ARC_SPAN * prog * k / (KICK_ARC_DOTS - 1))
            x = cx + math.sin(a) * R * f
            y = cy + math.cos(a) * R
            sz = PX + (k * 2) // KICK_ARC_GROWTH * PX
            surf.fill(C.WHITE, (snap(x) - sz // 2, snap(y) - sz // 2, sz, sz))

    def _ball(self, surf, ball, st):
        sp = math.hypot(ball["vx"], ball["vy"])
        self.trail.append((ball["x"], ball["y"], ball["r"]))
        if sp > TRAIL_SPEED:
            pts = list(self.trail)[:-1]
            for k, (x, y, r) in enumerate(pts):
                sz = max(PX, snap(r * (TRAIL_MIN_SHARE + TRAIL_EXTRA_SHARE * k / max(1, len(pts)))))
                layer = pygame.Surface((sz, sz), pygame.SRCALPHA)
                layer.fill((*C.WHITE, TRAIL_ALPHA + TRAIL_ALPHA_STEP * k))
                surf.blit(layer, (int(x - sz / 2), int(y - sz / 2)))
        for e in st.get("effects", []):
            if e["target"] == "ball":
                col = CATEGORY_COLORS[POWERS_BY_ID[e["power"]].category]
                pygame.draw.circle(surf, col, (int(ball["x"]), int(ball["y"])), int(ball["r"] + BALL_RING_GAP),
                                   EFFECT_RING_LINE)
        self.ball_sprite.draw(surf, ball["x"], ball["y"], ball["r"], ball["angle"])

    def _pickup(self, surf, pk):
        pdef = POWERS_BY_ID[pk["power"]]
        col = CATEGORY_COLORS[pdef.category]
        bob = PX * round(math.sin(self.t * PICKUP_BOB_HZ))
        x, y = int(pk["x"]), int(pk["y"] + bob)
        r = PowerRules.PICKUP_RADIUS
        blink = pk["ttl"] < PICKUP_BLINK_TIME and int(self.t * PICKUP_BLINK_HZ) % 2 == 0
        if not blink:
            pygame.draw.circle(surf, col, (x, y), r + PICKUP_RING_GAP, EFFECT_RING_LINE)
            icon = power_icon(pk["power"], r * 2)
            surf.blit(icon, icon.get_rect(center=(x, y)))
        timer_bar(surf, x - r, y + r + PICKUP_RING_GAP, 2 * r, pk["ttl"] / pk["ttl_max"], col)
        lab = pixelfont.render(pdef.label, LABEL_SCALE, C.WHITE, outline=C.INK)
        surf.blit(lab, lab.get_rect(midtop=(x, y + r + PICKUP_LABEL_GAP)))

    def _bomb(self, surf, b):
        x, y = int(b["x"]), int(b["y"])
        frac = b["fuse"] / b["fuse_max"]
        R = PowerRules.BOMB_BLAST_RADIUS
        on = int(self.t * (BOMB_BLINK_HZ + BOMB_BLINK_EXTRA * (1 - frac))) % 2 == 0
        n = BLAST_DOTS
        for k in range(n):
            if (k + int(self.t * BLAST_DOTS_HZ)) % 2:
                a = 2 * math.pi * k / n
                surf.fill(C.RED, (snap(x + math.cos(a) * R), snap(y + math.sin(a) * R), BLAST_DOT, BLAST_DOT))
        pygame.draw.circle(surf, C.INK, (x, y), BOMB_R)
        pygame.draw.circle(surf, C.RED if on else C.INK, (x, y), BOMB_CORE_R)
        surf.fill(C.WHITE, _around(x, y, BOMB_SHINE))
        pygame.draw.rect(surf, C.INK, _around(x, y, BOMB_FUSE))
        surf.fill(BOMB_SPARK_ON if on else C.ORANGE, _around(x, y, BOMB_SPARK))
        lab = pixelfont.render(f"{b['fuse']:.1f}", LABEL_SCALE, C.WHITE, outline=C.INK)
        surf.blit(lab, lab.get_rect(midbottom=(x, y - BOMB_LABEL_GAP)))

    # ------------------------------------------------------------------ HUD
    def draw_hud(self, surf, st):
        board = pygame.Rect((0, 0), BOARD)
        board.midtop = (CENTER_X, BOARD_TOP)
        pygame.draw.rect(surf, C.INK, board.move(SHADOW_OFFSET, SHADOW_OFFSET))
        pygame.draw.rect(surf, C.STRUCT_DARK, board)
        pygame.draw.rect(surf, C.INK, board, FRAME_LINE)
        led_area = board.inflate(-2 * BOARD_INSET, -2 * BOARD_INSET)
        pygame.draw.rect(surf, C.LED_BG, led_area)
        for i in (0, 1):
            ch = CHARACTERS_BY_ID[self.chars[i]]
            head = self.sprites.mini_head(ch["id"], 1, 1 if i == 0 else -1)
            plate = pygame.Rect((0, 0), PLATE)
            if i == 0:
                plate.midleft = (led_area.left + PLATE_INSET, led_area.centery)
            else:
                plate.midright = (led_area.right - PLATE_INSET, led_area.centery)
            pygame.draw.rect(surf, PLAYER_COLORS[i], plate)
            pygame.draw.rect(surf, C.INK, plate, PLATE_LINE)
            surf.blit(head, head.get_rect(center=plate.center))
            score = pixelfont.render_led(str(st["score"][i]), SCORE_LED_SCALE, C.LED_ON, C.LED_OFF)
            sx = led_area.centerx - SCORE_X if i == 0 else led_area.centerx + SCORE_X
            surf.blit(score, score.get_rect(center=(sx, led_area.centery - SCORE_RAISE)))
        low = (st["clock"] <= CLOCK_WARNING and st["phase"] == P.PHASE_PLAYING
               and int(self.t * CLOCK_BLINK_HZ) % 2 == 0)
        golden = st.get("golden")
        clock = pixelfont.render_led("ORO" if golden else fmt_clock(st["clock"]), CLOCK_LED_SCALE,
                                     C.LED_ON_2 if (low or golden) else C.LED_ON, C.LED_OFF)
        surf.blit(clock, clock.get_rect(center=(led_area.centerx, led_area.centery - CLOCK_RAISE)))
        state_txt = {P.PHASE_COUNTDOWN: "PREPARADOS", P.PHASE_PLAYING: "EN JUEGO",
                     P.PHASE_GOAL: "GOL", P.PHASE_FINISHED: "FINAL"}[st["phase"]]
        if st.get("golden") and st["phase"] in (P.PHASE_PLAYING, P.PHASE_COUNTDOWN):
            state_txt = "GOL DE ORO"
        if st["paused"]:
            state_txt = "EN PAUSA"
        lab = scale_px(pixelfont.render(state_txt, 1, STATE_TEXT_COLOR))
        surf.blit(lab, lab.get_rect(center=(led_area.centerx, led_area.bottom - STATE_TEXT_BOTTOM)))
        for i in (0, 1):                          # carteles con los nombres
            ch = CHARACTERS_BY_ID[self.chars[i]]
            name = pixelfont.render(short_name(ch).upper(), LABEL_SCALE, C.WHITE, outline=C.INK)
            r = name.get_rect()
            if i == 0:
                r.topright = (board.left - NAME_GAP, board.top + NAME_TOP)
            else:
                r.topleft = (board.right + NAME_GAP, board.top + NAME_TOP)
            bevel_box(surf, r.inflate(*NAME_PAD), PLAYER_COLORS[i])
            surf.blit(name, r)
        # efectos activos: J1 a la izquierda, J2 a la derecha, pelota en el centro
        cols = {0: [], 1: [], "c": []}
        for e in st.get("effects", []):
            t = e["target"]
            cols[0 if t in ("p0", "goal0") else 1 if t in ("p1", "goal1") else "c"].append(e)
        effect_w = HUD_EFFECT[0]
        for k, e in enumerate(cols[0]):
            y = board.top + HUD_EFFECTS_TOP + k * HUD_EFFECT_STEP
            self._hud_effect(surf, e, (board.left - NAME_GAP - effect_w, y))
        for k, e in enumerate(cols[1]):
            y = board.top + HUD_EFFECTS_TOP + k * HUD_EFFECT_STEP
            self._hud_effect(surf, e, (board.right + NAME_GAP, y))
        top = board.bottom + CENTER_EFFECTS_GAP
        if self.center_note:
            note = pygame.Rect(0, 0, pixelfont.text_width(self.center_note, LABEL_SCALE) + NOTE_PADDING, NOTE_H)
            note.midtop = (board.centerx, board.bottom + NOTE_GAP)
            inner = bevel_box(surf, note, C.CREAM, shadow=False)
            draw_text(surf, self.center_note, FONT_SMALL, inner.center, C.INK, outline=None)
            top = note.bottom + NOTE_BOTTOM_GAP
        for k, e in enumerate(cols["c"]):
            self._hud_effect(surf, e, (board.centerx - effect_w // 2, top + k * HUD_EFFECT_STEP))

    def _hud_effect(self, surf, e, topleft):
        pdef = POWERS_BY_ID[e["power"]]
        col = CATEGORY_COLORS[pdef.category]
        inner = bevel_box(surf, pygame.Rect(topleft, HUD_EFFECT), C.CREAM)
        surf.blit(power_icon(e["power"], HUD_ICON), (inner.left + HUD_ICON_INSET, inner.top + HUD_ICON_INSET))
        tgt = e["target"]
        label = ("PELOTA" if tgt == "ball" else "ARCO" if tgt.startswith("goal")
                 else self.who(int(tgt[1]), side_if_same=False).upper())
        draw_text(surf, label, FONT_SMALL, (inner.left + HUD_TEXT_X, inner.top + HUD_TEXT_Y),
                  C.INK, anchor="topleft", outline=None)
        draw_text(surf, f"{max(0.0, e['left']):.1f}s", FONT_SMALL,
                  (inner.right - HUD_TIME_MARGIN, inner.top + HUD_TEXT_Y), col, anchor="topright", outline=C.INK)
        timer_bar(surf, inner.left + HUD_TEXT_X, inner.bottom - HUD_TIMER_BOTTOM,
                  inner.width - HUD_TEXT_X - HUD_TIME_MARGIN, e["left"] / max(MIN_DURATION, e["dur"]), col)

    def draw_center_messages(self, surf, st):
        """Cuenta regresiva, ¡YA!, gol."""
        if st["phase"] == P.PHASE_COUNTDOWN and not st["paused"]:
            n = max(1, math.ceil(st["phase_left"]))
            frac = st["phase_left"] - math.floor(st["phase_left"])
            size = FONT_COUNTDOWN + int(COUNTDOWN_GROWTH * frac) // FONT_STEP * FONT_STEP
            draw_text(surf, str(n), size, (CENTER_X, COUNTDOWN_Y), C.GOLD, kind="title", outline=C.INK, shadow=True)
        if self.kickoff_flash > 0:
            draw_text(surf, "¡YA!", FONT_GO, (CENTER_X, COUNTDOWN_Y), C.WHITE, kind="title", outline=C.INK,
                      shadow=True)
        if self.golden_flash > 0:
            draw_text(surf, "¡GOL DE ORO!", FONT_BANNER, (CENTER_X, GOLDEN_Y), C.GOLD, kind="title", outline=C.INK,
                      shadow=True)
            draw_text(surf, "Empate: el próximo gol gana", FONT_TEXT, (CENTER_X, GOLDEN_NOTE_Y), C.INK,
                      outline=C.WHITE)
        if self.goal_banner:
            left, g = self.goal_banner
            col = PLAYER_COLORS[g["scorer"]]
            band = pygame.Rect(0, GOAL_BAND_TOP, SCREEN_W, GOAL_BAND_H)
            pygame.draw.rect(surf, C.INK, band)
            pygame.draw.rect(surf, C.CREAM, band.inflate(0, -2 * GOAL_BAND_BORDER))
            pygame.draw.rect(surf, col, (0, band.top + GOAL_BAND_BORDER, SCREEN_W, GOAL_STRIPE))
            pygame.draw.rect(surf, col, (0, band.bottom - GOAL_BAND_BORDER - GOAL_STRIPE, SCREEN_W, GOAL_STRIPE))
            wob = GOAL_WOBBLE_PX if int(self.t * GOAL_WOBBLE_HZ) % 2 else 0
            draw_text(surf, "¡GOOOL!", FONT_GOAL, (CENTER_X, GOAL_TEXT_Y - wob), col, kind="title", outline=C.INK,
                      shadow=True)
            sub = self.who(g["scorer"])
            if g.get("own_goal"):
                sub += "  (en contra)"
            draw_text(surf, sub, FONT_TEXT, (CENTER_X, GOAL_SCORER_Y), C.INK, outline=None)
