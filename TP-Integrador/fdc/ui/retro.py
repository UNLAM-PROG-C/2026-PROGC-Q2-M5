"""Retro drawing helpers: crisp pixels, bevelled panels and boxes.

The world is drawn with "art pixels" of PX = 2 logical pixels: sprites and
the background are generated at native resolution and scaled x2 without
smoothing.
"""
import pygame

from fdc.ui import palette

PX = 2                  # logical pixels per art pixel (all pixel art is x2)
# When pixelizing, pixels less opaque than this become transparent.
ALPHA_CUT = 110
MASK_THRESHOLD = 20     # minimum opacity of a pixel to count in the outline
DITHER_ALPHA = 90       # opacity of the dots of the dithered shadow
BEVEL_LIGHT = 45        # how much lighter the bevel light is (top and left)
BEVEL_DARK = 45         # how much darker the bevel shade is (bottom, right)
BOX_SHADOW_ALPHA = 60   # opacity of the shadow of a bevelled box
PANEL_SHADOW_ALPHA = 70  # opacity of the shadow of a panel
PANEL_SHADOW_OFFSET = 3  # art pixels the shadow of a panel is shifted
PANEL_INNER_LINE = 5     # art pixels from the edge to the inner line
PANEL_INNER_DARKEN = 28  # how much darker than the face the inner line is
PANEL_PADDING = 8        # art pixels from the edge to the usable area


def scale_px(surf, k=PX):
  """Scales a native surface by k without smoothing."""
  return pygame.transform.scale(
      surf, (surf.get_width() * k, surf.get_height() * k))


def snap(v, k=PX):
  """Rounds v to the grid of art pixels."""
  return int(round(v / k)) * k


def pixelize(surf, native_w, alpha_cut=ALPHA_CUT):
  """Reduces a smooth drawing to native pixel art (binary alpha)."""
  w, h = surf.get_size()
  nh = max(1, round(h * native_w / w))
  small = pygame.transform.smoothscale(surf, (native_w, nh))
  out = pygame.Surface((native_w, nh), pygame.SRCALPHA)
  for y in range(nh):
    for x in range(native_w):
      c = small.get_at((x, y))
      if c.a >= alpha_cut:
        out.set_at((x, y), _unblend(c))
  return out


def _unblend(c):
  """Undoes the blend with the transparent background."""
  k = palette.MAX_CHANNEL / c.a
  top = palette.MAX_CHANNEL
  return (min(top, int(c.r * k)), min(top, int(c.g * k)),
          min(top, int(c.b * k)), palette.OPAQUE)


def outline_native(surf, color, width=1):
  """Outer outline of 'width' pixels (at the same resolution)."""
  w, h = surf.get_size()
  out = pygame.Surface((w + 2 * width, h + 2 * width), pygame.SRCALPHA)
  rgb = tuple(color)[:palette.RGB_CHANNELS]
  sil = pygame.mask.from_surface(surf, MASK_THRESHOLD).to_surface(
      setcolor=(*rgb, palette.OPAQUE), unsetcolor=(0, 0, 0, 0))
  for dx in range(-width, width + 1):
    for dy in range(-width, width + 1):
      if dx or dy:
        out.blit(sil, (width + dx, width + dy))
  out.blit(surf, (width, width))
  return out


def dither_ellipse(w, h, color=palette.SHADOW, alpha=DITHER_ALPHA):
  """Shadow with a checkerboard pattern (16-bit style)."""
  s = pygame.Surface((max(2, w), max(2, h)), pygame.SRCALPHA)
  rx, ry = w / 2, h / 2
  for y in range(h):
    for x in range(w):
      inside = (((x - rx + 0.5) / rx) ** 2
                + ((y - ry + 0.5) / ry) ** 2 <= 1)
      if inside and (x + y) % 2 == 0:
        s.set_at((x, y), (*color, alpha))
  return s


def bevel_box(surf, rect, face, border=palette.INK, light=None, dark=None,
              shadow=True, b=PX):
  """Retro box: dark border, light top/left, shade bottom/right."""
  rect = pygame.Rect(rect)
  light = light or tuple(min(palette.MAX_CHANNEL, c + BEVEL_LIGHT)
                         for c in face)
  dark = dark or tuple(max(0, c - BEVEL_DARK) for c in face)
  if shadow:
    _blit_shadow(surf, rect, BOX_SHADOW_ALPHA, 2 * b)
  pygame.draw.rect(surf, border, rect)
  inner = rect.inflate(-2 * b, -2 * b)
  pygame.draw.rect(surf, face, inner)
  _draw_bevel(surf, inner, light, dark, b)
  return inner


def _blit_shadow(surf, rect, alpha, offset):
  sh = pygame.Surface(rect.size, pygame.SRCALPHA)
  sh.fill((*palette.SHADOW, alpha))
  surf.blit(sh, rect.move(offset, offset))


def _draw_bevel(surf, inner, light, dark, b):
  pygame.draw.rect(surf, light, (inner.left, inner.top, inner.width, b))
  pygame.draw.rect(surf, light, (inner.left, inner.top, b, inner.height))
  pygame.draw.rect(surf, dark, (inner.left, inner.bottom - b,
                                inner.width, b))
  pygame.draw.rect(surf, dark, (inner.right - b, inner.top,
                                b, inner.height))


def panel(surf, rect, face=palette.CREAM, border=palette.INK, alpha=None):
  """Dialog panel: classic double border. Returns the usable area."""
  rect = pygame.Rect(rect)
  _blit_shadow(surf, rect, PANEL_SHADOW_ALPHA, PANEL_SHADOW_OFFSET * PX)
  if alpha is not None:
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    layer.fill((*face, alpha))
    surf.blit(layer, rect)
  else:
    pygame.draw.rect(surf, face, rect)
  pygame.draw.rect(surf, border, rect, 2 * PX)
  inner = rect.inflate(-PANEL_INNER_LINE * PX, -PANEL_INNER_LINE * PX)
  pygame.draw.rect(surf, tuple(max(0, c - PANEL_INNER_DARKEN) for c in face),
                   inner, PX)
  return rect.inflate(-PANEL_PADDING * PX, -PANEL_PADDING * PX)
