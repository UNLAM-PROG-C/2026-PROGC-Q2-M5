"""Herramientas de ilustración procedural.

Todo se dibuja en una superficie SUPERMUESTREADA (SS veces más grande) y luego
se reduce con smoothscale: así las curvas, contornos y detalles quedan suaves
(anti-aliasing) aunque pygame.draw no lo tenga para polígonos rellenos.
"""
import math

import pygame

SS = 4  # factor de supermuestreo


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(round(lerp(a, b, t))) for a, b in zip(c1[:3], c2[:3]))


def shade(color, k):
    """k > 0 aclara hacia blanco, k < 0 oscurece hacia negro."""
    if k >= 0:
        return mix(color, (255, 255, 255), k)
    return mix(color, (0, 0, 0), -k)


def with_alpha(color, a):
    return (color[0], color[1], color[2], a)


def canvas(w, h):
    return pygame.Surface((max(1, int(w)), max(1, int(h))), pygame.SRCALPHA)


def downscale(surf, factor=SS):
    w, h = surf.get_size()
    return pygame.transform.smoothscale(surf, (max(1, round(w / factor)), max(1, round(h / factor))))


# ---------------------------------------------------------------------------
# Curvas
# ---------------------------------------------------------------------------
def catmull_rom(points, closed=True, steps=10):
    """Curva suave que pasa por todos los puntos de control."""
    pts = list(points)
    n = len(pts)
    out = []
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if closed else pts[max(i - 1, 0)]
        p1 = pts[i]
        p2 = pts[(i + 1) % n] if closed else pts[i + 1]
        p3 = pts[(i + 2) % n] if closed else pts[min(i + 2, n - 1)]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    if not closed:
        out.append(pts[-1])
    return out


def bezier(p0, p1, p2, steps=16):
    out = []
    for i in range(steps + 1):
        t = i / steps
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        out.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return out


def transform(points, cx, cy, sx, sy=None):
    sy = sx if sy is None else sy
    return [(cx + x * sx, cy + y * sy) for x, y in points]


def arc_points(cx, cy, rx, ry, a0, a1, steps=24):
    return [(cx + math.cos(math.radians(a0 + (a1 - a0) * i / steps)) * rx,
             cy + math.sin(math.radians(a0 + (a1 - a0) * i / steps)) * ry)
            for i in range(steps + 1)]


# ---------------------------------------------------------------------------
# Primitivas
# ---------------------------------------------------------------------------
def _translucent(color):
    return len(color) == 4 and color[3] < 255


def _blend(surf, color, bbox, draw):
    """pygame.draw no mezcla alfa: se dibuja opaco en una capa chica y se funde."""
    x0, y0, x1, y1 = (int(math.floor(bbox[0])) - 2, int(math.floor(bbox[1])) - 2,
                      int(math.ceil(bbox[2])) + 2, int(math.ceil(bbox[3])) + 2)
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    layer = pygame.Surface((w, h), pygame.SRCALPHA)
    draw(layer, (color[0], color[1], color[2], 255), (-x0, -y0))
    layer.fill((255, 255, 255, color[3]), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(layer, (x0, y0))


def _bbox(pts, pad=0.0):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _shift(pts, off):
    return [(x + off[0], y + off[1]) for x, y in pts]


def poly(surf, color, pts):
    if len(pts) < 3:
        return
    if _translucent(color):
        _blend(surf, color, _bbox(pts), lambda l, c, o: pygame.draw.polygon(l, c, _shift(pts, o)))
    else:
        pygame.draw.polygon(surf, color, pts)


def smooth_shape(surf, color, ctrl, steps=10):
    poly(surf, color, catmull_rom(ctrl, True, steps))


def circle(surf, color, c, r):
    if r <= 0:
        return
    if _translucent(color):
        _blend(surf, color, (c[0] - r, c[1] - r, c[0] + r, c[1] + r),
               lambda l, cc, o: pygame.draw.circle(l, cc, (round(c[0] + o[0]), round(c[1] + o[1])),
                                                   max(1, round(r))))
    else:
        pygame.draw.circle(surf, color, (round(c[0]), round(c[1])), max(1, round(r)))


def ellipse(surf, color, cx, cy, rx, ry, width=0):
    def draw(target, col, off):
        rect = pygame.Rect(0, 0, max(1, round(rx * 2)), max(1, round(ry * 2)))
        rect.center = (round(cx + off[0]), round(cy + off[1]))
        pygame.draw.ellipse(target, col, rect, width)
    if _translucent(color):
        _blend(surf, color, (cx - rx, cy - ry, cx + rx, cy + ry), draw)
    else:
        draw(surf, color, (0, 0))


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
    if len(pts) < 2:
        return
    if _translucent(color):
        _blend(surf, color, _bbox(pts, width), lambda l, c, o: _thick_polyline_opaque(l, c, _shift(pts, o), width))
    else:
        _thick_polyline_opaque(surf, color, pts, width)


def capsule(surf, color, a, b, r):
    thick_polyline(surf, color, [a, b], r * 2)


def rounded_rect(surf, color, rect, radius, width=0):
    pygame.draw.rect(surf, color, rect, width, border_radius=int(radius))


# ---------------------------------------------------------------------------
# Capas, recortes y contornos
# ---------------------------------------------------------------------------
def alpha_mask_surface(surf):
    """Superficie blanca con el alfa de 'surf' (sirve para recortar capas)."""
    m = pygame.mask.from_surface(surf, 8)
    return m.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(255, 255, 255, 0))


def clip(layer, mask_surf):
    """Recorta 'layer' a la forma de mask_surf (multiplica alfa)."""
    layer.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return layer


def outlined(surf, color, thickness, steps=16):
    """Devuelve una copia con contorno exterior de 'thickness' píxeles."""
    t = int(math.ceil(thickness))
    w, h = surf.get_size()
    out = pygame.Surface((w + 2 * t, h + 2 * t), pygame.SRCALPHA)
    m = pygame.mask.from_surface(surf, 20)
    sil = m.to_surface(setcolor=with_alpha(color, color[3] if len(color) > 3 else 255),
                       unsetcolor=(0, 0, 0, 0))
    for i in range(steps):
        a = 2 * math.pi * i / steps
        out.blit(sil, (t + round(math.cos(a) * thickness), t + round(math.sin(a) * thickness)))
    out.blit(sil, (t, t))
    out.blit(surf, (t, t))
    return out


def silhouette(surf, color, alpha_threshold=20):
    m = pygame.mask.from_surface(surf, alpha_threshold)
    return m.to_surface(setcolor=color, unsetcolor=(0, 0, 0, 0))


def vertical_gradient(size, top, bottom, alpha=None):
    w, h = size
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        c = mix(top, bottom, y / max(1, h - 1))
        if alpha is not None:
            c = with_alpha(c, alpha)
        pygame.draw.line(s, c, (0, y), (w, y))
    return s


def radial_glow(radius, color, strength=1.0):
    """Círculo difuso (para luces y brillos)."""
    size = radius * 2
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    for i in range(radius, 0, -2):
        a = int(255 * strength * (1 - i / radius) ** 2)
        pygame.draw.circle(s, with_alpha(color, min(255, a)), (radius, radius), i)
    return s


def blit_center(dst, src, center):
    r = src.get_rect(center=(round(center[0]), round(center[1])))
    dst.blit(src, r)
    return r


def rotate_about(src, angle, pivot_src, pivot_dst, scale=1.0):
    """Rota/escala 'src' alrededor de pivot_src (coords de src) y devuelve
    (superficie, posición de blit) para que el pivote caiga en pivot_dst."""
    w, h = src.get_size()
    cx, cy = w / 2, h / 2
    vx, vy = (pivot_src[0] - cx) * scale, (pivot_src[1] - cy) * scale
    rad = math.radians(angle)
    # pygame rota en sentido antihorario con y hacia abajo
    rx = vx * math.cos(rad) + vy * math.sin(rad)
    ry = -vx * math.sin(rad) + vy * math.cos(rad)
    rot = pygame.transform.rotozoom(src, angle, scale)
    rw, rh = rot.get_size()
    return rot, (pivot_dst[0] - rx - rw / 2, pivot_dst[1] - ry - rh / 2)
