"""Power icons: a badge with the colour of its category plus a pictogram.

Green = helps the receiver, red = harms it, purple = global. Powers that
act on the rival also carry a small target. If assets/icons/<id>.png
exists, that image is used.

Pictograms are drawn in "icon units": the centre is (0, 0) and 1 is the
radius of the pictogram (y grows downwards). So each shape below is a list
of points that does not depend on the final icon size. Stroke widths are
in those units too.
"""
import math

import pygame

from fdc import config
from fdc.ui import art
from fdc.ui import assets
from fdc.ui import palette
from fdc.ui import retro

WHITE = (255, 255, 255)            # pictograms
# Badge outline (darker than palette.INK: it is seen small).
INK = (26, 24, 40)
SOFT_WHITE = (255, 255, 255, 150)  # secondary strokes (net of the goal)
_cache = {}

# --- badge
VECTOR_SIZE = 128                  # px: drawn big, then turned to pixel art
MIN_ICON_PX = 8                    # native px: minimum pixelated icon size
BADGE_R = 0.46                     # badge radius (share of the icon side)
BADGE_GLOW = 1.0                   # bright halo around the badge (radius)
BADGE_GLOW_LIGHT = 0.55            # how much white the halo has
BADGE_RIM = 0.86                   # white ring (share of the badge radius)
BADGE_FACE = 0.72                  # circle with the category colour (same)
BADGE_SHADE = 0.35                 # the bottom of the face is this darker
BADGE_LIFT = 0.10                  # px the lit part rises (share of radius)
BADGE_FACE_LIT = 0.62              # radius of the lit part (same)
GLYPH_SCALE = 0.62                 # radius of the pictogram (same)
# --- pulse: the icon shines when the power appears (projector)
PULSE_STEPS = 5                    # brightness levels kept in the cache
PULSE_ADD = 45                     # white added to the icon (0-255)
PULSE_RING = 4                     # px of the bright ring
PULSE_RING_AT = 1.02               # ring radius (share of the badge radius)
WHITE_ALPHA = 255                  # opaque white of the ring
# --- flame of the fire power (crisp pixels, without glow)
# Bitmap of the flame, one character per art pixel: o = body, y = heart,
# w = bright centre, . = transparent. It is outlined and scaled xPX.
FLAME_ART = (
    ".....o....",
    "....oo....",
    "....ooo...",
    "...oooo...",
    "...ooooo..",
    "..oooooo..",
    "..oooyoo..",
    ".ooyyyyoo.",
    ".ooywwyoo.",
    "..oyyyyo..",
    "..oooooo..",
    "...oooo...",
    "....oo....",
)
FLAME_COLORS = {"o": palette.ORANGE, "y": palette.GOLD,
                "w": palette.CREAM}
FLAME_OUTLINE_PX = 1               # px of dark outline around the flame

# Target of the powers that affect the rival (bottom right).
TARGET_AT = 0.62                   # offset from the centre (share of radius)
TARGET_OUTER = 0.32                # dark circle
TARGET_INNER = 0.24                # white circle
TARGET_SCALE = 0.2                 # radius of the target
TARGET_RED = (200, 40, 40)         # colour of the target
TARGET_RING_R = 0.62               # ring of the target (target units)
TARGET_RING_W = 0.22               # thickness of the ring
TARGET_CROSS_W = 0.16              # thickness of the cross
TARGETED = ("rival", "rival_goal")  # targets that get the small target

# --- thick arrow
ARROW_SIZE = 0.5                   # default size (from centre to tip)
ARROW_TAIL = 0.6                   # the tail is 0.6 sizes behind the centre
ARROW_NECK = 0.05                  # where the shaft ends and the head starts
ARROW_HEAD_W = 0.5                 # half base of the head (in sizes)
ARROW_SHAFT_W = 0.2                # shaft thickness for an ARROW_SIZE arrow
# --- ball
PENTAGON_SIDES = 5                 # centre patch of the ball: pentagon...
PENTAGON_STEP = 72                 # ...with a vertex every 72 degrees...
UP_ANGLE = -90                     # ...starting upwards
BALL_PATCH = 0.38                  # patch radius (share of the ball radius)
BALL_SEAM_END = 0.95               # the seams go from the patch to here
BALL_SEAM_W = 0.07                 # thickness of the seams
# --- goal
GOAL_FRAME_W = 0.16                # thickness of posts and crossbar
GOAL_NET_COLUMNS = 4               # the net has 4 columns
GOAL_NET_W = 0.05                  # thickness of the threads
# --- person (grow and shrink): everything times its size
PERSON_HEAD_Y = -0.35              # head: height of the centre...
PERSON_HEAD_R = 0.32               # ...and radius
# Body (trapeze), icon units.
PERSON_BODY = ((-0.3, 0.55), (-0.24, 0.02), (0.24, 0.02), (0.3, 0.55))
# --- injured boot
# Silhouette of the boot, icon units.
BOOT = ((-0.55, -0.55), (-0.1, -0.55), (-0.08, 0.05), (0.55, 0.12),
        (0.65, 0.42), (-0.6, 0.42))
# Red cross over it, icon units.
BOOT_CROSS = (((-0.45, -0.35), (0.05, 0.2)), ((0.05, -0.35), (-0.45, 0.2)))
BOOT_CROSS_COLOR = (230, 60, 60)   # red of the cross
BOOT_CROSS_W = 0.14                # thickness of the cross
BOOT_SOLE = ((-0.6, 0.5), (0.66, 0.5))   # sole, icon units
BOOT_SOLE_W = 0.08                 # thickness of the sole
# --- snowflake (freeze)
SNOW_ARMS = 3                      # three crossed bars = six arms
SNOW_FIRST = 90                    # degrees of the first bar (vertical)
SNOW_ARM_STEP = 60                 # degrees between bars
SNOW_ARM = 0.72                    # length of each arm
SNOW_ARM_W = 0.13                  # thickness of the arms
SNOW_BRANCH_AT = 0.6               # the branches start at 60 % of the arm...
SNOW_BRANCH_ANGLE = 45             # ...at 45 degrees...
SNOW_BRANCH = 0.25                 # ...with this length...
SNOW_BRANCH_W = 0.09               # ...and this thickness
SNOW_CORE = 0.14                   # centre circle
# --- bolt (more speed) and motion lines
# Silhouette of the bolt, icon units.
BOLT = ((0.12, -0.78), (-0.42, 0.08), (-0.04, 0.08), (-0.2, 0.78),
        (0.44, -0.16), (0.04, -0.16), (0.24, -0.78))
# Little lines on the left, icon units.
SPEED_LINES = (((-0.75, -0.3), (-0.5, -0.3)), ((-0.8, 0.1), (-0.52, 0.1)))
SPEED_LINE_W = 0.08                # thickness of those lines
# --- snail (less speed)
# Body of the snail, icon units.
SNAIL_BODY = ((-0.7, 0.45), (0.6, 0.45), (0.72, 0.3), (0.55, 0.2),
              (-0.6, 0.25))
SNAIL_HEAD = (0.62, 0.12, 0.13)    # head (x, y, radius)
# Antennae, icon units.
SNAIL_ANTENNAS = (((0.6, 0.05), (0.66, -0.3)), ((0.7, 0.08), (0.84, -0.22)))
SNAIL_ANTENNA_W = 0.06             # thickness of the antennae
SNAIL_SHELL = (-0.1, -0.08, 0.46)  # shell (x, y, radius)
SPIRAL_POINTS = 40                 # points of the spiral of the shell
SPIRAL_ANGLE = 4.2                 # the spiral turns 4.2 pi (two turns+)
SPIRAL_R = 0.38                    # outer radius of the spiral...
SPIRAL_SHRINK = 0.85               # ...that closes down to 15 %
SPIRAL_LIGHTEN = 0.2               # the spiral is a bit lighter than ink
SPIRAL_W = 0.06                    # thickness of the spiral
# --- spring (super jump)
SPRING_ZIGZAGS = 6                 # segments of the zigzag
SPRING_HALF_W = 0.3                # half width
SPRING_W = 0.1                     # thickness
SPRING_TOP, SPRING_BOTTOM = 0.2, 0.7   # the spring goes from y = 0.2 to 0.7
# --- bomb
BOMB_BODY = (-0.08, 0.14, 0.56)    # bomb (x, y, radius)...
BOMB_CORE_R = 0.46                 # ...and its dark part
BOMB_SHINE = (-0.26, -0.04, 0.12)  # shine (x, y, radius)
BOMB_SHINE_COLOR = (255, 255, 255, 140)   # translucent white shine
# Cap of the fuse, icon units.
BOMB_CAP = ((0.18, -0.4), (0.38, -0.2), (0.28, -0.1), (0.08, -0.3))
# Fuse: curve (start, control, end), icon units.
BOMB_FUSE = ((0.3, -0.3), (0.45, -0.62), (0.62, -0.55))
BOMB_FUSE_STEPS = 10               # segments of that curve
BOMB_FUSE_W = 0.08                 # thickness of the fuse
SPARK_CENTER = (0.66, -0.6)        # spark at the tip of the fuse
SPARK_RAYS = 6                     # rays of the spark...
SPARK_RAY_STEP = 60                # ...one every 60 degrees...
SPARK_RAY_TURN = 15                # ...turned 15 degrees
SPARK_RAY = (0.06, 0.2)            # each ray goes from this distance to this
SPARK_RAY_W = 0.06                 # thickness of the rays
SPARK_COLOR = (255, 220, 90)       # yellow
# --- bounces (high and low bounce)
BOUNCE_GROUND = 0.5                # height of the floor of the bounces
# Height of the first bounce (high bounce / low bounce), icon units.
BOUNCE_HEIGHT = {True: 0.75, False: 0.22}
# Bounces: (start x, end x, relative height) for high and low bounce.
BOUNCE_ARCS = {True: ((-0.85, -0.25, 1.0), (-0.25, 0.25, 0.8),
                      (0.25, 0.65, 0.6)),
               False: ((-0.85, -0.25, 1.0), (-0.25, 0.25, 0.6),
                       (0.25, 0.65, 0.3))}
BOUNCE_STEPS = 12                  # segments of each curve
BOUNCE_TRAIL = (255, 255, 255, 200)  # colour of the trail of the bounces
BOUNCE_TRAIL_W = 0.07              # thickness of the trail
BOUNCE_FLOOR = ((-0.9, 0.62), (0.9, 0.62))   # floor, icon units
BOUNCE_FLOOR_W = 0.08              # thickness of the floor
BOUNCE_BALL_X = 0.65               # small ball at the end of the bounces...
BOUNCE_BALL_LIFT = 0.22            # ...resting on the floor...
BOUNCE_BALL_R = 0.2                # ...with this radius
# --- pictograms made of the pieces above
JUMP_ARROW_UP = (0, -0.25)         # more jump: arrow up over the spring
JUMP_ARROW_DOWN = (0, -0.05)       # less jump: arrow down...
JUMP_FLOOR = ((-0.6, 0.62), (0.6, 0.62))   # ...against the floor
JUMP_FLOOR_W = 0.14                # thickness of that floor
BIG_GOAL = (-0.12, 0.2, 0.5, 0.42)  # big goal (x, y, half width, half h)
SMALL_GOAL = (-0.12, 0.32, 0.36, 0.28)   # small goal (same fields)
GOAL_ARROW_X = 0.55                # arrow next to the goal...
BIG_GOAL_ARROW_Y = -0.35           # ...up high (grow)...
SMALL_GOAL_ARROW_Y = -0.2          # ...or a bit lower (shrink)
GOAL_ARROW_SIZE = 0.35             # size of that arrow
GROW_PERSON = (0, 0.08, 0.95)      # big person (x, y, size)
SHRINK_PERSON = (0, 0.2, 0.6)      # small person (x, y, size)
SIZE_ARROWS = ((-1, -1), (1, -1))  # small diagonal arrows up left and right
SIZE_ARROW_AT = 0.6                # distance of those arrows to the centre
SHRINK_ARROW_Y = 0.55              # when shrinking they go a bit lower
DIAGONAL = 0.707                   # component of a diagonal (about 1/sqrt 2)
SIZE_ARROW_SIZE = 0.22             # size of the small arrows
BIG_BALL = (-0.12, 0.1, 0.58)      # big ball (x, y, radius)
SMALL_BALL = (-0.1, 0.2, 0.34)     # small ball (x, y, radius)
# Plus sign of the big ball, icon units.
PLUS_SIGN = (((0.5, -0.62), (0.5, -0.18)), ((0.28, -0.4), (0.72, -0.4)))
MINUS_SIGN = (((0.3, -0.4), (0.72, -0.4)),)   # minus of the small ball
SIGN_W = 0.13                      # thickness of the plus and minus
# F3 powers: a bulb turned off, two opposite arrows and a flame.
BULB_BODY = (0.0, -0.08, 0.28)     # x, y and radius of the bulb
# Socket of the bulb (trapezoid below it).
BULB_BASE = ((-0.15, 0.2), (0.15, 0.2), (0.11, 0.36), (-0.11, 0.36))
BULB_RAY = (0.42, 0.54)            # from and to (radius) of the rays
BULB_RAYS = 6                      # rays around the bulb
BULB_RAY_W = 0.07                  # thickness of those rays
SLASH = ((-0.42, 0.42), (0.42, -0.42))   # crossed out ("off")
SLASH_W = 0.12                     # thickness of that line
CONFUSION_RING = 0.4               # radius of the turning ring
CONFUSION_RING_W = 0.12            # thickness of the ring
CONFUSION_ARROW = 0.22             # size of the two arrows
CONFUSION_HEAD = 0.44              # where the arrows start (x)
CONFUSION_UP, CONFUSION_DOWN = -0.06, 0.06   # y of the two arrows
FULL_TURN = 360.0                  # degrees of a full circle
# Outline of the flame.
FLAME_OUTER = ((0.0, -0.5), (0.25, -0.08), (0.18, 0.24), (0.0, 0.44),
               (-0.18, 0.24), (-0.25, -0.08))
# Dark tongue inside the flame.
FLAME_INNER = ((0.0, -0.1), (0.11, 0.1), (0.0, 0.3), (-0.11, 0.1))
# Small white core at the bottom of that tongue.
FLAME_CORE = ((0.0, 0.06), (0.05, 0.16), (0.0, 0.26), (-0.05, 0.16))


class Glyph:
  """Pen that draws in icon units around a centre (cx, cy)."""

  def __init__(self, surf, cx, cy, r):
    self.s, self.cx, self.cy, self.r = surf, cx, cy, r

  def p(self, x, y):
    """Pixel position of the point (x, y) in icon units."""
    return self.cx + x * self.r, self.cy + y * self.r

  def pts(self, lst):
    return [self.p(x, y) for x, y in lst]

  def poly(self, color, lst):
    art.poly(self.s, color, self.pts(lst))

  def line(self, color, lst, w):
    art.thick_polyline(self.s, color, self.pts(lst), w * self.r)

  def lines(self, color, segments, w):
    for seg in segments:
      self.line(color, list(seg), w)

  def circle(self, color, x, y, rr):
    art.circle(self.s, color, self.p(x, y), rr * self.r)

  def ring(self, color, x, y, rr, w):
    pygame.draw.circle(self.s, color, [round(v) for v in self.p(x, y)],
                       round(rr * self.r), max(1, round(w * self.r)))


def _arrow(g, x, y, direction, size=ARROW_SIZE, color=WHITE):
  """Thick arrow; direction = unit (dx, dy)."""
  dx, dy = direction
  px, py = -dy, dx
  tip = (x + dx * size, y + dy * size)
  base = (x - dx * size * ARROW_TAIL, y - dy * size * ARROW_TAIL)
  neck = (x + dx * size * ARROW_NECK, y + dy * size * ARROW_NECK)
  g.line(color, [base, neck], ARROW_SHAFT_W * size / ARROW_SIZE)
  head = size * ARROW_HEAD_W
  g.poly(color, [tip, (neck[0] + px * head, neck[1] + py * head),
                 (neck[0] - px * head, neck[1] - py * head)])


def _ball(g, x, y, r):
  g.circle(WHITE, x, y, r)
  g.circle(INK, x, y, r * BALL_PATCH)
  for k in range(PENTAGON_SIDES):
    a = math.radians(UP_ANGLE + k * PENTAGON_STEP)
    g.line(INK, [_polar(x, y, a, r * BALL_PATCH),
                 _polar(x, y, a, r * BALL_SEAM_END)], BALL_SEAM_W)


def _polar(x, y, a, d):
  """Point at distance d from (x, y) in the direction a (radians)."""
  return x + math.cos(a) * d, y + math.sin(a) * d


def _goal(g, x, y, w, h):
  g.line(WHITE, [(x - w, y + h), (x - w, y - h), (x + w, y - h),
                 (x + w, y + h)], GOAL_FRAME_W)
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
      _snow_branches(g, a, dx * sgn, dy * sgn, sgn)
  g.circle(WHITE, 0, 0, SNOW_CORE)


def _snow_branches(g, a, ex, ey, sgn):
  mx, my = ex * SNOW_BRANCH_AT, ey * SNOW_BRANCH_AT
  for t in (1, -1):
    b = a + t * math.radians(SNOW_BRANCH_ANGLE)
    g.line(WHITE, [(mx, my), (mx + math.cos(b) * SNOW_BRANCH * sgn,
                              my + math.sin(b) * SNOW_BRANCH * sgn)],
           SNOW_BRANCH_W)


def _bolt(g):
  g.poly(WHITE, BOLT)


def _snail(g):
  g.poly(WHITE, SNAIL_BODY)
  g.circle(WHITE, *SNAIL_HEAD)
  g.lines(WHITE, SNAIL_ANTENNAS, SNAIL_ANTENNA_W)
  g.circle(WHITE, *SNAIL_SHELL)
  g.line(art.shade(INK, SPIRAL_LIGHTEN), _spiral(), SPIRAL_W)


def _spiral():
  sx, sy, _ = SNAIL_SHELL
  pts = []
  for i in range(SPIRAL_POINTS):
    t = i / (SPIRAL_POINTS - 1)
    a = t * SPIRAL_ANGLE * math.pi
    rr = SPIRAL_R * (1 - t * SPIRAL_SHRINK)
    pts.append((sx + math.cos(a) * rr, sy + math.sin(a) * rr))
  return pts


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
    g.line(SPARK_COLOR, [_polar(cx, cy, a, near), _polar(cx, cy, a, far)],
           SPARK_RAY_W)


def _bounces(g, tall):
  h = BOUNCE_HEIGHT[tall]
  ground = BOUNCE_GROUND
  for x0, x1, k in BOUNCE_ARCS[tall]:
    curve = art.bezier((x0, ground), ((x0 + x1) / 2, ground - h * k * 2),
                       (x1, ground), BOUNCE_STEPS)
    g.line(BOUNCE_TRAIL, curve, BOUNCE_TRAIL_W)
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
  for sx, sy in SIZE_ARROWS:                    # small arrows outwards
    _arrow(g, sx * SIZE_ARROW_AT, sy * SIZE_ARROW_AT,
           (sx * DIAGONAL, sy * DIAGONAL), SIZE_ARROW_SIZE)


def _shrink(g):
  _person(g, *SHRINK_PERSON)
  for sx, sy in SIZE_ARROWS:                    # small arrows inwards
    _arrow(g, sx * SIZE_ARROW_AT, sy * SHRINK_ARROW_Y,
           (-sx * DIAGONAL, -sy * DIAGONAL), SIZE_ARROW_SIZE)


def _big_ball(g):
  _ball(g, *BIG_BALL)
  g.lines(WHITE, PLUS_SIGN, SIGN_W)


def _small_ball(g):
  _ball(g, *SMALL_BALL)
  g.lines(WHITE, MINUS_SIGN, SIGN_W)


def _blackout(g):
  """Bulb with its rays and a line across: the lights go out."""
  x, y, r = BULB_BODY
  g.circle(WHITE, x, y, r)
  g.poly(INK, list(BULB_BASE))
  near, far = BULB_RAY
  for k in range(BULB_RAYS):
    a = math.radians(k * FULL_TURN / BULB_RAYS)
    g.line(WHITE, [_polar(x, y, a, near), _polar(x, y, a, far)],
           BULB_RAY_W)
  g.line(INK, list(SLASH), SLASH_W)


def _confusion(g):
  """Two opposite arrows around a ring: everything spins."""
  _arrow(g, -CONFUSION_HEAD, CONFUSION_UP, (0, -1), CONFUSION_ARROW)
  _arrow(g, CONFUSION_HEAD, CONFUSION_DOWN, (0, 1), CONFUSION_ARROW)
  g.ring(WHITE, 0.0, 0.0, CONFUSION_RING, CONFUSION_RING_W)


def _fire(g):
  """Flame: white body with the dark inner tongue."""
  g.poly(WHITE, FLAME_OUTER)
  g.poly(INK, FLAME_INNER)
  g.poly(WHITE, FLAME_CORE)


GLYPHS = {                          # pictogram of each power
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
    "blackout": _blackout,
    "confusion": _confusion,
    "fire": _fire,
}


def _vector_icon(power_id, size):
  pdef = config.POWERS_BY_ID[power_id]
  surf = art.canvas(size, size)
  c = size / 2
  r = size * BADGE_R
  _badge(surf, c, r, config.CATEGORY_COLORS[pdef.category])
  glyph = art.canvas(size, size)
  GLYPHS[power_id](Glyph(glyph, c, c, r * GLYPH_SCALE))
  surf.blit(glyph, (0, 0))
  if pdef.target in TARGETED:
    _target(surf, c + r * TARGET_AT, c + r * TARGET_AT, r)
  return surf


def _badge(surf, c, r, color):
  """Badge with a bright halo, dark outline, white rim and a lit face."""
  art.circle(surf, art.shade(color, BADGE_GLOW_LIGHT), (c, c),
             r * BADGE_GLOW)
  art.circle(surf, INK, (c, c), r)
  art.circle(surf, WHITE, (c, c), r * BADGE_RIM)
  art.circle(surf, art.shade(color, -BADGE_SHADE), (c, c), r * BADGE_FACE)
  art.circle(surf, color, (c, c - r * BADGE_LIFT), r * BADGE_FACE_LIT)


def _target(surf, mx, my, r):
  """Small red target: the power acts on the rival."""
  art.circle(surf, INK, (mx, my), r * TARGET_OUTER)
  art.circle(surf, WHITE, (mx, my), r * TARGET_INNER)
  g = Glyph(surf, mx, my, r * TARGET_SCALE)
  g.ring(TARGET_RED, 0, 0, TARGET_RING_R, TARGET_RING_W)
  g.line(TARGET_RED, [(-1, 0), (1, 0)], TARGET_CROSS_W)
  g.line(TARGET_RED, [(0, -1), (0, 1)], TARGET_CROSS_W)


def power_icon(power_id, size, pulse=0.0):
  """Pixel art icon: drawn at high resolution and reduced to native
    pixels (size / PX), scaled up without smoothing (Flyweight cache).

    `pulse` (0-1) is the brightness of a power that has just appeared: the
    icon is lightened and gets a bright ring, so it is seen from the back of
    the classroom. Only PULSE_STEPS levels are drawn and cached.
    """
  level = int(round(max(0.0, min(1.0, pulse)) * PULSE_STEPS))
  key = (power_id, size, level)
  if key in _cache:
    return _cache[key]
  icon = _base_icon(power_id, size)
  if level:
    icon = _pulsed(icon, level / PULSE_STEPS)
  _cache[key] = icon
  return icon


def _base_icon(power_id, size):
  """Icon without the pulse: the file of assets/icons or the vector one."""
  custom = assets.load_override_image("icons", f"{power_id}.png")
  if custom is not None:
    return pygame.transform.scale(custom, (size, size))
  native = max(MIN_ICON_PX, size // retro.PX)
  return retro.scale_px(
      retro.pixelize(_vector_icon(power_id, VECTOR_SIZE), native), retro.PX)


def _pulsed(icon, amount):
  """Brighter copy of the icon with a ring: the power pops when it appears."""
  out = icon.copy()
  add = int(PULSE_ADD * amount)
  if add:
    out.fill((add, add, add), special_flags=pygame.BLEND_RGB_ADD)
  side = icon.get_width()
  ring = art.canvas(side, side)
  pygame.draw.circle(ring, (*WHITE, int(WHITE_ALPHA * amount)),
                     (side // 2, side // 2),
                     int(side * BADGE_R * PULSE_RING_AT), PULSE_RING)
  out.blit(ring, (0, 0))
  return out


def flame():
  """Pixel art flame of the fire power: orange with a yellow heart and a
    dark outline, without glow. Drawn once and cached."""
  if "flame" not in _cache:
    bits = _flame_bits()
    _cache["flame"] = retro.scale_px(
        retro.outline_native(bits, palette.INK, FLAME_OUTLINE_PX),
        retro.PX)
  return _cache["flame"]


def _flame_bits():
  """The flame at native resolution (one pixel per art pixel)."""
  width, height = len(FLAME_ART[0]), len(FLAME_ART)
  surf = art.canvas(width, height)
  for y, row in enumerate(FLAME_ART):
    for x, char in enumerate(row):
      if char in FLAME_COLORS:
        surf.set_at((x, y), (*FLAME_COLORS[char], palette.OPAQUE))
  return surf

