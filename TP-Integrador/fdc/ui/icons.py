"""Íconos de poderes: insignia del color de su categoría + pictograma.

Verde = beneficia al receptor, rojo = lo perjudica, violeta = global.
Los poderes que actúan sobre el rival llevan además una pequeña mira.
Si existe assets/iconos/<id>.png se usa esa imagen.

Los pictogramas se dibujan en "unidades del ícono": el centro es (0, 0) y
1 es el radio del pictograma (y crece hacia abajo). Así cada forma de abajo
es una lista de puntos que no depende del tamaño final del ícono. Los
grosores de trazo también van en esas unidades.
"""
import math

import pygame

from ..config import CATEGORY_COLORS, POWERS_BY_ID
from . import art
from .art import circle, shade, thick_polyline
from .assets import load_override_image
from .retro import PX, pixelize, scale_px

WHITE = (255, 255, 255)            # pictogramas
INK = (26, 24, 40)                 # contorno de la insignia (más oscuro que palette.INK: se ve chico)
SOFT_WHITE = (255, 255, 255, 150)  # trazos secundarios (red del arco)
_cache = {}

# --- insignia
VECTOR_SIZE = 128                  # px: el ícono se dibuja grande y después se pasa a pixel art
MIN_ICON_PX = 8                    # px nativos: tamaño mínimo del ícono pixelado
BADGE_R = 0.46                     # radio de la insignia (fracción del lado del ícono)
BADGE_RIM = 0.86                   # aro blanco (fracción del radio de la insignia)
BADGE_FACE = 0.74                  # círculo del color de la categoría (ídem)
GLYPH_SCALE = 0.54                 # radio del pictograma (ídem)
# mira de los poderes que afectan al rival (abajo a la derecha)
TARGET_AT = 0.62                   # corrimiento desde el centro (fracción del radio de la insignia)
TARGET_OUTER = 0.32                # círculo oscuro
TARGET_INNER = 0.24                # círculo blanco
TARGET_SCALE = 0.2                 # radio de la mira
TARGET_RED = (200, 40, 40)         # color de la mira
TARGET_RING_R = 0.62               # aro de la mira (unidades de la mira)
TARGET_RING_W = 0.22               # grosor del aro
TARGET_CROSS_W = 0.16              # grosor de la cruz

# --- flecha gruesa
ARROW_SIZE = 0.5                   # tamaño por defecto (del centro a la punta)
ARROW_TAIL = 0.6                   # la cola llega a 0,6 tamaños detrás del centro
ARROW_NECK = 0.05                  # donde termina el palo y empieza la punta
ARROW_HEAD_W = 0.5                 # media base de la punta (en tamaños)
ARROW_SHAFT_W = 0.2                # grosor del palo para una flecha de tamaño ARROW_SIZE
# --- pelota
PENTAGON_SIDES = 5                 # parche central de la pelota: pentágono...
PENTAGON_STEP = 72                 # ...con un vértice cada 72 grados...
UP_ANGLE = -90                     # ...empezando hacia arriba
BALL_PATCH = 0.38                  # radio del parche (fracción del radio de la pelota)
BALL_SEAM_END = 0.95               # las costuras van del parche hasta acá
BALL_SEAM_W = 0.07                 # grosor de las costuras
# --- arco
GOAL_FRAME_W = 0.16                # grosor de palos y travesaño
GOAL_NET_COLUMNS = 4               # la red tiene 4 columnas
GOAL_NET_W = 0.05                  # grosor de los hilos
# --- persona (agrandar y achicar): todo multiplicado por su tamaño
PERSON_HEAD_Y = -0.35              # cabeza: altura del centro...
PERSON_HEAD_R = 0.32               # ...y radio
PERSON_BODY = ((-0.3, 0.55), (-0.24, 0.02), (0.24, 0.02), (0.3, 0.55))   # cuerpo (trapecio)
# --- botín lesionado
BOOT = ((-0.55, -0.55), (-0.1, -0.55), (-0.08, 0.05), (0.55, 0.12), (0.65, 0.42), (-0.6, 0.42))   # silueta
BOOT_CROSS = (((-0.45, -0.35), (0.05, 0.2)), ((0.05, -0.35), (-0.45, 0.2)))   # cruz roja encima
BOOT_CROSS_COLOR = (230, 60, 60)   # rojo de la cruz
BOOT_CROSS_W = 0.14                # grosor de la cruz
BOOT_SOLE = ((-0.6, 0.5), (0.66, 0.5))   # suela
BOOT_SOLE_W = 0.08                 # grosor de la suela
# --- copo de nieve (congelar)
SNOW_ARMS = 3                      # tres barras cruzadas = seis brazos
SNOW_FIRST = 90                    # grados de la primera barra (vertical)
SNOW_ARM_STEP = 60                 # grados entre barras
SNOW_ARM = 0.72                    # largo de cada brazo
SNOW_ARM_W = 0.13                  # grosor de los brazos
SNOW_BRANCH_AT = 0.6               # las ramitas salen a 60 % del brazo...
SNOW_BRANCH_ANGLE = 45             # ...a 45 grados...
SNOW_BRANCH = 0.25                 # ...con este largo...
SNOW_BRANCH_W = 0.09               # ...y este grosor
SNOW_CORE = 0.14                   # círculo del centro
# --- rayo (más velocidad) y líneas de movimiento
BOLT = ((0.12, -0.78), (-0.42, 0.08), (-0.04, 0.08), (-0.2, 0.78), (0.44, -0.16), (0.04, -0.16),
        (0.24, -0.78))             # silueta del rayo
SPEED_LINES = (((-0.75, -0.3), (-0.5, -0.3)), ((-0.8, 0.1), (-0.52, 0.1)))   # rayitas a la izquierda
SPEED_LINE_W = 0.08                # grosor de las rayitas
# --- caracol (menos velocidad)
SNAIL_BODY = ((-0.7, 0.45), (0.6, 0.45), (0.72, 0.3), (0.55, 0.2), (-0.6, 0.25))   # cuerpo
SNAIL_HEAD = (0.62, 0.12, 0.13)    # cabeza (x, y, radio)
SNAIL_ANTENNAS = (((0.6, 0.05), (0.66, -0.3)), ((0.7, 0.08), (0.84, -0.22)))   # antenas
SNAIL_ANTENNA_W = 0.06             # grosor de las antenas
SNAIL_SHELL = (-0.1, -0.08, 0.46)  # caparazón (x, y, radio)
SPIRAL_POINTS = 40                 # puntos de la espiral del caparazón
SPIRAL_ANGLE = 4.2                 # la espiral gira 4,2 π (algo más de dos vueltas)
SPIRAL_R = 0.38                    # radio de afuera de la espiral...
SPIRAL_SHRINK = 0.85               # ...que se cierra hasta el 15 %
SPIRAL_LIGHTEN = 0.2               # la espiral es un poco más clara que el contorno
SPIRAL_W = 0.06                    # grosor de la espiral
# --- resorte (súper salto)
SPRING_ZIGZAGS = 6                 # tramos del zigzag
SPRING_HALF_W = 0.3                # medio ancho
SPRING_W = 0.1                     # grosor
SPRING_TOP, SPRING_BOTTOM = 0.2, 0.7   # el resorte va de y = 0,2 a 0,7
# --- bomba
BOMB_BODY = (-0.08, 0.14, 0.56)    # bomba (x, y, radio)...
BOMB_CORE_R = 0.46                 # ...y su parte oscura
BOMB_SHINE = (-0.26, -0.04, 0.12)  # brillo (x, y, radio)
BOMB_SHINE_COLOR = (255, 255, 255, 140)   # brillo blanco translúcido
BOMB_CAP = ((0.18, -0.4), (0.38, -0.2), (0.28, -0.1), (0.08, -0.3))   # tapita de la mecha
BOMB_FUSE = ((0.3, -0.3), (0.45, -0.62), (0.62, -0.55))   # mecha: curva (inicio, control, fin)
BOMB_FUSE_STEPS = 10               # tramos de esa curva
BOMB_FUSE_W = 0.08                 # grosor de la mecha
SPARK_CENTER = (0.66, -0.6)        # chispa en la punta de la mecha
SPARK_RAYS = 6                     # rayitos de la chispa...
SPARK_RAY_STEP = 60                # ...uno cada 60 grados...
SPARK_RAY_TURN = 15                # ...girados 15 grados
SPARK_RAY = (0.06, 0.2)            # cada rayito va de esta distancia a esta
SPARK_RAY_W = 0.06                 # grosor de los rayitos
SPARK_COLOR = (255, 220, 90)       # amarillo
# --- piques (rebote alto y bajo)
BOUNCE_GROUND = 0.5                # altura del piso de los piques
BOUNCE_HEIGHT = {True: 0.75, False: 0.22}   # altura del primer pique (rebote alto / bajo)
# piques: (x de inicio, x de fin, altura relativa) para rebote alto y bajo
BOUNCE_ARCS = {True: ((-0.85, -0.25, 1.0), (-0.25, 0.25, 0.8), (0.25, 0.65, 0.6)),
               False: ((-0.85, -0.25, 1.0), (-0.25, 0.25, 0.6), (0.25, 0.65, 0.3))}
BOUNCE_STEPS = 12                  # tramos de cada curva
BOUNCE_TRAIL = (255, 255, 255, 200)  # color de la estela de los piques
BOUNCE_TRAIL_W = 0.07              # grosor de la estela
BOUNCE_FLOOR = ((-0.9, 0.62), (0.9, 0.62))   # piso
BOUNCE_FLOOR_W = 0.08              # grosor del piso
BOUNCE_BALL_X = 0.65               # pelotita al final de los piques...
BOUNCE_BALL_LIFT = 0.22            # ...apoyada sobre el piso...
BOUNCE_BALL_R = 0.2                # ...con este radio
# --- pictogramas armados con las piezas de arriba
JUMP_ARROW_UP = (0, -0.25)         # más salto: flecha hacia arriba sobre el resorte
JUMP_ARROW_DOWN = (0, -0.05)       # menos salto: flecha hacia abajo...
JUMP_FLOOR = ((-0.6, 0.62), (0.6, 0.62))   # ...contra el piso
JUMP_FLOOR_W = 0.14                # grosor de ese piso
BIG_GOAL = (-0.12, 0.2, 0.5, 0.42)  # arco grande (x, y, medio ancho, medio alto)
SMALL_GOAL = (-0.12, 0.32, 0.36, 0.28)   # arco chico
GOAL_ARROW_X = 0.55                # flecha al costado del arco...
BIG_GOAL_ARROW_Y = -0.35           # ...arriba (agrandar)...
SMALL_GOAL_ARROW_Y = -0.2          # ...o un poco más abajo (achicar)
GOAL_ARROW_SIZE = 0.35             # tamaño de esa flecha
GROW_PERSON = (0, 0.08, 0.95)      # persona grande (x, y, tamaño)
SHRINK_PERSON = (0, 0.2, 0.6)      # persona chica
SIZE_ARROWS = ((-1, -1), (1, -1))  # flechitas en diagonal arriba a la izquierda y a la derecha
SIZE_ARROW_AT = 0.6                # distancia de esas flechitas al centro
SHRINK_ARROW_Y = 0.55              # al achicar van un poco más abajo
DIAGONAL = 0.707                   # componente de una dirección diagonal (≈ 1/√2)
SIZE_ARROW_SIZE = 0.22             # tamaño de las flechitas
BIG_BALL = (-0.12, 0.1, 0.58)      # pelota grande (x, y, radio)
SMALL_BALL = (-0.1, 0.2, 0.34)     # pelota chica
PLUS_SIGN = (((0.5, -0.62), (0.5, -0.18)), ((0.28, -0.4), (0.72, -0.4)))   # "+" de la pelota grande
MINUS_SIGN = (((0.3, -0.4), (0.72, -0.4)),)   # "-" de la pelota chica
SIGN_W = 0.13                      # grosor del + y del -


class Glyph:
    def __init__(self, surf, cx, cy, r):
        self.s, self.cx, self.cy, self.r = surf, cx, cy, r

    def p(self, x, y):
        return self.cx + x * self.r, self.cy + y * self.r

    def pts(self, lst):
        return [self.p(x, y) for x, y in lst]

    def poly(self, color, lst):
        art.poly(self.s, color, self.pts(lst))

    def line(self, color, lst, w):
        thick_polyline(self.s, color, self.pts(lst), w * self.r)

    def lines(self, color, segments, w):
        for seg in segments:
            self.line(color, list(seg), w)

    def circle(self, color, x, y, rr):
        circle(self.s, color, self.p(x, y), rr * self.r)

    def ring(self, color, x, y, rr, w):
        pygame.draw.circle(self.s, color, [round(v) for v in self.p(x, y)], round(rr * self.r),
                           max(1, round(w * self.r)))


def _arrow(g, x, y, direction, size=ARROW_SIZE, color=WHITE):
    """Flecha gruesa; direction = (dx, dy) unitario."""
    dx, dy = direction
    px, py = -dy, dx
    tip = (x + dx * size, y + dy * size)
    base = (x - dx * size * ARROW_TAIL, y - dy * size * ARROW_TAIL)
    neck = (x + dx * size * ARROW_NECK, y + dy * size * ARROW_NECK)
    g.line(color, [base, neck], ARROW_SHAFT_W * size / ARROW_SIZE)
    g.poly(color, [tip, (neck[0] + px * size * ARROW_HEAD_W, neck[1] + py * size * ARROW_HEAD_W),
                   (neck[0] - px * size * ARROW_HEAD_W, neck[1] - py * size * ARROW_HEAD_W)])


def _ball(g, x, y, r):
    g.circle(WHITE, x, y, r)
    g.circle(INK, x, y, r * BALL_PATCH)
    for k in range(PENTAGON_SIDES):
        a = math.radians(UP_ANGLE + k * PENTAGON_STEP)
        g.line(INK, [(x + math.cos(a) * r * BALL_PATCH, y + math.sin(a) * r * BALL_PATCH),
                     (x + math.cos(a) * r * BALL_SEAM_END, y + math.sin(a) * r * BALL_SEAM_END)], BALL_SEAM_W)


def _goal(g, x, y, w, h):
    g.line(WHITE, [(x - w, y + h), (x - w, y - h), (x + w, y - h), (x + w, y + h)], GOAL_FRAME_W)
    for k in range(1, GOAL_NET_COLUMNS):
        xx = x - w + 2 * w * k / GOAL_NET_COLUMNS
        g.line(SOFT_WHITE, [(xx, y - h), (xx, y + h)], GOAL_NET_W)
    g.line(SOFT_WHITE, [(x - w, y), (x + w, y)], GOAL_NET_W)


def _person(g, x, y, s):
    g.circle(WHITE, x, y + PERSON_HEAD_Y * s, PERSON_HEAD_R * s)
    g.poly(WHITE, [(x + dx * s, y + dy * s) for dx, dy in PERSON_BODY])


def _boot(g):
    g.poly(WHITE, BOOT)
    g.lines(BOOT_CROSS_COLOR, BOOT_CROSS, BOOT_CROSS_W)
    g.line(INK, list(BOOT_SOLE), BOOT_SOLE_W)


def _snowflake(g):
    for k in range(SNOW_ARMS):
        a = math.radians(SNOW_FIRST + k * SNOW_ARM_STEP)
        dx, dy = math.cos(a) * SNOW_ARM, math.sin(a) * SNOW_ARM
        g.line(WHITE, [(-dx, -dy), (dx, dy)], SNOW_ARM_W)
        for sgn in (1, -1):
            ex, ey = dx * sgn, dy * sgn
            mx, my = ex * SNOW_BRANCH_AT, ey * SNOW_BRANCH_AT
            for t in (1, -1):
                b = a + t * math.radians(SNOW_BRANCH_ANGLE)
                g.line(WHITE, [(mx, my), (mx + math.cos(b) * SNOW_BRANCH * sgn, my + math.sin(b) * SNOW_BRANCH * sgn)],
                       SNOW_BRANCH_W)
    g.circle(WHITE, 0, 0, SNOW_CORE)


def _bolt(g):
    g.poly(WHITE, BOLT)


def _snail(g):
    g.poly(WHITE, SNAIL_BODY)
    g.circle(WHITE, *SNAIL_HEAD)
    g.lines(WHITE, SNAIL_ANTENNAS, SNAIL_ANTENNA_W)
    g.circle(WHITE, *SNAIL_SHELL)
    sx, sy, _ = SNAIL_SHELL
    pts = []
    for i in range(SPIRAL_POINTS):
        t = i / (SPIRAL_POINTS - 1)
        a = t * SPIRAL_ANGLE * math.pi
        rr = SPIRAL_R * (1 - t * SPIRAL_SHRINK)
        pts.append((sx + math.cos(a) * rr, sy + math.sin(a) * rr))
    g.line(shade(INK, SPIRAL_LIGHTEN), pts, SPIRAL_W)


def _spring(g, y0, y1, x=0.0, w=SPRING_HALF_W):
    pts = []
    n = SPRING_ZIGZAGS
    for i in range(n + 1):
        yy = y0 + (y1 - y0) * i / n
        pts.append((x + (w if i % 2 else -w), yy))
    g.line(WHITE, pts, SPRING_W)


def _bomb(g):
    x, y, r = BOMB_BODY
    g.circle(WHITE, x, y, r)
    g.circle(INK, x, y, BOMB_CORE_R)
    g.circle(BOMB_SHINE_COLOR, *BOMB_SHINE)
    g.poly(WHITE, BOMB_CAP)
    g.line(WHITE, art.bezier(*BOMB_FUSE, BOMB_FUSE_STEPS), BOMB_FUSE_W)
    cx, cy = SPARK_CENTER
    near, far = SPARK_RAY
    for k in range(SPARK_RAYS):
        a = math.radians(k * SPARK_RAY_STEP + SPARK_RAY_TURN)
        g.line(SPARK_COLOR, [(cx + math.cos(a) * near, cy + math.sin(a) * near),
                             (cx + math.cos(a) * far, cy + math.sin(a) * far)], SPARK_RAY_W)


def _bounces(g, tall):
    h = BOUNCE_HEIGHT[tall]
    ground = BOUNCE_GROUND
    for x0, x1, k in BOUNCE_ARCS[tall]:
        g.line(BOUNCE_TRAIL, art.bezier((x0, ground), ((x0 + x1) / 2, ground - h * k * 2), (x1, ground), BOUNCE_STEPS),
               BOUNCE_TRAIL_W)
    g.line(WHITE, list(BOUNCE_FLOOR), BOUNCE_FLOOR_W)
    _ball(g, BOUNCE_BALL_X, ground - BOUNCE_BALL_LIFT, BOUNCE_BALL_R)


def _speed_up(g):
    _bolt(g)
    g.lines(WHITE, SPEED_LINES, SPEED_LINE_W)


def _jump_up(g):
    _arrow(g, *JUMP_ARROW_UP, (0, -1), ARROW_SIZE)
    _spring(g, SPRING_TOP, SPRING_BOTTOM)


def _jump_down(g):
    _arrow(g, *JUMP_ARROW_DOWN, (0, 1), ARROW_SIZE)
    g.line(WHITE, list(JUMP_FLOOR), JUMP_FLOOR_W)


def _big_goal(g):
    _goal(g, *BIG_GOAL)
    _arrow(g, GOAL_ARROW_X, BIG_GOAL_ARROW_Y, (0, -1), GOAL_ARROW_SIZE)


def _small_goal(g):
    _goal(g, *SMALL_GOAL)
    _arrow(g, GOAL_ARROW_X, SMALL_GOAL_ARROW_Y, (0, 1), GOAL_ARROW_SIZE)


def _grow(g):
    _person(g, *GROW_PERSON)
    for sx, sy in SIZE_ARROWS:                    # flechitas hacia afuera
        _arrow(g, sx * SIZE_ARROW_AT, sy * SIZE_ARROW_AT, (sx * DIAGONAL, sy * DIAGONAL), SIZE_ARROW_SIZE)


def _shrink(g):
    _person(g, *SHRINK_PERSON)
    for sx, sy in SIZE_ARROWS:                    # flechitas hacia adentro
        _arrow(g, sx * SIZE_ARROW_AT, sy * SHRINK_ARROW_Y, (-sx * DIAGONAL, -sy * DIAGONAL), SIZE_ARROW_SIZE)


def _big_ball(g):
    _ball(g, *BIG_BALL)
    g.lines(WHITE, PLUS_SIGN, SIGN_W)


def _small_ball(g):
    _ball(g, *SMALL_BALL)
    g.lines(WHITE, MINUS_SIGN, SIGN_W)


GLYPHS = {                          # pictograma de cada poder
    "speed_up": _speed_up,
    "speed_down": _snail,
    "jump_up": _jump_up,
    "jump_down": _jump_down,
    "freeze_rival": _snowflake,
    "freeze_self": _snowflake,
    "big_goal": _big_goal,
    "small_goal": _small_goal,
    "grow": _grow,
    "shrink": _shrink,
    "injured_self": _boot,
    "injured_rival": _boot,
    "bombs": _bomb,
    "low_bounce": lambda g: _bounces(g, False),
    "high_bounce": lambda g: _bounces(g, True),
    "big_ball": _big_ball,
    "small_ball": _small_ball,
}


def _vector_icon(power_id, S):
    pdef = POWERS_BY_ID[power_id]
    col = CATEGORY_COLORS[pdef.category]
    surf = art.canvas(S, S)
    c = S / 2
    r = S * BADGE_R
    circle(surf, INK, (c, c), r)
    circle(surf, WHITE, (c, c), r * BADGE_RIM)
    circle(surf, col, (c, c), r * BADGE_FACE)
    glyph = art.canvas(S, S)
    GLYPHS[power_id](Glyph(glyph, c, c, r * GLYPH_SCALE))
    surf.blit(glyph, (0, 0))
    if pdef.target in ("rival", "rival_goal"):
        mx, my = c + r * TARGET_AT, c + r * TARGET_AT
        circle(surf, INK, (mx, my), r * TARGET_OUTER)
        circle(surf, WHITE, (mx, my), r * TARGET_INNER)
        g = Glyph(surf, mx, my, r * TARGET_SCALE)
        g.ring(TARGET_RED, 0, 0, TARGET_RING_R, TARGET_RING_W)
        g.line(TARGET_RED, [(-1, 0), (1, 0)], TARGET_CROSS_W)
        g.line(TARGET_RED, [(0, -1), (0, 1)], TARGET_CROSS_W)
    return surf


def power_icon(power_id, size):
    """Ícono pixel art: se ilustra en alta resolución y se reduce a píxeles
    nativos (size / PX) sin suavizado al agrandar."""
    key = (power_id, size)
    if key in _cache:
        return _cache[key]
    custom = load_override_image("iconos", f"{power_id}.png")
    if custom is not None:
        icon = pygame.transform.scale(custom, (size, size))
    else:
        native = max(MIN_ICON_PX, size // PX)
        icon = scale_px(pixelize(_vector_icon(power_id, VECTOR_SIZE), native), PX)
    _cache[key] = icon
    return icon
