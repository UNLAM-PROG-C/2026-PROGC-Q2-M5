"""Own pixel art font (5x7 with lower case, accents and arrows).

It does not depend on system fonts: each glyph is a grid of '#'. A letter
"box" is 11 rows: accents in 0-1, capitals in 2-8 (baseline at 8) and
descenders in 9-10. Text is drawn at scale 1 and enlarged without smoothing
(sharp pixels, retro style).
"""
import pygame

from fdc.ui import palette

BOX_H = 11          # rows of a letter box (accents + capitals + descenders)
LINE_H = 12         # rows between lines
CAP_TOP = 2         # first row of the capitals (below the accents)
BASELINE = 9        # row after the baseline (where capitals and digits end)
DEFAULT_SCALE = 2   # default scale of the font
CACHE_LIMIT = 800   # texts kept before the cache is emptied
LED_DOT = 4         # px per lamp of the LED scoreboard
LED_HIGHLIGHT = 70  # how much lighter the shine of a lit lamp is
LED_HIGHLIGHT_MIN = 3   # lamps of this size or more get their shine
# The 1-pixel outline is made by moving the letter to its neighbours.
OUTLINE_OFFSETS = (-1, 0, 1)
LOWER_ACCENT_ROW = 2    # accents of lower case letters go on this row
ON = "#"            # a lit pixel in the glyph grids

# char -> (top row, rows)
GLYPHS = {}


def _glyph(chars, top, *rows):
  for c in chars:
    GLYPHS[c] = (top, rows)


# --- capitals -------------------------------------------------------------
_glyph("A", 2, ".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#")
_glyph("B", 2, "####.", "#...#", "#...#", "####.", "#...#", "#...#", "####.")
_glyph("C", 2, ".###.", "#...#", "#....", "#....", "#....", "#...#", ".###.")
_glyph("D", 2, "####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####.")
_glyph("E", 2, "#####", "#....", "#....", "####.", "#....", "#....", "#####")
_glyph("F", 2, "#####", "#....", "#....", "####.", "#....", "#....", "#....")
_glyph("G", 2, ".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####")
_glyph("H", 2, "#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#")
_glyph("I", 2, "###", ".#.", ".#.", ".#.", ".#.", ".#.", "###")
_glyph("J", 2, "..###", "...#.", "...#.", "...#.", "#..#.", "#..#.", ".##..")
_glyph("K", 2, "#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#")
_glyph("L", 2, "#....", "#....", "#....", "#....", "#....", "#....", "#####")
_glyph("M", 2, "#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#")
_glyph("N", 2, "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#")
_glyph("O", 2, ".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###.")
_glyph("P", 2, "####.", "#...#", "#...#", "####.", "#....", "#....", "#....")
_glyph("Q", 2, ".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#")
_glyph("R", 2, "####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#")
_glyph("S", 2, ".####", "#....", "#....", ".###.", "....#", "....#", "####.")
_glyph("T", 2, "#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#..")
_glyph("U", 2, "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###.")
_glyph("V", 2, "#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#..")
_glyph("W", 2, "#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#.")
_glyph("X", 2, "#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#")
_glyph("Y", 2, "#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#..")
_glyph("Z", 2, "#####", "....#", "...#.", "..#..", ".#...", "#....", "#####")
# --- digits ----------------------------------------------------------------
_glyph("0", 2, ".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###.")
_glyph("1", 2, "..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###.")
_glyph("2", 2, ".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####")
_glyph("3", 2, "####.", "....#", "....#", ".###.", "....#", "....#", "####.")
_glyph("4", 2, "...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#.")
_glyph("5", 2, "#####", "#....", "####.", "....#", "....#", "#...#", ".###.")
_glyph("6", 2, ".###.", "#....", "#....", "####.", "#...#", "#...#", ".###.")
_glyph("7", 2, "#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#...")
_glyph("8", 2, ".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###.")
_glyph("9", 2, ".###.", "#...#", "#...#", ".####", "....#", "....#", ".###.")
# --- lower case -------------------------------------------------------------
_glyph("a", 4, ".###.", "....#", ".####", "#...#", ".####")
_glyph("b", 2, "#....", "#....", "####.", "#...#", "#...#", "#...#", "####.")
_glyph("c", 4, ".###.", "#....", "#....", "#....", ".###.")
_glyph("d", 2, "....#", "....#", ".####", "#...#", "#...#", "#...#", ".####")
_glyph("e", 4, ".###.", "#...#", "#####", "#....", ".###.")
_glyph("f", 2, "..##", ".#..", "####", ".#..", ".#..", ".#..", ".#..")
_glyph("g", 4, ".####", "#...#", "#...#", "#...#", ".####", "....#", ".###.")
_glyph("h", 2, "#....", "#....", "####.", "#...#", "#...#", "#...#", "#...#")
_glyph("i", 2, "#", ".", "#", "#", "#", "#", "#")
_glyph("j", 2, "..#", "...", "..#", "..#", "..#", "..#", "..#", "#.#", ".#.")
_glyph("k", 2, "#...", "#...", "#..#", "#.#.", "##..", "#.#.", "#..#")
_glyph("l", 2, "#.", "#.", "#.", "#.", "#.", "#.", ".#")
_glyph("m", 4, "##.#.", "#.#.#", "#.#.#", "#.#.#", "#.#.#")
_glyph("n", 4, "####.", "#...#", "#...#", "#...#", "#...#")
_glyph("o", 4, ".###.", "#...#", "#...#", "#...#", ".###.")
_glyph("p", 4, "####.", "#...#", "#...#", "#...#", "####.", "#....", "#....")
_glyph("q", 4, ".####", "#...#", "#...#", "#...#", ".####", "....#", "....#")
_glyph("r", 4, "#.##", "##..", "#...", "#...", "#...")
_glyph("s", 4, ".####", "#....", ".###.", "....#", "####.")
_glyph("t", 2, ".#..", ".#..", "####", ".#..", ".#..", ".#..", "..##")
_glyph("u", 4, "#...#", "#...#", "#...#", "#...#", ".####")
_glyph("v", 4, "#...#", "#...#", "#...#", ".#.#.", "..#..")
_glyph("w", 4, "#...#", "#...#", "#.#.#", "#.#.#", ".#.#.")
_glyph("x", 4, "#...#", ".#.#.", "..#..", ".#.#.", "#...#")
_glyph("y", 4, "#...#", "#...#", "#...#", "#...#", ".####", "....#", ".###.")
_glyph("z", 4, "#####", "...#.", "..#..", ".#...", "#####")
_glyph("ı", 4, "#", "#", "#", "#", "#")
# --- signs -----------------------------------------------------------------
_glyph(" ", 8, "...")
_glyph(".", 8, "#")
_glyph(",", 8, ".#", "#.")
_glyph(":", 4, "#", ".", ".", "#")
_glyph(";", 4, ".#", "..", "..", ".#", "#.")
_glyph("!", 2, "#", "#", "#", "#", "#", ".", "#")
_glyph("¡", 4, "#", ".", "#", "#", "#", "#", "#")
_glyph("?", 2, ".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#..")
_glyph("¿", 4, "..#..", ".....", "..#..", ".#...", "#....", "#...#", ".###.")
_glyph("-", 5, "####")
_glyph("+", 4, "..#..", "..#..", "#####", "..#..", "..#..")
_glyph("=", 5, "####", "....", "####")
_glyph("(", 2, "..#", ".#.", "#..", "#..", "#..", ".#.", "..#")
_glyph(")", 2, "#..", ".#.", "..#", "..#", "..#", ".#.", "#..")
_glyph("[", 2, "##", "#.", "#.", "#.", "#.", "#.", "##")
_glyph("]", 2, "##", ".#", ".#", ".#", ".#", ".#", "##")
_glyph("/", 2, "....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#....")
_glyph("|", 1, "#", "#", "#", "#", "#", "#", "#", "#", "#")
_glyph("%", 2, "##..#", "##.#.", "...#.", "..#..", ".#...", ".#.##", "#..##")
_glyph("'", 2, "#", "#")
_glyph('"', 2, "#.#", "#.#")
_glyph("<", 3, "...#", "..#.", ".#..", "#...", ".#..", "..#.", "...#")
_glyph(">", 3, "#...", ".#..", "..#.", "...#", "..#.", ".#..", "#...")
_glyph("_", 9, "#####")
_glyph("#", 2, ".#.#.", "#####", ".#.#.", ".#.#.", "#####", ".#.#.")
_glyph("*", 3, "#.#.#", ".###.", "#####", ".###.", "#.#.#")
_glyph("×", 4, "#...#", ".#.#.", "..#..", ".#.#.", "#...#")
_glyph("&", 2, ".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#")
_glyph("←", 4, "..#..", ".#...", "#####", ".#...", "..#..")
_glyph("→", 4, "..#..", "...#.", "#####", "...#.", "..#..")
_glyph("↑", 2, "..#..", ".###.", "#.#.#", "..#..", "..#..", "..#..", "..#..")
_glyph("↓", 2, "..#..", "..#..", "..#..", "..#..", "#.#.#", ".###.", "..#..")
_glyph("►", 2, "#....", "##...", "###..", "####.", "###..", "##...", "#....")
_glyph("◄", 2, "....#", "...##", "..###", ".####", "..###", "...##", "....#")
_glyph("•", 4, ".##.", "####", "####", ".##.")
_glyph("º", 2, ".#.", "#.#", ".#.", "...", "###")
_glyph("ª", 2, ".##", "#.#", ".##", "...", "###")

# --- accents (composed)
_ACUTE = ("..#", ".#.")
_TILDE = (".#.#", "#.#.")
_DIAER = ("#.#",)


def _pixels(top, rows, col_offset=0):
  """Set of (row, column) of the lit pixels of a grid."""
  return {(top + r, col_offset + c) for r, line in enumerate(rows)
          for c, ch in enumerate(line) if ch == ON}


def _compose(base, mark, lower):
  """Glyph of `base` with an accent `mark` on top."""
  top, rows = GLYPHS[base]
  offset = (len(rows[0]) - len(mark[0])) // 2
  mark_row = LOWER_ACCENT_ROW if lower else 0
  grid = _pixels(top, rows) | _pixels(mark_row, mark, offset)
  c0 = min(c for _, c in grid)
  c1 = max(c for _, c in grid) + 1
  new_top = min(top, mark_row)
  rows_out = tuple("".join(ON if (r, c) in grid else "."
                           for c in range(c0, c1))
                   for r in range(new_top, top + len(rows)))
  return new_top, rows_out


for _src, _dst in (("A", "Á"), ("E", "É"), ("I", "Í"), ("O", "Ó"),
                   ("U", "Ú")):
  GLYPHS[_dst] = _compose(_src, _ACUTE, False)
GLYPHS["Ñ"] = _compose("N", _TILDE, False)
GLYPHS["Ü"] = _compose("U", _DIAER, False)
for _src, _dst in (("a", "á"), ("e", "é"), ("ı", "í"), ("o", "ó"),
                   ("u", "ú")):
  GLYPHS[_dst] = _compose(_src, _ACUTE, True)
GLYPHS["ñ"] = _compose("n", _TILDE, True)
GLYPHS["ü"] = _compose("u", _DIAER, True)

REPLACE = {"…": "...", "·": "-", "—": "-", "–": "-", "−": "-"}
_cache = {}


def clear_cache():
  """Drops the cached surfaces (when pygame closes)."""
  _cache.clear()


def normalize(text):
  """Replaces characters the font lacks."""
  for old, new in REPLACE.items():
    text = text.replace(old, new)
  return "".join(c if c in GLYPHS else ("?" if c.strip() else " ")
                 for c in text)


def text_width(text, scale=1):
  text = normalize(text)
  if not text:
    return 0
  width = sum(len(GLYPHS[c][1][0]) + 1 for c in text) - 1
  return width * scale


def _mask(text):
  """White surface (scale 1) with the pixels of the text."""
  text = normalize(text)
  surf = pygame.Surface((max(1, text_width(text)), BOX_H), pygame.SRCALPHA)
  x = 0
  for c in text:
    top, rows = GLYPHS[c]
    for row, col in _pixels(top, rows, x):
      surf.set_at((col, row), (*palette.WHITE, palette.OPAQUE))
    x += len(rows[0]) + 1
  return surf


def _tinted(mask, color):
  tinted = mask.copy()
  tinted.fill((*color[:palette.RGB_CHANNELS], palette.OPAQUE),
              special_flags=pygame.BLEND_RGBA_MULT)
  return tinted


def render(text, scale=DEFAULT_SCALE, color=palette.WHITE, outline=None,
           shadow=None, shadow_off=1):
  """Sharp text. outline: outline colour (1 font pixel); shadow: colour
    of a shadow moved down and to the right."""
  key = (text, scale, tuple(color), tuple(outline) if outline else None,
         tuple(shadow) if shadow else None, shadow_off)
  cached = _cache.get(key)
  if cached is not None:
    return cached
  base = _compose_layers(_mask(text), color, outline, shadow, shadow_off)
  surf = pygame.transform.scale(base, (base.get_width() * scale,
                                       base.get_height() * scale))
  if len(_cache) > CACHE_LIMIT:
    _cache.clear()
  _cache[key] = surf
  return surf


def _compose_layers(mask, color, outline, shadow, shadow_off):
  """Shadow, outline and letters at scale 1."""
  width, height = mask.get_size()
  pad = 1 if outline else 0
  extra = shadow_off if shadow else 0
  base = pygame.Surface((width + 2 * pad + extra, height + 2 * pad + extra),
                        pygame.SRCALPHA)
  if shadow:
    _blit_shadow(base, _tinted(mask, shadow), pad, extra, outline)
  if outline:
    _blit_outline(base, _tinted(mask, outline), pad)
  base.blit(_tinted(mask, color), (pad, pad))
  return base


def _blit_outline(base, outline_img, pad):
  for dx in OUTLINE_OFFSETS:
    for dy in OUTLINE_OFFSETS:
      if dx or dy:
        base.blit(outline_img, (pad + dx, pad + dy))


def _blit_shadow(base, shadow_img, pad, extra, outline):
  if not outline:
    base.blit(shadow_img, (extra, extra))
    return
  for dx in OUTLINE_OFFSETS:
    for dy in OUTLINE_OFFSETS:
      base.blit(shadow_img, (pad + dx + extra, pad + dy + extra))


def render_led(text, dot=LED_DOT, on=palette.LED_ON, off=palette.LED_OFF,
               bg=None):
  """Scoreboard text: each font pixel is a square lamp."""
  key = ("led", text, dot, tuple(on), tuple(off) if off else None,
         tuple(bg) if bg else None)
  cached = _cache.get(key)
  if cached is not None:
    return cached
  _cache[key] = _led_surface(_mask(text), dot, on, off, bg)
  return _cache[key]


def _led_surface(mask, dot, on, off, bg):
  width = mask.get_width()
  # Only the band of capitals and digits.
  surf = pygame.Surface((width * dot + 1, (BASELINE - CAP_TOP) * dot + 1),
                        pygame.SRCALPHA)
  if bg:
    surf.fill(bg)
  for y in range(CAP_TOP, BASELINE):
    for x in range(width):
      _lamp(surf, mask.get_at((x, y)).a > 0, x, y, dot, on, off)
  return surf


def _lamp(surf, lit, x, y, dot, on, off):
  """One LED lamp: lit (with a shine) or off."""
  size = max(1, dot - 1)
  rect = pygame.Rect(x * dot + 1, (y - CAP_TOP) * dot + 1, size, size)
  if lit:
    pygame.draw.rect(surf, on, rect)
    if size >= LED_HIGHLIGHT_MIN:
      shine = tuple(min(palette.MAX_CHANNEL, c + LED_HIGHLIGHT)
                    for c in on)
      pygame.draw.rect(surf, shine, (rect.x, rect.y, size - 1, 1))
  elif off:
    pygame.draw.rect(surf, off, rect)
