"""Íconos de poderes: insignia del color de su categoría + pictograma.

Verde = beneficia al receptor, rojo = lo perjudica, violeta = global.
Los poderes que actúan sobre el rival llevan además una pequeña mira.
Si existe assets/iconos/<id>.png se usa esa imagen.
"""
import math

import pygame

from ..config import CATEGORY_COLORS, POWERS_BY_ID
from . import art
from .art import circle, shade, thick_polyline
from .assets import load_override_image
from .retro import PX, pixelize, scale_px

WHITE = (255, 255, 255)
INK = (26, 24, 40)
_cache = {}


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

    def circle(self, color, x, y, rr):
        circle(self.s, color, self.p(x, y), rr * self.r)

    def ring(self, color, x, y, rr, w):
        pygame.draw.circle(self.s, color, [round(v) for v in self.p(x, y)], round(rr * self.r),
                           max(1, round(w * self.r)))


def _arrow(g, x, y, direction, size=0.5, color=WHITE):
    """Flecha gruesa; direction = (dx, dy) unitario."""
    dx, dy = direction
    px, py = -dy, dx
    tip = (x + dx * size, y + dy * size)
    base = (x - dx * size * 0.6, y - dy * size * 0.6)
    neck = (x + dx * size * 0.05, y + dy * size * 0.05)
    g.line(color, [base, neck], 0.2 * size / 0.5)
    g.poly(color, [tip, (neck[0] + px * size * 0.5, neck[1] + py * size * 0.5),
                   (neck[0] - px * size * 0.5, neck[1] - py * size * 0.5)])


def _ball(g, x, y, r):
    g.circle(WHITE, x, y, r)
    g.circle(INK, x, y, r * 0.38)
    for k in range(5):
        a = math.radians(-90 + k * 72)
        g.line(INK, [(x + math.cos(a) * r * 0.38, y + math.sin(a) * r * 0.38),
                     (x + math.cos(a) * r * 0.95, y + math.sin(a) * r * 0.95)], 0.07)


def _goal(g, x, y, w, h):
    g.line(WHITE, [(x - w, y + h), (x - w, y - h), (x + w, y - h), (x + w, y + h)], 0.16)
    for k in range(1, 4):
        xx = x - w + 2 * w * k / 4
        g.line((255, 255, 255, 150), [(xx, y - h), (xx, y + h)], 0.05)
    g.line((255, 255, 255, 150), [(x - w, y), (x + w, y)], 0.05)


def _person(g, x, y, s):
    g.circle(WHITE, x, y - 0.35 * s, 0.32 * s)
    g.poly(WHITE, [(x - 0.3 * s, y + 0.55 * s), (x - 0.24 * s, y + 0.02 * s),
                   (x + 0.24 * s, y + 0.02 * s), (x + 0.3 * s, y + 0.55 * s)])


def _boot(g):
    g.poly(WHITE, [(-0.55, -0.55), (-0.1, -0.55), (-0.08, 0.05), (0.55, 0.12), (0.65, 0.42),
                   (-0.6, 0.42)])
    g.line((230, 60, 60), [(-0.45, -0.35), (0.05, 0.2)], 0.14)
    g.line((230, 60, 60), [(0.05, -0.35), (-0.45, 0.2)], 0.14)
    g.line(INK, [(-0.6, 0.5), (0.66, 0.5)], 0.08)


def _snowflake(g):
    for k in range(3):
        a = math.radians(90 + k * 60)
        dx, dy = math.cos(a) * 0.72, math.sin(a) * 0.72
        g.line(WHITE, [(-dx, -dy), (dx, dy)], 0.13)
        for sgn in (1, -1):
            ex, ey = dx * sgn, dy * sgn
            mx, my = ex * 0.6, ey * 0.6
            for t in (1, -1):
                b = a + t * math.radians(45)
                g.line(WHITE, [(mx, my), (mx + math.cos(b) * 0.25 * sgn, my + math.sin(b) * 0.25 * sgn)],
                       0.09)
    g.circle(WHITE, 0, 0, 0.14)


def _bolt(g):
    g.poly(WHITE, [(0.12, -0.78), (-0.42, 0.08), (-0.04, 0.08), (-0.2, 0.78), (0.44, -0.16),
                   (0.04, -0.16), (0.24, -0.78)])


def _snail(g):
    g.poly(WHITE, [(-0.7, 0.45), (0.6, 0.45), (0.72, 0.3), (0.55, 0.2), (-0.6, 0.25)])
    g.circle(WHITE, 0.62, 0.12, 0.13)
    g.line(WHITE, [(0.6, 0.05), (0.66, -0.3)], 0.06)
    g.line(WHITE, [(0.7, 0.08), (0.84, -0.22)], 0.06)
    g.circle(WHITE, -0.1, -0.08, 0.46)
    pts = []
    for i in range(40):
        t = i / 39
        a = t * 4.2 * math.pi
        rr = 0.38 * (1 - t * 0.85)
        pts.append((-0.1 + math.cos(a) * rr, -0.08 + math.sin(a) * rr))
    g.line(shade(INK, 0.2), pts, 0.06)


def _spring(g, y0, y1, x=0.0, w=0.3):
    pts = []
    n = 6
    for i in range(n + 1):
        yy = y0 + (y1 - y0) * i / n
        pts.append((x + (w if i % 2 else -w), yy))
    g.line(WHITE, pts, 0.1)


def _bomb(g):
    g.circle(WHITE, -0.08, 0.14, 0.56)
    g.circle(INK, -0.08, 0.14, 0.46)
    g.circle((255, 255, 255, 140), -0.26, -0.04, 0.12)
    g.poly(WHITE, [(0.18, -0.4), (0.38, -0.2), (0.28, -0.1), (0.08, -0.3)])
    g.line(WHITE, art.bezier((0.3, -0.3), (0.45, -0.62), (0.62, -0.55), 10), 0.08)
    for k in range(6):
        a = math.radians(k * 60 + 15)
        g.line((255, 220, 90), [(0.66 + math.cos(a) * 0.06, -0.6 + math.sin(a) * 0.06),
                                (0.66 + math.cos(a) * 0.2, -0.6 + math.sin(a) * 0.2)], 0.06)


def _bounces(g, tall):
    h = 0.75 if tall else 0.22
    for x0, x1, k in ((-0.85, -0.25, 1.0), (-0.25, 0.25, 0.8 if tall else 0.6), (0.25, 0.65, 0.6 if tall else 0.3)):
        g.line((255, 255, 255, 200), art.bezier((x0, 0.5), ((x0 + x1) / 2, 0.5 - h * k * 2), (x1, 0.5), 12), 0.07)
    g.line(WHITE, [(-0.9, 0.62), (0.9, 0.62)], 0.08)
    _ball(g, 0.65, 0.5 - 0.22, 0.2)


GLYPHS = {
    "speed_up": lambda g: (_bolt(g), g.line(WHITE, [(-0.75, -0.3), (-0.5, -0.3)], 0.08),
                           g.line(WHITE, [(-0.8, 0.1), (-0.52, 0.1)], 0.08)),
    "speed_down": _snail,
    "jump_up": lambda g: (_arrow(g, 0, -0.25, (0, -1), 0.5), _spring(g, 0.2, 0.7)),
    "jump_down": lambda g: (_arrow(g, 0, -0.05, (0, 1), 0.5),
                            g.line(WHITE, [(-0.6, 0.62), (0.6, 0.62)], 0.14)),
    "freeze_rival": _snowflake,
    "freeze_self": _snowflake,
    "big_goal": lambda g: (_goal(g, -0.12, 0.2, 0.5, 0.42), _arrow(g, 0.55, -0.35, (0, -1), 0.35)),
    "small_goal": lambda g: (_goal(g, -0.12, 0.32, 0.36, 0.28), _arrow(g, 0.55, -0.2, (0, 1), 0.35)),
    "grow": lambda g: (_person(g, 0, 0.08, 0.95),
                       [_arrow(g, sx * 0.6, sy * 0.6, (sx * 0.707, sy * 0.707), 0.22)
                        for sx, sy in ((-1, -1), (1, -1))]),
    "shrink": lambda g: (_person(g, 0, 0.2, 0.6),
                         [_arrow(g, sx * 0.6, sy * 0.55, (-sx * 0.707, -sy * 0.707), 0.22)
                          for sx, sy in ((-1, -1), (1, -1))]),
    "injured_self": _boot,
    "injured_rival": _boot,
    "bombs": _bomb,
    "low_bounce": lambda g: _bounces(g, False),
    "high_bounce": lambda g: _bounces(g, True),
    "big_ball": lambda g: (_ball(g, -0.12, 0.1, 0.58), g.line(WHITE, [(0.5, -0.62), (0.5, -0.18)], 0.13),
                           g.line(WHITE, [(0.28, -0.4), (0.72, -0.4)], 0.13)),
    "small_ball": lambda g: (_ball(g, -0.1, 0.2, 0.34), g.line(WHITE, [(0.3, -0.4), (0.72, -0.4)], 0.13)),
}


def _vector_icon(power_id, S):
    pdef = POWERS_BY_ID[power_id]
    col = CATEGORY_COLORS[pdef.category]
    surf = art.canvas(S, S)
    c = S / 2
    r = S * 0.46
    circle(surf, INK, (c, c), r)
    circle(surf, WHITE, (c, c), r * 0.86)
    circle(surf, col, (c, c), r * 0.74)
    glyph = art.canvas(S, S)
    GLYPHS[power_id](Glyph(glyph, c, c, r * 0.54))
    surf.blit(glyph, (0, 0))
    if pdef.target in ("rival", "rival_goal"):
        mx, my = c + r * 0.62, c + r * 0.62
        circle(surf, INK, (mx, my), r * 0.32)
        circle(surf, WHITE, (mx, my), r * 0.24)
        g = Glyph(surf, mx, my, r * 0.2)
        g.ring((200, 40, 40), 0, 0, 0.62, 0.22)
        g.line((200, 40, 40), [(-1, 0), (1, 0)], 0.16)
        g.line((200, 40, 40), [(0, -1), (0, 1)], 0.16)
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
        native = max(8, size // PX)
        icon = scale_px(pixelize(_vector_icon(power_id, 128), native), PX)
    _cache[key] = icon
    return icon
