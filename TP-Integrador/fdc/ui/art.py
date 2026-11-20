"""Drawing tools: colour blends, curves and shapes with transparency.

pygame.draw does not blend transparency: if the colour has alpha, the shape
is drawn opaque on a small layer and that layer is blended on the target.
"""
import math

import pygame

from fdc.ui import palette

BEZIER_STEPS = 16           # segments that approximate a Bezier curve
BLEND_MARGIN = 2            # px of margin of the helper layer around a shape
MIN_POLYGON_POINTS = 3      # a polygon needs at least three points
MIN_POLYLINE_POINTS = 2     # a stroke needs at least two points
GLOW_RING_STEP = 2          # px between the rings of the soft glow
RGBA_CHANNELS = 4           # channels of a colour with alpha (r, g, b, a)
ALPHA = 3                   # index of the alpha inside an RGBA colour


def lerp(a, b, t):
  """Linear interpolation between a and b."""
  return a + (b - a) * t


def mix(c1, c2, t):
  """Colour between c1 (t = 0) and c2 (t = 1)."""
  rgb = palette.RGB_CHANNELS
  return tuple(int(round(lerp(a, b, t))) for a, b in zip(c1[:rgb], c2[:rgb]))


def shade(color, k):
  """k > 0 lightens towards white, k < 0 darkens towards black."""
  if k >= 0:
    return mix(color, palette.WHITE, k)
  return mix(color, palette.SHADOW, -k)


def with_alpha(color, a):
  """The same colour with alpha a."""
  return (*color[:palette.RGB_CHANNELS], a)


def canvas(w, h):
  """Transparent surface of at least 1x1."""
  return pygame.Surface((max(1, int(w)), max(1, int(h))), pygame.SRCALPHA)


def bezier(p0, p1, p2, steps=BEZIER_STEPS):
  """Quadratic Bezier curve (p1 is the control point)."""
  out = []
  for i in range(steps + 1):
    t = i / steps
    a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
    out.append((a * p0[0] + b * p1[0] + c * p2[0],
                a * p0[1] + b * p1[1] + c * p2[1]))
  return out


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def _translucent(color):
  return len(color) == RGBA_CHANNELS and color[ALPHA] < palette.OPAQUE


def _blend(surf, color, bbox, draw):
  """Draws opaque on a small layer and blends it with the colour alpha."""
  left, top, right, bottom = bbox
  x0 = int(math.floor(left)) - BLEND_MARGIN
  y0 = int(math.floor(top)) - BLEND_MARGIN
  x1 = int(math.ceil(right)) + BLEND_MARGIN
  y1 = int(math.ceil(bottom)) + BLEND_MARGIN
  w, h = max(1, x1 - x0), max(1, y1 - y0)
  layer = pygame.Surface((w, h), pygame.SRCALPHA)
  draw(layer, with_alpha(color, palette.OPAQUE), (-x0, -y0))
  layer.fill((*palette.WHITE, color[ALPHA]),
             special_flags=pygame.BLEND_RGBA_MULT)
  surf.blit(layer, (x0, y0))


def _bbox(pts, pad=0.0):
  xs = [p[0] for p in pts]
  ys = [p[1] for p in pts]
  return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _shift(pts, off):
  return [(x + off[0], y + off[1]) for x, y in pts]


def poly(surf, color, pts):
  """Filled polygon (with alpha if the colour has it)."""
  if len(pts) < MIN_POLYGON_POINTS:
    return
  if _translucent(color):
    _blend(surf, color, _bbox(pts),
           lambda l, c, o: pygame.draw.polygon(l, c, _shift(pts, o)))
  else:
    pygame.draw.polygon(surf, color, pts)


def circle(surf, color, c, r):
  """Filled circle (with alpha if the colour has it)."""
  if r <= 0:
    return
  if _translucent(color):
    _blend(surf, color, (c[0] - r, c[1] - r, c[0] + r, c[1] + r),
           lambda l, cc, o: pygame.draw.circle(
               l, cc, (round(c[0] + o[0]), round(c[1] + o[1])),
               max(1, round(r))))
  else:
    pygame.draw.circle(surf, color, (round(c[0]), round(c[1])),
                       max(1, round(r)))


def _thick_polyline_opaque(surf, color, pts, width):
  r = width / 2
  for a, b in zip(pts, pts[1:]):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy) or 1
    nx, ny = -dy / d * r, dx / d * r
    pygame.draw.polygon(surf, color, [
        (a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny),
        (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)])
  for p in pts:
    pygame.draw.circle(surf, color, (round(p[0]), round(p[1])),
                       max(1, round(r)))


def thick_polyline(surf, color, pts, width):
  """Thick stroke with rounded ends and joints."""
  if len(pts) < MIN_POLYLINE_POINTS:
    return
  if _translucent(color):
    _blend(surf, color, _bbox(pts, width),
           lambda l, c, o: _thick_polyline_opaque(l, c, _shift(pts, o),
                                                  width))
  else:
    _thick_polyline_opaque(surf, color, pts, width)


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------
def clip(layer, mask_surf):
  """Clips 'layer' to the shape of mask_surf (multiplies the alpha)."""
  layer.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
  return layer


def radial_glow(radius, color, strength=1.0):
  """Soft circle (for lights and glows)."""
  size = radius * 2
  s = pygame.Surface((size, size), pygame.SRCALPHA)
  for i in range(radius, 0, -GLOW_RING_STEP):
    a = int(palette.MAX_CHANNEL * strength * (1 - i / radius) ** 2)
    pygame.draw.circle(s, with_alpha(color, min(palette.MAX_CHANNEL, a)),
                       (radius, radius), i)
  return s
