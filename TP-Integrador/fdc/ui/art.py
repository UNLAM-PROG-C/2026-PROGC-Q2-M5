"""Herramientas de dibujo: mezclas de color, curvas y figuras con transparencia.

pygame.draw no mezcla la transparencia: si el color tiene alfa, la figura se
dibuja opaca en una capa chica y esa capa se funde sobre el destino.
"""
import math

import pygame

from . import palette as C

BEZIER_STEPS = 16           # tramos con los que se aproxima una curva de Bézier
BLEND_MARGIN = 2            # px de margen de la capa auxiliar alrededor de la figura
MIN_POLYGON_POINTS = 3      # un polígono necesita al menos tres puntos
MIN_POLYLINE_POINTS = 2     # un trazo necesita al menos dos puntos
GLOW_RING_STEP = 2          # px entre los anillos del brillo difuso
RGBA_CHANNELS = 4           # canales de un color con transparencia (rojo, verde, azul y alfa)
ALPHA = 3                   # posición del alfa dentro de un color RGBA


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(round(lerp(a, b, t))) for a, b in zip(c1[:C.RGB_CHANNELS], c2[:C.RGB_CHANNELS]))


def shade(color, k):
    """k > 0 aclara hacia blanco, k < 0 oscurece hacia negro."""
    if k >= 0:
        return mix(color, C.WHITE, k)
    return mix(color, C.SHADOW, -k)


def with_alpha(color, a):
    return (*color[:C.RGB_CHANNELS], a)


def canvas(w, h):
    return pygame.Surface((max(1, int(w)), max(1, int(h))), pygame.SRCALPHA)


def bezier(p0, p1, p2, steps=BEZIER_STEPS):
    """Curva de Bézier cuadrática (p1 es el punto de control)."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        out.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return out


# ---------------------------------------------------------------------------
# Primitivas
# ---------------------------------------------------------------------------
def _translucent(color):
    return len(color) == RGBA_CHANNELS and color[ALPHA] < C.OPAQUE


def _blend(surf, color, bbox, draw):
    """Dibuja opaco en una capa chica y la funde con el alfa del color."""
    left, top, right, bottom = bbox
    x0, y0 = int(math.floor(left)) - BLEND_MARGIN, int(math.floor(top)) - BLEND_MARGIN
    x1, y1 = int(math.ceil(right)) + BLEND_MARGIN, int(math.ceil(bottom)) + BLEND_MARGIN
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    layer = pygame.Surface((w, h), pygame.SRCALPHA)
    draw(layer, with_alpha(color, C.OPAQUE), (-x0, -y0))
    layer.fill((*C.WHITE, color[ALPHA]), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(layer, (x0, y0))


def _bbox(pts, pad=0.0):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _shift(pts, off):
    return [(x + off[0], y + off[1]) for x, y in pts]


def poly(surf, color, pts):
    if len(pts) < MIN_POLYGON_POINTS:
        return
    if _translucent(color):
        _blend(surf, color, _bbox(pts), lambda l, c, o: pygame.draw.polygon(l, c, _shift(pts, o)))
    else:
        pygame.draw.polygon(surf, color, pts)


def circle(surf, color, c, r):
    if r <= 0:
        return
    if _translucent(color):
        _blend(surf, color, (c[0] - r, c[1] - r, c[0] + r, c[1] + r),
               lambda l, cc, o: pygame.draw.circle(l, cc, (round(c[0] + o[0]), round(c[1] + o[1])),
                                                   max(1, round(r))))
    else:
        pygame.draw.circle(surf, color, (round(c[0]), round(c[1])), max(1, round(r)))


def _thick_polyline_opaque(surf, color, pts, width):
    r = width / 2
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1
        nx, ny = -dy / d * r, dx / d * r
        pygame.draw.polygon(surf, color, [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny),
                                          (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)])
    for p in pts:
        pygame.draw.circle(surf, color, (round(p[0]), round(p[1])), max(1, round(r)))


def thick_polyline(surf, color, pts, width):
    """Trazo grueso con extremos y uniones redondeadas."""
    if len(pts) < MIN_POLYLINE_POINTS:
        return
    if _translucent(color):
        _blend(surf, color, _bbox(pts, width), lambda l, c, o: _thick_polyline_opaque(l, c, _shift(pts, o), width))
    else:
        _thick_polyline_opaque(surf, color, pts, width)


# ---------------------------------------------------------------------------
# Capas
# ---------------------------------------------------------------------------
def clip(layer, mask_surf):
    """Recorta 'layer' a la forma de mask_surf (multiplica alfa)."""
    layer.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return layer


def radial_glow(radius, color, strength=1.0):
    """Círculo difuso (para luces y brillos)."""
    size = radius * 2
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    for i in range(radius, 0, -GLOW_RING_STEP):
        a = int(C.MAX_CHANNEL * strength * (1 - i / radius) ** 2)
        pygame.draw.circle(s, with_alpha(color, min(C.MAX_CHANNEL, a)), (radius, radius), i)
    return s
