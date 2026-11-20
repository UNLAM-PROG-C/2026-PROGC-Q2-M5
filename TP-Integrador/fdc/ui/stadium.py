"""Retro stadium: pixel art background, goals, ball and shadows.

The background is drawn once at native resolution (640 x 360) with light
colours and scaled x2. Stands and crowd use soft pastel tones so the ball
and the players (with an outline) always stand out.

Background measures are NATIVE px (half the logical screen); the ones of
goals, ball and shadows are px of the logical screen.
"""
import math
import random

import pygame

from fdc import config
from fdc.ui import art
from fdc.ui import assets
from fdc.ui import palette
from fdc.ui import pixelfont
from fdc.ui import retro

PX = retro.PX
W, H = config.Arena.WIDTH, config.Arena.HEIGHT
NW, NH = W // PX, H // PX
FLOOR = config.Arena.FLOOR_Y
HALF_BAR = config.Arena.BAR_THICKNESS / 2   # half the crossbar thickness
GRASS_TOP = 252            # far edge of the grass (native px)

# --- sky
# Seed of the crowd and the grass: the stadium always looks the same.
STADIUM_SEED = 1986
SKY_BOTTOM_Y = 40                  # the sky gradient goes from y = 0 to 40
# Ordered 4 x 4 dither matrix (Bayer): which gradient pixels get each colour.
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
BAYER_SIZE = 4                     # side of that matrix
BAYER_LEVELS = 16                  # levels of the pattern (4 x 4)
# Clouds: (x, y, width) in native px.
CLOUDS = ((40, 8, 36), (230, 4, 28), (430, 10, 40), (580, 6, 24))
# Puffs of a cloud: (dx, dy, radius) in native px.
CLOUD_PUFFS = ((0, 4, 6), (7, 0, 8), (16, 3, 7), (24, 5, 5))
CLOUD_W = 30                       # cloud width those puffs are measured for
CLOUD_SHADE_DROP = 2               # px the shade of each puff goes down
# --- roof
ROOF_TOP, ROOF_BOTTOM = 24, 46     # the roof goes from y = 24 to 46
ROOF_EDGE = 4                      # shaded band at the foot of the roof
ROOF_TRUSS = 16                    # px between the Vs of the truss
ROOF_TRUSS_TOP = 1                 # the truss starts 1 px below the top...
ROOF_TRUSS_BOTTOM = 6              # ...and ends 6 px above the foot
ROOF_SHADOW = 10                   # shadow below the roof (height, px)
COLUMN_X0 = 20                     # first column (px)...
COLUMN_EVERY = 120                 # ...and one every 120 px
COLUMN_W = 3                       # column width (with 1 px light inside)
FLOODLIGHTS = (60, 250, 390, 580)  # x of the floodlights (px)
FLOODLIGHT = (18, 6)               # box of a floodlight (width, height)
LAMPS = 4                          # lamps per floodlight
LAMP_FIRST_X = -7                  # first lamp, from the floodlight centre
LAMP_STEP = 4                      # px between lamps
LAMP_Y = -5                        # lamps, from the roof edge (px)
LAMP_SIZE = 3                      # px: side of a lamp
LAMP_COLOR = (255, 250, 214)       # warm light
# --- stands
# Three stands: (top y, bottom y) in native px.
TIERS = ((56, 112), (116, 176), (180, 232))
TIER_RAIL = 4                      # rail over each stand (height, px)
SEAT_ROW = 6                       # height of each row of seats (px)
# Shirts of the crowd: the muted tones of the animated stands (guia-visual).
# Skin and hair come from the same table, so OPTIMIZADO and FULL match.
CROWD_COLORS = [tuple(round(channel * 255) for channel in shirt)
                for shirt in config.Gpu.CROWD_SHIRTS]
SKIN_TONES = [tuple(round(channel * 255) for channel in skin)
              for skin in config.Gpu.CROWD_SKINS]   # skin tones (RGB)
CROWD_START_MAX = 3                # first person of a row: x from 0 to 3
CROWD_FILL = 0.62                  # probability that a seat is taken
ARMS_UP = 0.06                     # probability of arms up
CROWD_GAP = (5, 7)                 # px from one person to the next (random)
BODY = (0, 2, 4, 3)                # body of a person (dx, dy, width, height)
HEAD = (1, 0, 2, 2)                # head (dx, dy, width, height)
ARMS = ((-1, -2, 1, 2), (4, -2, 1, 2))   # arms up (dx, dy, width, height)
STAIRS_X0 = 64                     # first stairs (px)...
STAIRS_EVERY = 128                 # ...and one every 128 px
STAIRS_W = 8                       # width of the stairs (px)
STEP_H = 3                         # height of each step (px)
# --- stands at the final resolution (only the OPTIMIZADO mode sees them) ---
# Same geometry and colours as the animated crowd of FULL (`k_tribuna`), so
# both modes show the same people instead of blocks of 2 x 2 px.
CROWD_TOP = config.Gpu.CROWD_TOP            # px: top of the stands
CROWD_BOTTOM = config.Gpu.CROWD_BOTTOM      # px: its bottom (the wall)
CROWD_SEAT = config.Gpu.CROWD_SEAT          # px: one seat of the grid
CROWD_BODY = config.Gpu.CROWD_BODY          # px: shirt of one person
CROWD_HEAD = config.Gpu.CROWD_HEAD          # px: radius of the head
CROWD_STEP = int(config.Gpu.CROWD_STEP)     # px: dark step of a row
CROWD_STEP_RIM = 1                 # px: lit edge of that step
CROWD_SHOULDER_EDGE = 1            # px: darker line on top of the shirt
CROWD_SHOULDER_SHADE = config.Gpu.CROWD_SHOULDER_SHADE   # how much it darkens
CROWD_HAIR_DROP = 2                # px the hair goes up over the face
CROWD_FACE_INSET = 1               # px the face shrinks inside the rim
CROWD_SHIRTS = config.Gpu.CROWD_SHIRTS      # 0-1 rgb of each team's shirt
CROWD_SKINS = config.Gpu.CROWD_SKINS        # 0-1 rgb: skin tones
CROWD_HAIRS = config.Gpu.CROWD_HAIRS        # 0-1 rgb: hair tones
CROWD_TREAD = config.Gpu.CROWD_TREAD        # 0-1 rgb: floor of a row
CROWD_RISER = config.Gpu.CROWD_RISER        # ...its dark front
CROWD_EDGE = config.Gpu.CROWD_EDGE          # ...and its lit edge
CROWD_OUTLINE_COLOUR = config.Gpu.CROWD_OUTLINE_COLOUR   # rim of the heads
CROWD_SHADE_TOP = config.Gpu.CROWD_SHADE_TOP      # darkness of the last row
CROWD_SHADE_BOTTOM = config.Gpu.CROWD_SHADE_BOTTOM   # ...and of the first
CROWD_VAR_MIN = config.Gpu.CROWD_VAR_MIN    # brightness of the dullest shirt
CROWD_VAR_RANGE = config.Gpu.CROWD_VAR_RANGE   # extra brightness of a shirt
BYTE_MAX = 255.0                   # top of a channel (colours are 0-1 here)
# --- wall and advertising boards
WALL_Y = 232                       # wall below the last stand (px)...
WALL_H = 3                         # ...and its height
BOARD_Y = WALL_Y + WALL_H          # boards, next to the wall...
BOARD_H = 17                       # ...down to the grass edge (px)
BOARD_TOP_STRIPE = 3               # colour band on top of a board (px)
BOARD_BOTTOM_STRIPE = 2            # colour band at the bottom (px)
BOARD_TEXT_DROP = 1                # the text goes 1 px below the centre
# --- grass
STRIPE_FAR = 36                    # width of the grass stripes far away...
STRIPE_GROWTH = 20                 # ...that open up to 36 + 20 at the front
STRIPE_OFFSET = 100                # keeps the stripe number positive
GRASS_BLADES = 900                 # loose dark blades of grass
BLADES_BELOW = 2                   # they start 2 px below the grass edge
FAR_LINE = 4                       # far chalk line: px below the grass edge
NEAR_LINE = 6                      # near chalk line: px above the bottom
# Centre circle (how far left of the centre it starts, y, width, height).
CENTER_CIRCLE = (64, 280, 128, 44)
CENTER_SPOT = (1, 301, 3, 2)       # centre spot (same fields)
AREA_TOP = 10                      # penalty areas: px below the far line...
AREA_BOTTOM = 8                    # ...and above the near line
AREA_FAR_W = 58                    # width of the area far away (px)...
AREA_NEAR_W = 74                   # ...and at the front (perspective)
# Advertising boards: (text, colour name in the palette).
BOARDS = ((config.GAME_NAME.upper(), "BLUE"),
          ("PROGRAMACION CONCURRENTE", "RED"),
          ("PROCESOS  COLAS  EVENTOS", "GREEN"),
          (config.GAME_NAME.upper(), "PURPLE"))

# --- goals
NET_FILL = (255, 255, 255, 40)     # net: almost transparent white...
NET_LINE_COLOR = (255, 255, 255, 150)  # ...with stronger threads
NET_CELL = 8                       # px between threads of the net
GOAL_SHADOW_H = 5                  # native px: height of the goal shadow
GOAL_SHADOW_ALPHA = 80             # opacity of that shadow
GOAL_SHADOW_RAISE = 6              # px above the floor
POST_W = 6                         # px: width of the back post
POST_INSET = 6                     # px from the side of the screen
FLAG_INSET = 24                    # flag: px from the side of the screen
FLAG_POLE_H = 34                   # height of the pole over the goal (px)
FLAG_W = 30                        # length of the triangle (px)
FLAG_H = 18                        # height of the triangle (px)
BAR_RADIUS = 6                     # rounded corners of the crossbar frame...
BAR_INNER_RADIUS = 5               # ...and of the crossbar (px)
GLOW_MARGIN = 8                    # px of crossbar glow with a power
GLOW_ALPHA = 70                    # opacity of that glow
GOAL_LINE_MARK = 10                # px: chalk mark below the goal mouth

# --- ball
BALL_WHITE = (250, 250, 250)       # ball white (a bit grey: not a shine)
PENTAGON_SIDES = 5                 # black patches: pentagons...
PENTAGON_STEP = 72                 # ...with a vertex every 72 degrees
UP_ANGLE = -90                     # degrees: vertex pointing up
CENTER_PATCH = 0.38                # centre patch radius (share of the ball)
# Degrees: the outer patches go between the vertices of the centre one.
PATCH_OFFSET = 36
PATCH_DISTANCE = 0.98              # at this share of the radius from centre
PATCH_SIZE = 0.36                  # radius of those patches (share)
PATCH_FLIP = 180                   # degrees: outer patches are upside down
MIN_BALL_PX = 6                    # minimum ball diameter in native px
ANGLE_STEP = 15                    # degrees between cached ball frames...
ANGLE_BUCKETS = 24                 # ...24 frames = one turn
BALL_SHADE = (0, 0, 0, 60)         # fixed shade bottom right (r, g, b, a)
SHADE_AT = (0.3, 0.32)             # offset of that shade (share of radius)
SHADE_R = 0.95                     # radius of that shade (share of radius)
BALL_SHINE = (255, 255, 255, 200)  # shine top left (r, g, b, a)
SHINE_AT = (0.68, 0.62)            # position of the shine (share of radius)
SHINE_R = 0.18                     # radius of the shine (share of radius)

# --- shadows on the floor
SHADOW_ALPHA = 90                  # opacity of a shadow on the floor
SHADOW_MIN_SCALE = 0.25            # the shadow shrinks with height to 1/4...
SHADOW_FADE_HEIGHT = 380           # ...at this height (px)
SHADOW_MIN_W = 4                   # native px: minimum width
SHADOW_FLATNESS = 0.28             # shadow height = 28 % of its width
SHADOW_BOOST = 1.6                 # the dither looks lighter: compensated
SHADOW_ALPHA_STEP = 10             # similar opacities share the cached image
SHADOW_DROP = 2                    # px below the floor


def _dither_band(s, y0, y1, c_top, c_bot):
  """Two colour gradient with an ordered dither (16-bit look)."""
  for y in range(y0, y1):
    t = (y - y0) / max(1, y1 - y0 - 1)
    for x in range(NW):
      thr = (BAYER[y % BAYER_SIZE][x % BAYER_SIZE] + 0.5) / BAYER_LEVELS
      s.set_at((x, y), c_bot if t > thr else c_top)


def _cloud(s, x, y, w):
  for col, dy0 in ((palette.CLOUD_SHADE, CLOUD_SHADE_DROP),
                   (palette.CLOUD, 0)):
    for dx, dy, r in CLOUD_PUFFS:
      pygame.draw.circle(s, col, (x + int(dx * w / CLOUD_W),
                                  y + dy + dy0), int(r * w / CLOUD_W))


def _at(x, y, rect):
  """Rectangle (dx, dy, width, height) relative to the point (x, y)."""
  dx, dy, w, h = rect
  return x + dx, y + dy, w, h


def _hline(s, color, y):
  pygame.draw.line(s, color, (0, y), (NW, y))


def _roof(s):
  """Roof with a truss, columns and floodlights."""
  y0, y1 = ROOF_TOP, ROOF_BOTTOM
  pygame.draw.rect(s, palette.ROOF, (0, y0, NW, y1 - y0))
  pygame.draw.rect(s, palette.STRUCT_SHADE,
                   (0, y1 - ROOF_EDGE, NW, ROOF_EDGE))
  _hline(s, palette.STRUCT_DARK, y0)
  _hline(s, palette.STRUCT_DARK, y1 - ROOF_EDGE - 1)
  _truss(s, y0, y1)
  _under_roof(s, y1)
  for x in FLOODLIGHTS:
    _floodlight(s, x, y0)


def _under_roof(s, y1):
  """Shadow below the roof, with the columns."""
  pygame.draw.rect(s, palette.STRUCT_SHADE, (0, y1, NW, ROOF_SHADOW))
  _hline(s, palette.STRUCT_DARK, y1 + ROOF_SHADOW - 1)
  for x in range(COLUMN_X0, NW, COLUMN_EVERY):
    pygame.draw.rect(s, palette.STRUCT_DARK,
                     (x, y1, COLUMN_W, ROOF_SHADOW))
    pygame.draw.rect(s, palette.STRUCT, (x + 1, y1, 1, ROOF_SHADOW))


def _truss(s, y0, y1):
  half = ROOF_TRUSS // 2
  top, bottom = y0 + ROOF_TRUSS_TOP, y1 - ROOF_TRUSS_BOTTOM
  for x in range(0, NW + ROOF_TRUSS, ROOF_TRUSS):
    pygame.draw.line(s, palette.STRUCT_SHADE, (x, top), (x + half, bottom))
    pygame.draw.line(s, palette.STRUCT_SHADE, (x + ROOF_TRUSS, top),
                     (x + half, bottom))


def _floodlight(s, x, y0):
  fw, fh = FLOODLIGHT
  pygame.draw.rect(s, palette.STRUCT_DARK, (x - fw // 2, y0 - fh, fw, fh))
  for k in range(LAMPS):
    pygame.draw.rect(s, LAMP_COLOR, (x + LAMP_FIRST_X + k * LAMP_STEP,
                                     y0 + LAMP_Y, LAMP_SIZE, LAMP_SIZE))


def _stands(s, rng):
  """Three stands with seats, a random crowd and stairs."""
  for y0, y1 in TIERS:
    pygame.draw.rect(s, palette.SEAT_DEEP, (0, y0 - TIER_RAIL, NW,
                                            TIER_RAIL))
    _hline(s, palette.SEAT_EDGE, y0 - TIER_RAIL)
    for row_y in range(y0, y1, SEAT_ROW):
      _seat_row(s, row_y)
      _crowd_row(s, rng, row_y)
    for x in range(STAIRS_X0, NW, STAIRS_EVERY):
      _stairs(s, x, y0, y1)


def _seat_row(s, row_y):
  seat = (palette.SEAT_DARK if (row_y // SEAT_ROW) % 2 == 0
          else palette.SEAT_DEEP)
  pygame.draw.rect(s, seat, (0, row_y, NW, SEAT_ROW))
  _hline(s, palette.SEAT_DEEP, row_y + SEAT_ROW - 1)


def _crowd_row(s, rng, row_y):
  x = rng.randint(0, CROWD_START_MAX)
  while x < NW:
    if rng.random() < CROWD_FILL:
      _person(s, rng, x, row_y)
    x += rng.randint(*CROWD_GAP)


def _person(s, rng, x, row_y):
  shirt = CROWD_COLORS[0] if x < NW // 2 else CROWD_COLORS[1]
  s.fill(shirt, _at(x, row_y, BODY))
  skin = rng.choice(SKIN_TONES)
  s.fill(skin, _at(x, row_y, HEAD))
  if rng.random() < ARMS_UP:
    for arm in ARMS:
      s.fill(skin, _at(x, row_y, arm))


def _stairs(s, x, y0, y1):
  pygame.draw.rect(s, palette.SEAT_DEEP, (x, y0, STAIRS_W, y1 - y0))
  for yy in range(y0, y1, STEP_H):
    pygame.draw.line(s, palette.SEAT_DARK, (x, yy),
                     (x + STAIRS_W - 1, yy))


def _boards(s):
  """Wall and advertising boards."""
  pygame.draw.rect(s, palette.STRUCT_SHADE, (0, WALL_Y, NW, WALL_H))
  bw = NW // len(BOARDS)
  for i, (label, color_name) in enumerate(BOARDS):
    _board(s, pygame.Rect(i * bw, BOARD_Y, bw, BOARD_H), label,
           getattr(palette, color_name))


def _board(s, r, label, col):
  pygame.draw.rect(s, palette.WHITE, r)
  pygame.draw.rect(s, col, (r.x, r.y, r.w, BOARD_TOP_STRIPE))
  pygame.draw.rect(s, col, (r.x, r.bottom - BOARD_BOTTOM_STRIPE, r.w,
                            BOARD_BOTTOM_STRIPE))
  pygame.draw.line(s, palette.STRUCT_DARK, (r.x, r.y), (r.x, r.bottom))
  img = pixelfont.render(label, 1, col)
  s.blit(img, img.get_rect(center=(r.centerx,
                                   r.centery + BOARD_TEXT_DROP)))


def _pitch(s, rng):
  """Grass with stripes that open to the front, and chalk lines."""
  _grass(s)
  for _ in range(GRASS_BLADES):
    s.set_at((rng.randrange(NW),
              rng.randrange(GRASS_TOP + BLADES_BELOW, NH)),
             palette.GRASS_DARK)
  far, near = GRASS_TOP + FAR_LINE, NH - NEAR_LINE
  _chalk_lines(s, far, near)
  for side in (0, 1):
    _penalty_area(s, side, far + AREA_TOP, near - AREA_BOTTOM)


def _chalk_lines(s, far, near):
  _hline(s, palette.LINE, far)
  _hline(s, palette.LINE, near)
  pygame.draw.line(s, palette.LINE, (NW // 2, far), (NW // 2, near))
  left, y, w, h = CENTER_CIRCLE
  pygame.draw.ellipse(s, palette.LINE, (NW // 2 - left, y, w, h), 1)
  left, y, w, h = CENTER_SPOT
  s.fill(palette.LINE, (NW // 2 - left, y, w, h))


def _grass(s):
  for y in range(GRASS_TOP, NH):
    t = (y - GRASS_TOP) / (NH - GRASS_TOP)
    stripe_w = STRIPE_FAR + STRIPE_GROWTH * t
    for x in range(NW):
      k = int((x - NW / 2) / stripe_w + STRIPE_OFFSET)
      s.set_at((x, y), palette.GRASS_A if k % 2 == 0
               else palette.GRASS_B)


def _penalty_area(s, side, top, bottom):
  def edge(x):
    return x if side == 0 else NW - x
  box = [(edge(0), top), (edge(AREA_FAR_W), top),
         (edge(AREA_NEAR_W), bottom), (edge(0), bottom)]
  pygame.draw.lines(s, palette.LINE, False, box, 1)


def build_background():
  """The whole stadium (or assets/backgrounds/stadium.png if present)."""
  custom = assets.load_override_image("backgrounds", "stadium.png")
  if custom is not None:
    return pygame.transform.scale(custom, (W, H)).convert()
  big = retro.scale_px(_paint_stadium())
  _crowd_band(big)          # OPTIMIZADO: the stands at final resolution
  return big.convert()


def _paint_stadium():
  """Sky, roof, stands, boards and pitch at the native resolution."""
  rng = random.Random(STADIUM_SEED)
  s = pygame.Surface((NW, NH))
  _dither_band(s, 0, SKY_BOTTOM_Y, palette.SKY_TOP, palette.SKY_BOTTOM)
  for x, y, w in CLOUDS:
    _cloud(s, x, y, w)
  _roof(s)
  _stands(s, rng)
  _boards(s)
  _pitch(s, rng)
  return s


def _crowd_band(screen):
  """Stands at one pixel per pixel (the animated crowd covers them in FULL).

    The whole background is drawn at 640 x 360 and scaled x2, so its people
    end up as 2 x 2 blocks in OPTIMIZADO. This band keeps the same geometry
    as `k_tribuna` at the final size, so both modes show the same crowd.
    """
  height = CROWD_BOTTOM - CROWD_TOP
  band = pygame.Surface((W, height))
  rng = random.Random(STADIUM_SEED)
  rows = height // CROWD_SEAT[1]
  for row in range(rows):
    _band_row(band, rng, row, rows)
  _band_stairs(band)
  screen.blit(band, (0, CROWD_TOP))


def _band_row(band, rng, row, rows):
  """Floor, step and people of one row of the full resolution stands."""
  top = row * CROWD_SEAT[1]
  edge = top + CROWD_SEAT[1] - CROWD_STEP
  shade = _band_shade(row, rows)
  band.fill(_tone(CROWD_TREAD, shade), (0, top, W, CROWD_SEAT[1]))
  band.fill(_tone(CROWD_EDGE, shade), (0, edge, W, CROWD_STEP_RIM))
  band.fill(_tone(CROWD_RISER, shade), (0, edge + CROWD_STEP_RIM, W,
                                       CROWD_STEP - CROWD_STEP_RIM))
  _band_people(band, rng, row, edge, shade)


def _band_people(band, rng, row, edge, shade):
  """The people of a row: one seat of the grid each, some of them empty."""
  seat_w = CROWD_SEAT[0]
  shift = (row % 2) * (seat_w // 2)
  for seat in range(-1, W // seat_w + 1):
    if rng.random() < CROWD_FILL:
      _band_person(band, rng, seat * seat_w - shift, edge, shade)


def _band_person(band, rng, x, edge, shade):
  """Torso with shoulders and a head with hair, at the final size."""
  body_w, body_h = CROWD_BODY
  left = x + (CROWD_SEAT[0] - body_w) // 2
  shirt = _tone(CROWD_SHIRTS[0 if x < W // 2 else 1], shade * _vary(rng))
  band.fill(shirt, (left, edge - body_h, body_w, body_h))
  band.fill(_darker(shirt, CROWD_SHOULDER_SHADE),
            (left + 1, edge - body_h, body_w - 2, CROWD_SHOULDER_EDGE))
  _band_head(band, rng, left + body_w // 2, edge - body_h - CROWD_HEAD, shade)


def _band_head(band, rng, cx, cy, shade):
  """Dark rim, face and hair of one person."""
  r = int(CROWD_HEAD)
  pygame.draw.circle(band, _tone(CROWD_OUTLINE_COLOUR, shade), (cx, cy), r)
  pygame.draw.circle(band, _tone(rng.choice(CROWD_SKINS), shade), (cx, cy),
                     r - 1)
  pygame.draw.circle(band, _tone(rng.choice(CROWD_HAIRS), shade),
                     (cx, cy - CROWD_HAIR_DROP), r - 1)
  pygame.draw.circle(band, _tone(CROWD_SKINS[0], shade), (cx, cy + 1),
                     r - CROWD_FACE_INSET)


def _band_stairs(band):
  """Dark aisles of the stands, at the same x as the scaled background."""
  for x in range(STAIRS_X0 * PX, W, STAIRS_EVERY * PX):
    band.fill(palette.SEAT_DEEP, (x, 0, STAIRS_W * PX, band.get_height()))
    for y in range(0, band.get_height(), STEP_H * PX):
      band.fill(palette.SEAT_DARK, (x, y, STAIRS_W * PX, PX))


def _band_shade(row, rows):
  """Darkness of a row: the ones up there are further away."""
  far = row / (rows - 1)
  return CROWD_SHADE_TOP + (CROWD_SHADE_BOTTOM - CROWD_SHADE_TOP) * far


def _vary(rng):
  """Brightness of one shirt (the hash does this in the kernel)."""
  return CROWD_VAR_MIN + CROWD_VAR_RANGE * rng.random()


def _tone(rgb, factor):
  """Colour of the crowd (0-1 floats) times a brightness, as a byte rgb."""
  return tuple(_clip(channel * factor * BYTE_MAX) for channel in rgb)


def _darker(rgb, factor):
  """Byte rgb darkened by `factor` (0-1)."""
  return tuple(_clip(channel * factor) for channel in rgb)


def _clip(value):
  """Byte channel of a 0-255 float (rounded and clipped)."""
  return min(palette.MAX_CHANNEL, int(value + 0.5))



# ---------------------------------------------------------------------------
# Goals (drawn every frame: their height changes with the powers)
# ---------------------------------------------------------------------------
def goal_bar_y(height):
  """y of the crossbar centre for a goal of that height."""
  return FLOOR - height - HALF_BAR


def _goal_x(side):
  depth = config.Arena.GOAL_DEPTH
  mouth = depth if side == 0 else W - depth
  x0, x1 = (0, mouth) if side == 0 else (mouth, W)
  return mouth, x0, x1


def draw_goal_back(surf, side, height):
  """Net, back post and owner flag (behind players and ball)."""
  _, x0, x1 = _goal_x(side)
  top = int(goal_bar_y(height) - HALF_BAR)
  top -= top % PX
  surf.blit(_net(x1 - x0, FLOOR - top), (x0, top))
  sh = retro.dither_ellipse((x1 - x0) // PX, GOAL_SHADOW_H,
                            alpha=GOAL_SHADOW_ALPHA)
  surf.blit(retro.scale_px(sh), (x0, FLOOR - GOAL_SHADOW_RAISE))
  px = POST_INSET if side == 0 else W - POST_INSET - POST_W
  pygame.draw.rect(surf, palette.INK,
                   (px - PX, top, POST_W + 2 * PX, FLOOR - top))
  pygame.draw.rect(surf, palette.WHITE, (px, top, POST_W, FLOOR - top))
  _flag(surf, side, top)


def _net(w, h):
  net = pygame.Surface((w, h), pygame.SRCALPHA)
  net.fill(NET_FILL)
  for gx in range(0, w, NET_CELL):
    net.fill(NET_LINE_COLOR, (gx, 0, PX, h))
  for gy in range(0, h, NET_CELL):
    net.fill(NET_LINE_COLOR, (0, gy, w, PX))
  return net


def _flag(surf, side, top):
  """Little flag with the colour of the goal owner."""
  fx = FLAG_INSET if side == 0 else W - FLAG_INSET
  fy = top - FLAG_POLE_H
  pygame.draw.rect(surf, palette.INK, (fx - PX, fy, 2 * PX, top - fy))
  d = 1 if side == 0 else -1
  pts = [(fx, fy), (fx + d * FLAG_W, fy + FLAG_H // 2), (fx, fy + FLAG_H)]
  pygame.draw.polygon(surf, config.PLAYER_COLORS[side], pts)
  pygame.draw.polygon(surf, palette.INK, pts, PX)


def draw_goal_front(surf, side, height, highlight=None):
  """Crossbar (in front of everything) with a rounded tip."""
  mouth = _goal_x(side)[0]
  bar = _crossbar(side, height)
  pygame.draw.rect(surf, palette.INK, bar.inflate(2 * PX, 2 * PX),
                   border_radius=BAR_RADIUS)
  pygame.draw.rect(surf, palette.WHITE, bar, border_radius=BAR_INNER_RADIUS)
  pygame.draw.rect(surf, palette.STRUCT_SHADE,
                   (bar.x, bar.bottom - PX, bar.w, PX))
  if highlight:
    _glow(surf, bar, highlight)
  pygame.draw.rect(surf, palette.LINE,
                   (mouth - PX // 2, FLOOR, PX, GOAL_LINE_MARK))


def _crossbar(side, height):
  mouth, x0, x1 = _goal_x(side)
  y = int(goal_bar_y(height))
  t = int(config.Arena.BAR_THICKNESS)
  a, b = (x0, mouth + t // 2) if side == 0 else (mouth - t // 2, x1)
  return pygame.Rect(a, y - t // 2, b - a, t)


def _glow(surf, bar, color):
  glow = pygame.Surface((bar.w + 2 * GLOW_MARGIN, bar.h + 2 * GLOW_MARGIN),
                        pygame.SRCALPHA)
  glow.fill((*color, GLOW_ALPHA))
  surf.blit(glow, (bar.x - GLOW_MARGIN, bar.y - GLOW_MARGIN))


# ---------------------------------------------------------------------------
# Pixel art ball (frames by angle and size)
# ---------------------------------------------------------------------------
def _pentagon(cx, cy, r, rot):
  return [(cx + math.cos(math.radians(rot + k * PENTAGON_STEP)) * r,
           cy + math.sin(math.radians(rot + k * PENTAGON_STEP)) * r)
          for k in range(PENTAGON_SIDES)]


def _round_mask(r):
  mask = art.canvas(r * 2, r * 2)
  art.circle(mask, palette.WHITE, (r, r), r)
  return mask


class BallSprite:
  """Ball frames, cached by diameter and angle (Flyweight)."""
  # px: radius of the ball drawing before it becomes pixel art.
  VECTOR_R = 64

  def __init__(self):
    custom = assets.load_override_image("sprites", "ball.png")
    size = (self.VECTOR_R * 2, self.VECTOR_R * 2)
    self.pattern = (pygame.transform.smoothscale(custom, size)
                    if custom is not None else self._vector_pattern())
    self.frames = {}

  def _vector_pattern(self):
    r = self.VECTOR_R
    s = art.canvas(r * 2, r * 2)
    art.circle(s, BALL_WHITE, (r, r), r)
    art.poly(s, palette.INK, _pentagon(r, r, r * CENTER_PATCH, UP_ANGLE))
    for k in range(PENTAGON_SIDES):
      rot = UP_ANGLE + PATCH_OFFSET + k * PENTAGON_STEP
      a = math.radians(rot)
      art.poly(s, palette.INK, _pentagon(
          r + math.cos(a) * r * PATCH_DISTANCE,
          r + math.sin(a) * r * PATCH_DISTANCE,
          r * PATCH_SIZE, rot + PATCH_FLIP))
    art.clip(s, _round_mask(r))
    return s

  def frame(self, radius, angle):
    """Ball image for that radius (px) and angle (degrees)."""
    d = max(MIN_BALL_PX, int(round(radius * 2 / PX)))   # native diameter
    abucket = int(angle // ANGLE_STEP) % ANGLE_BUCKETS
    key = (d, abucket)
    img = self.frames.get(key)
    if img is None:
      img = self._draw_frame(d, abucket)
      self.frames[key] = img
    return img

  def _draw_frame(self, d, abucket):
    r = self.VECTOR_R
    rot = pygame.transform.rotozoom(self.pattern, abucket * ANGLE_STEP,
                                    1.0)
    cx, cy = rot.get_width() / 2, rot.get_height() / 2
    crop = rot.subsurface(pygame.Rect(round(cx - r), round(cy - r),
                                      2 * r, 2 * r)).copy()
    crop.blit(self._shade(r), (0, 0))
    shine_x, shine_y = SHINE_AT
    art.circle(crop, BALL_SHINE, (r * shine_x, r * shine_y), r * SHINE_R)
    native = retro.outline_native(retro.pixelize(crop, d), palette.INK, 1)
    return retro.scale_px(native)

  def _shade(self, r):
    """Fixed shading (it does not turn with the ball)."""
    shade = art.canvas(2 * r, 2 * r)
    shade_x, shade_y = SHADE_AT
    art.circle(shade, BALL_SHADE, (r + r * shade_x, r + r * shade_y),
               r * SHADE_R)
    return art.clip(shade, _round_mask(r))

  def draw(self, surf, x, y, r, angle):
    """Draws the ball centred at (x, y)."""
    img = self.frame(r, angle)
    surf.blit(img, img.get_rect(center=(round(x), round(y))))


_shadows = {}


def draw_shadow(surf, x, width, height_above, alpha=SHADOW_ALPHA):
  """Dithered shadow; it shrinks and fades with height."""
  k = max(SHADOW_MIN_SCALE, 1 - height_above / SHADOW_FADE_HEIGHT)
  w = max(SHADOW_MIN_W, int(width * k / PX))
  h = max(2, int(w * SHADOW_FLATNESS))
  a = min(palette.MAX_CHANNEL, int(alpha * k * SHADOW_BOOST))
  key = (w, h, a // SHADOW_ALPHA_STEP)
  img = _shadows.get(key)
  if img is None:
    img = retro.scale_px(retro.dither_ellipse(w, h, alpha=a))
    _shadows[key] = img
  surf.blit(img, (round(x - img.get_width() / 2),
                  FLOOR - img.get_height() // 2 + SHADOW_DROP))
