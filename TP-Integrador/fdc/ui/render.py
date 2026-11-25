"""Drawing of the match from the LAST state received from the simulation.

The interface does not compute positions, goals or effects: it only decides
how they look (boot angle, head hop, particles, texts). Retro style: 2x2
pixels, pixel art font, LED scoreboard.

Measures in px of the logical screen; the ones marked "x scale" are
multiplied by the player size (powers make it bigger or smaller).
"""
import collections
import math

import pygame

from fdc import config
from fdc import protocol
from fdc.gpu import effects_state
from fdc.ui import assets
from fdc.ui import characters
from fdc.ui import icons
from fdc.ui import layout
from fdc.ui import palette
from fdc.ui import pixelfont
from fdc.ui import retro
from fdc.ui import sprites
from fdc.ui import stadium

PX = retro.PX
# s: margin so that 3.0000001 s shows as 0:03 and not 0:04.
CLOCK_EPSILON = 1e-6
SECONDS_PER_MINUTE = 60            # to show the clock as minutes:seconds

# --- kick: the boot winds up, sweeps forward, stays up and comes back
# (shares of the kick).
KICK_WINDUP_END = 0.15             # end of the wind-up
KICK_SWING_END = 0.45              # end of the sweep
KICK_SWING_TIME = 0.30             # length of the sweep (from 0.15 to 0.45)
KICK_HOLD_END = 0.70               # end of the leg up
KICK_RETURN_TIME = 0.30            # length of the return (from 0.70 to 1)
KICK_WINDUP_ANGLE = 25             # degrees backwards when winding up
KICK_SWING_ARC = 125               # degrees of the sweep (from +25 to -100)
KICK_FORWARD_ANGLE = -100          # degrees forward at the top

# --- small bar of remaining time
TIMER_BAR_H = 6                    # px: total height
TIMER_BAR_BORDER = 2               # px: dark border around the empty part

# --- player
TRAIL_LENGTH = 6                   # recent ball positions that make the trail
BALL_SHADOW_SCALE = 2.4            # the ball shadow is 2.4 times its radius
PLAYER_SHADOW_W = 84               # px x scale: width of the player shadow
PLAYER_SHADOW_ALPHA = 110          # opacity of the player shadow
AIR_UP_ANGLE = -30                 # degrees of the boot while rising...
AIR_DOWN_ANGLE = 10                # ...and while falling
WALK_MIN_SPEED = 25                # px/s: slower than this, the player is idle
STRIDE_PX = 14.0                   # px walked per radian of the step
WALK_SWING = 22                    # degrees the boot swings when walking
# The head hops at the ends of the step (|cos| greater than this).
WALK_BOB_AT = 0.8
# "No kick" sign: white square with a red cross next to the boot.
NO_KICK_BEHIND = 8                 # px behind the player
NO_KICK_HEIGHT = 14                # px above the feet
NO_KICK_SIZE = 16                  # px: side of the sign
NO_KICK_BORDER = 2                 # px: dark border
NO_KICK_CROSS = (8, 4)             # cross: (length, thickness) in px
# Speed lines behind a fast player.
SPEED_LINES_MIN = 60               # px/s: slower than this they are not drawn
SPEED_LINE_HEIGHTS = (24, 50, 76)  # px x scale above the feet
SPEED_LINE_BEHIND = 44             # px x scale behind the player centre
SPEED_LINE_STAGGER = 6             # px x scale each line shifts from the last
SPEED_LINE_LEN = 18                # px: length of a line...
SPEED_LINE_WOBBLE = 8              # ...that stretches up to 8 px
SPEED_LINE_HZ = 20                 # rhythm of that stretching (rad/s)
# Spring below a player with super jump.
SPRING_W = 70                      # px x scale
SPRING_H = 14                      # px
SPRING_DROP = 2                    # px below the floor
SPRING_LINE = 4                    # px: thickness
# Arc that shows the reach of the kick.
KICK_ARC_FROM = 0.12               # seen from this share of the kick...
KICK_ARC_TO = 0.75                 # ...up to this one
KICK_ARC_GROW = 0.4                # share of the kick when the arc is open
KICK_ARC_HEIGHT = 20               # px x scale: arc centre above the feet
# The arc reaches the kick reach plus 60 % of the boot radius.
KICK_ARC_REACH_SHARE = 0.6
KICK_ARC_DOTS = 7                  # dots of the arc
KICK_ARC_START = -10               # degrees of the first dot
KICK_ARC_SPAN = 110                # degrees of the open arc
# Dots grow towards the tip: one art pixel every 1.5 dots.
KICK_ARC_GROWTH = 3
# Small arrow over the head (player colour) and active effects.
INDICATOR_GAP = 12                 # px between the head and the arrow
# Dark triangle (relative to the arrow tip), px.
ARROW_OUTER = ((-12, -16), (12, -16), (0, 2))
ARROW_INNER = ((-8, -14), (8, -14), (0, -2))    # colour triangle, px
LAST_TOUCH_BALL_R = 10             # px: radius of the "last touch" ball
LAST_TOUCH_BALL_AT = (16, -8)      # where that ball goes from the arrow (px)
MINI_EFFECT_STEP = 30              # px between effect icons over the head
MINI_EFFECT_RAISE = 40             # px above the arrow
MINI_ICON = 32                     # px: icon of an active effect
MINI_TIMER_GAP = 2                 # px between the icon and its timer
MIN_DURATION = 0.001               # s: avoids dividing by zero in timers
# Ice block of a frozen player.
ICE_FILL = (170, 225, 255, 120)    # translucent light blue
ICE_FACET = (210, 240, 255, 90)    # flat translucent facets
ICE_EDGE = (240, 250, 255, 230)    # white border of the block
ICE_EDGE_LINE = 3                  # px: thickness of the inner border
ICE_INK_LINE = 2                   # px: thickness of the outer outline
ICE_TOP_SHARE = 1 / 3              # width share of the upper facet
ICE_BOTTOM_SHARE = 1 / 4           # width share of the lower facet
ICE_FROST_COUNT = 5                # teeth along the base
ICE_TEXT_GAP = 4                   # px: gap from the block to its timer
ICE_STREAKS = 3                    # diagonal reflections
ICE_STREAK_FIRST = 0.2             # the first one at 20 % of the width...
ICE_STREAK_STEP = 0.25             # ...and the others every 25 %
ICE_STREAK_STEPS = 6               # steps of each reflection
ICE_STREAK_TOP = 10                # px from the top of the block
ICE_STREAK_COLOR = (255, 255, 255, 200)   # almost opaque white
# Burnt player (the fire power: the ball burns whoever touches it).
BURN_TINT = (190, 150, 130)        # rgb multiplier: the body looks charred
BURN_PROP = "burned"               # property of the burn in the effects
WORLD_TIMERS = (effects_state.ICE_PROP, BURN_PROP)
BURN_FLAME_SINK = 2                # px below the feet where the flames end
BURN_TEXT_GAP = 4                  # px between the flame and the seconds
EFFECT_INDICATOR_GAP = 26          # px: keep the arrow above the timer
# Ball.
TRAIL_SPEED = 560                  # px/s: faster than this the ball trails
TRAIL_MIN_SHARE = 0.4              # the oldest trail is 40 % of the radius...
TRAIL_EXTRA_SHARE = 0.6            # ...and the newest one 40 % + 60 %
TRAIL_ALPHA = 70                   # opacity of the oldest trail...
TRAIL_ALPHA_STEP = 20              # ...that rises by 20 towards the ball
BALL_RING_GAP = 6                  # px between the ball and its power ring
EFFECT_RING_LINE = 2               # px: thickness of the colour rings
# Power object on the pitch.
PICKUP_BOB_HZ = 3.2                # rhythm of its floating (rad/s)
PICKUP_BLINK_TIME = 1.5            # s: in its last seconds it blinks...
PICKUP_BLINK_HZ = 8                # ...with this rhythm
PICKUP_RING_GAP = 6                # px between the icon and its ring
PICKUP_ICON_SCALE = 2.3            # px of icon per px of pickup radius
PICKUP_PULSE_TIME = 0.8            # s of the bright pulse when it appears
PICKUP_PULSE_FLOOR = 0.3           # soft breathing after that (0-1)
PICKUP_PULSE_HZ = 4.0              # rad/s of that breathing
PICKUP_LABEL_GAP = 14              # px between the object and its name
LABEL_SCALE = 2                    # pixel font scale of the pitch labels
# Bomb.
BOMB_BLINK_HZ = 8                  # blink of the fuse at the start...
BOMB_BLINK_EXTRA = 16              # ...that speeds up to 8 + 16 at the end
BLAST_DOTS = 40                    # dots of the circle of the blast reach
BLAST_DOTS_HZ = 10                 # the dots twinkle alternately (per second)
BLAST_DOT = 4                      # px: side of each dot
BOMB_R = 20                        # px: radius of the bomb
BOMB_CORE_R = 16                   # px: radius of the blinking core
BOMB_SHINE = (-8, -8, 4, 4)        # shine (from the centre: x, y, w, h)
BOMB_FUSE = (6, -22, 6, 8)         # fuse (same fields)
BOMB_SPARK = (10, -28, 6, 6)       # spark of the fuse (same fields)
BOMB_SPARK_ON = (255, 220, 90)     # lit spark (off: orange)
BOMB_LABEL_GAP = 30                # px above the centre: seconds left

# --- top scoreboard
BOARD = (500, 92)                  # (width, height) in px
BOARD_TOP = 4                      # px from the top of the screen
BOARD_INSET = 8                    # px between the frame and the LED screen
PLATE = (56, 60)                   # box with each player face (w, h) in px
PLATE_INSET = 6                    # px from the side of the LED screen
PLATE_LINE = 2                     # px: border of the box
SCORE_LED_SCALE = 7                # size of the LED dots of the goals
SCORE_X = 118                      # px each side of the centre for goals
SCORE_RAISE = 4                    # px above the centre
CLOCK_WARNING = 10                 # s: in the last seconds the clock blinks...
CLOCK_BLINK_HZ = 4                 # ...with this rhythm
CLOCK_LED_SCALE = 6                # size of the LED dots of the clock
CLOCK_RAISE = 6                    # px above the centre
STATE_TEXT_COLOR = (180, 190, 200)  # light grey: the match state text
STATE_TEXT_BOTTOM = 10             # px from the bottom of the LED screen
NAME_GAP = 12                      # px between the board and the name signs
NAME_TOP = 8                       # px from the top of the board
NAME_PAD = (14, 10)                # px each name sign grows (width, height)
HUD_EFFECT = (210, 40)             # box of an active effect (w, h) in px
HUD_EFFECTS_TOP = 46               # first effect of a player, from board top
HUD_EFFECT_STEP = 46               # px between effects
HUD_ICON = 32                      # px: icon of the effect
HUD_ICON_INSET = 4                 # px from the box corner
HUD_TEXT_X = 40                    # who it affects, from the left edge (px)
HUD_TEXT_Y = 4                     # texts, from the top of the box (px)
HUD_TIME_MARGIN = 4                # seconds left, from the right edge (px)
HUD_TIMER_BOTTOM = 10              # timer, from the bottom of the box (px)
CENTER_EFFECTS_GAP = 12            # px between board and ball/match effects
NOTE_PADDING = 20                  # pause request note: px added to text...
NOTE_H = 26                        # ...height...
NOTE_GAP = 10                      # ...px below the board...
NOTE_BOTTOM_GAP = 8                # ...and px to what comes below
# Name of the match state on the LED board, by phase.
STATE_TEXTS = {protocol.PHASE_COUNTDOWN: "PREPARADOS",
               protocol.PHASE_PLAYING: "EN JUEGO",
               protocol.PHASE_GOAL: "GOL", protocol.PHASE_FINISHED: "FINAL"}
LEFT_TARGETS = ("p0", "goal0")     # effects shown on the left column
RIGHT_TARGETS = ("p1", "goal1")    # effects shown on the right column

# --- signs at the centre
COUNTDOWN_Y = 330                  # countdown numbers and the go sign (px)
# The number starts 32 points bigger and shrinks within the second.
COUNTDOWN_GROWTH = 32
FONT_STEP = 8                      # font sizes go by 8 (an integer scale)
GOLDEN_Y = 186                     # golden goal sign (px)
GOLDEN_NOTE_Y = 240                # note below it: next goal wins (px)
GOAL_BAND_TOP = 262                # goal band: top edge...
GOAL_BAND_H = 132                  # ...and height (px)
GOAL_BAND_BORDER = 6               # px: dark border top and bottom
GOAL_STRIPE = 6                    # px: stripes with the scorer colour
GOAL_WOBBLE_PX = 4                 # the goal text hops 4 px...
GOAL_WOBBLE_HZ = 8                 # ...with this rhythm
GOAL_TEXT_Y = 312                  # goal text (px)
GOAL_SCORER_Y = 368                # name of the scorer (px)


def fmt_clock(secs):
  """Clock text m:ss for that many seconds left."""
  secs = max(0, int(math.ceil(secs - CLOCK_EPSILON)))
  return (f"{secs // SECONDS_PER_MINUTE:01d}:"
          f"{secs % SECONDS_PER_MINUTE:02d}")


def kick_angle(prog):
  """Boot angle during the kick (0 = rest; negative = forward)."""
  if prog < KICK_WINDUP_END:
    return KICK_WINDUP_ANGLE * prog / KICK_WINDUP_END
  if prog < KICK_SWING_END:
    return (KICK_WINDUP_ANGLE
            - KICK_SWING_ARC * (prog - KICK_WINDUP_END) / KICK_SWING_TIME)
  if prog < KICK_HOLD_END:
    return KICK_FORWARD_ANGLE
  return (KICK_FORWARD_ANGLE
          - KICK_FORWARD_ANGLE * (prog - KICK_HOLD_END) / KICK_RETURN_TIME)


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def timer_bar(surf, x, y, w, frac, color):
  """Retro bar of remaining time."""
  b = TIMER_BAR_BORDER
  pygame.draw.rect(surf, palette.INK, (x, y, w, TIMER_BAR_H))
  pygame.draw.rect(surf, palette.CREAM_DARK,
                   (x + b, y + b, w - 2 * b, TIMER_BAR_H - 2 * b))
  fill = int((w - 2 * b) * max(0.0, min(1.0, frac)))
  if fill > 0:
    pygame.draw.rect(surf, color, (x + b, y + b, fill, TIMER_BAR_H - 2 * b))


def snap(v):
  """Takes a coordinate to the grid of art pixels."""
  return int(v) // PX * PX


def _around(x, y, rect):
  """Rectangle (dx, dy, width, height) relative to the point (x, y)."""
  dx, dy, w, h = rect
  return x + dx, y + dy, w, h


def _power_color(power_id):
  return config.CATEGORY_COLORS[config.POWERS_BY_ID[power_id].category]


def _effect_frac(e):
  return e["left"] / max(MIN_DURATION, e["dur"])


def _column(target):
  """HUD column of an effect: 0 (left), 1 (right) or "c" (centre)."""
  if target in LEFT_TARGETS:
    return 0
  return 1 if target in RIGHT_TARGETS else "c"


def _walk_pose(stride):
  """(boot angle, head hop) while walking."""
  ph = stride / STRIDE_PX
  return (WALK_SWING * math.sin(ph),
          (-1 if abs(math.cos(ph)) > WALK_BOB_AT else 0))


def _draw_no_kick(surf, bx, by):
  """No kick sign: white square with a border and a red cross, centred
    at (bx, by)."""
  half = NO_KICK_SIZE // 2
  inner = half - NO_KICK_BORDER
  length, thick = NO_KICK_CROSS
  pygame.draw.rect(surf, palette.INK,
                   (bx - half, by - half, NO_KICK_SIZE, NO_KICK_SIZE))
  pygame.draw.rect(surf, palette.WHITE,
                   (bx - inner, by - inner, 2 * inner, 2 * inner))
  pygame.draw.rect(surf, palette.RED,
                   (bx - length // 2, by - thick // 2, length, thick))
  pygame.draw.rect(surf, palette.RED,
                   (bx - thick // 2, by - length // 2, thick, length))


def _draw_ice(surf, p, effect):
  x0, y0, x1, y1 = effects_state.ice_box(p, effect)
  if y1 <= y0 or x1 <= x0:
    return
  ice = pygame.Surface((x1 - x0, y1 - y0), pygame.SRCALPHA)
  _ice_shell(ice)
  surf.blit(ice, (x0, y0))
  if effect:
    _effect_time(surf, ice.get_rect(topleft=(x0, y0)), effect["left"],
                 ICE_TEXT_GAP)


def _ice_shell(ice):
  outer = ice.get_rect()
  edge = _inset(outer, ICE_INK_LINE)
  fill = _inset(edge, ICE_EDGE_LINE)
  _ice_layer(ice, outer, palette.INK)
  _ice_layer(ice, edge, ICE_EDGE)
  _ice_layer(ice, fill, ICE_FILL)
  if fill.height > ICE_STREAK_TOP + ICE_STREAK_STEPS * 2 * PX:
    _ice_facets(ice, fill)
    _ice_streaks(ice, fill)
    _ice_frost(ice, fill)


def _inset(rect, margin):
  delta = -margin * 2
  return rect.inflate(delta, delta)


def _ice_layer(ice, rect, colour):
  if rect.width <= 0 or rect.height <= 0:
    return
  x, y = rect.topleft
  right, bottom = rect.right - 1, rect.bottom - 1
  bevel = min(PX, rect.width // 2, rect.height // 2)
  pygame.draw.polygon(ice, colour, (
      (x + bevel, y), (right - bevel, y), (right, y + bevel),
      (right, bottom - bevel), (right - bevel, bottom),
      (x + bevel, bottom), (x, bottom - bevel), (x, y + bevel)))


def _ice_facets(ice, rect):
  x, y = rect.topleft
  right, bottom = rect.right - 1, rect.bottom - 1
  top = min(rect.height - 1, snap(rect.width * ICE_TOP_SHARE))
  low = min(rect.height - 1, snap(rect.width * ICE_BOTTOM_SHARE))
  pygame.draw.polygon(ice, ICE_FACET, (
      (x + PX, y + PX), (x + top, y + PX), (x + PX, y + top)))
  pygame.draw.polygon(ice, ICE_FACET, (
      (right - PX, bottom - PX), (right - low, bottom - PX),
      (right - PX, bottom - low)))


def _ice_streaks(ice, rect):
  ice.set_clip(rect)
  for k in range(ICE_STREAKS):
    share = ICE_STREAK_FIRST + ICE_STREAK_STEP * k
    x = rect.left + snap(rect.width * share)
    for j in range(ICE_STREAK_STEPS):
      y = rect.top + ICE_STREAK_TOP + j * 2 * PX
      ice.fill(ICE_STREAK_COLOR, (x - j * PX, y, PX, 2 * PX))
  ice.set_clip(None)


def _ice_frost(ice, rect):
  y = rect.bottom - 1
  for index in range(ICE_FROST_COUNT):
    x = rect.left + (index + 1) * rect.width // (ICE_FROST_COUNT + 1)
    pygame.draw.polygon(ice, ICE_EDGE,
                        ((x - PX, y), (x, y - 2 * PX), (x + PX, y)))


def _burnt(img):
  """Copy of the sprite of a burnt player: charred, without glow."""
  dark = img.copy()
  dark.fill(BURN_TINT, special_flags=pygame.BLEND_RGB_MULT)
  return dark


def _effect_time(surf, bounds, seconds, gap):
  label = _label(f"{max(0.0, seconds):.1f}s")
  surf.blit(label, label.get_rect(
      midbottom=(bounds.centerx, bounds.top - gap)))


def _flame_layers(p, time):
  frame = int(time * icons.FLAME_FPS) % icons.FLAME_FRAMES
  back, front = icons.flame_crown(frame, p["scale"])
  rect = back.get_rect(midbottom=(p["x"], p["y"] + BURN_FLAME_SINK))
  return back, front, rect


def _draw_kick_arc(surf, p, f):
  """Visible reach of the kick: an arc of white pixels."""
  s = p["scale"]
  cx, cy = p["x"], p["y"] - KICK_ARC_HEIGHT * s
  spec = config.PlayerSpec
  reach = (spec.KICK_REACH_X + spec.KICK_RADIUS * KICK_ARC_REACH_SHARE) * s
  prog = min(1.0, (p["kick"] - KICK_ARC_FROM) / KICK_ARC_GROW)
  for k in range(KICK_ARC_DOTS):
    a = math.radians(KICK_ARC_START
                     + KICK_ARC_SPAN * prog * k / (KICK_ARC_DOTS - 1))
    x = cx + math.sin(a) * reach * f
    y = cy + math.cos(a) * reach
    sz = PX + (k * 2) // KICK_ARC_GROWTH * PX
    surf.fill(palette.WHITE, (snap(x) - sz // 2, snap(y) - sz // 2, sz, sz))


def _draw_speed_lines(surf, p, col, t):
  s = p["scale"]
  d = -1 if p["vx"] > 0 else 1
  for k, hh in enumerate(SPEED_LINE_HEIGHTS):
    x0 = p["x"] + d * (SPEED_LINE_BEHIND + k * SPEED_LINE_STAGGER) * s
    ln = snap(SPEED_LINE_LEN
              + SPEED_LINE_WOBBLE * math.sin(t * SPEED_LINE_HZ + k))
    pygame.draw.rect(surf, col, (min(x0, x0 + d * ln), p["y"] - hh * s,
                                 ln, 2 * PX))


def _draw_spring(surf, p, col):
  r = pygame.Rect(0, 0, int(SPRING_W * p["scale"]), SPRING_H)
  r.center = (p["x"], stadium.FLOOR + SPRING_DROP)
  pygame.draw.ellipse(surf, col, r, SPRING_LINE)


def effect_icon(effect, size):
  """Icon of an effect: the flame of a burn, the badge of its power."""
  if effect.get("prop") == BURN_PROP:
    return icons.flame()
  return icons.power_icon(effect["power"], size)


def effect_color(effect):
  """Colour of an effect: fire orange for a burn, its category otherwise."""
  if effect.get("prop") == BURN_PROP:
    return palette.ORANGE
  return _power_color(effect["power"])


def _draw_mini_effect(surf, e, center):
  icon = icons.power_icon(e["power"], MINI_ICON)
  r = icon.get_rect(center=(round(center[0]), round(center[1])))
  surf.blit(icon, r)
  timer_bar(surf, r.left, r.bottom + MINI_TIMER_GAP, r.width,
            _effect_frac(e), _power_color(e["power"]))


def _draw_blast_ring(surf, x, y, t):
  """Twinkling red dots on the reach of the explosion."""
  reach = config.PowerRules.BOMB_BLAST_RADIUS
  n = BLAST_DOTS
  for k in range(n):
    if (k + int(t * BLAST_DOTS_HZ)) % 2:
      a = 2 * math.pi * k / n
      surf.fill(palette.RED, (snap(x + math.cos(a) * reach),
                              snap(y + math.sin(a) * reach),
                              BLAST_DOT, BLAST_DOT))


def _draw_bomb_body(surf, x, y, on):
  pygame.draw.circle(surf, palette.INK, (x, y), BOMB_R)
  pygame.draw.circle(surf, palette.RED if on else palette.INK, (x, y),
                     BOMB_CORE_R)
  surf.fill(palette.WHITE, _around(x, y, BOMB_SHINE))
  pygame.draw.rect(surf, palette.INK, _around(x, y, BOMB_FUSE))
  surf.fill(BOMB_SPARK_ON if on else palette.ORANGE,
            _around(x, y, BOMB_SPARK))


def _draw_pickup_icon(surf, power_id, x, y, col, pulse=0.0):
  r = config.PowerRules.PICKUP_RADIUS
  pygame.draw.circle(surf, col, (x, y), r + PICKUP_RING_GAP,
                     EFFECT_RING_LINE)
  icon = icons.power_icon(power_id, int(r * PICKUP_ICON_SCALE), pulse)
  surf.blit(icon, icon.get_rect(center=(x, y)))


def _pickup_pulse(pk, t):
  """Brightness of the pickup icon: a pulse at birth, then a soft breath."""
  age = pk["ttl_max"] - pk["ttl"]
  born = max(0.0, 1.0 - age / PICKUP_PULSE_TIME)
  soft = PICKUP_PULSE_FLOOR * (0.5 + 0.5 * math.sin(t * PICKUP_PULSE_HZ))
  return max(born, soft)


def _draw_score(surf, led_area, i, score):
  img = pixelfont.render_led(str(score), SCORE_LED_SCALE, palette.LED_ON,
                             palette.LED_OFF)
  sx = led_area.centerx - SCORE_X if i == 0 else led_area.centerx + SCORE_X
  surf.blit(img, img.get_rect(center=(sx, led_area.centery - SCORE_RAISE)))


def _draw_time_left(surf, inner, e, col):
  """Seconds left of an effect and its timer bar."""
  assets.draw_text(surf, f"{max(0.0, e['left']):.1f}s", layout.FONT_SMALL,
                   (inner.right - HUD_TIME_MARGIN, inner.top + HUD_TEXT_Y),
                   col, anchor="topright", outline=palette.INK)
  timer_bar(surf, inner.left + HUD_TEXT_X, inner.bottom - HUD_TIMER_BOTTOM,
            inner.width - HUD_TEXT_X - HUD_TIME_MARGIN, _effect_frac(e), col)


def _draw_golden_sign(surf):
  _title(surf, "¡GOL DE ORO!", layout.FONT_BANNER,
         (layout.CENTER_X, GOLDEN_Y), palette.GOLD)
  assets.draw_text(surf, "Empate: el próximo gol gana", layout.FONT_TEXT,
                   (layout.CENTER_X, GOLDEN_NOTE_Y), palette.INK,
                   outline=palette.WHITE)


def _draw_goal_band(surf, col):
  """Cream band with stripes of the scorer colour."""
  width = layout.SCREEN_W
  band = pygame.Rect(0, GOAL_BAND_TOP, width, GOAL_BAND_H)
  pygame.draw.rect(surf, palette.INK, band)
  pygame.draw.rect(surf, palette.CREAM,
                   band.inflate(0, -GOAL_BAND_BORDER - GOAL_BAND_BORDER))
  pygame.draw.rect(surf, col, (0, band.top + GOAL_BAND_BORDER, width,
                               GOAL_STRIPE))
  pygame.draw.rect(surf, col, (0, band.bottom - GOAL_BAND_BORDER
                               - GOAL_STRIPE, width, GOAL_STRIPE))


def _label(text):
  return pixelfont.render(text, LABEL_SCALE, palette.WHITE,
                          outline=palette.INK)


def _title(surf, text, size, pos, color):
  assets.draw_text(surf, text, size, pos, color, kind="title",
                   outline=palette.INK, shadow=True)


class MatchRenderer:
  """Draws the world, the scoreboard and the centre signs."""

  def __init__(self, app, chars):
    self.app = app
    self.sprites = app.sprites
    self.ball_sprite = app.ball_sprite
    self.background = app.background
    self.chars = list(chars)
    self.t = 0.0
    self.trail = collections.deque(maxlen=TRAIL_LENGTH)
    self.kickoff_flash = 0.0
    self.goal_banner = None      # (time left, goal data)
    self.golden_flash = 0.0
    # Small text below the scoreboard (online: a pause was requested).
    self.center_note = None

  def who(self, i, side_if_same=True):
    """Character name (side and colour already tell the players apart).
        If both chose the same one, the side is added."""
    name = characters.short_name(
        characters.CHARACTERS_BY_ID[self.chars[i]])
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

  # ------------------------------------------------------------ world
  def draw_world(self, surf, st, offset=(0, 0)):
    surf.blit(self.background, offset)
    self.app.postfx.draw_crowd(surf)
    goals = st["goals"]
    for side in (0, 1):
      stadium.draw_goal_back(surf, side, goals[side])
    self._objects(surf, st)
    self._shadows(surf, st)
    for i in sorted(range(2), key=lambda k: st["players"][k]["y"]):
      self._player(surf, i, st["players"][i], st)
    self._ball(surf, st["ball"], st)
    for side in (0, 1):
      stadium.draw_goal_front(surf, side, goals[side],
                              self._goal_highlight(st, side))

  def _objects(self, surf, st):
    """Bombs and the power object on the pitch."""
    for b in st.get("bombs", []):
      self._bomb(surf, b)
    if st.get("pickup"):
      self._pickup(surf, st["pickup"])

  def _shadows(self, surf, st):
    ball = st["ball"]
    stadium.draw_shadow(surf, ball["x"], ball["r"] * BALL_SHADOW_SCALE,
                        stadium.FLOOR - ball["y"] - ball["r"])
    for p in st["players"]:
      stadium.draw_shadow(surf, p["x"], PLAYER_SHADOW_W * p["scale"],
                          stadium.FLOOR - p["y"], PLAYER_SHADOW_ALPHA)

  def _goal_highlight(self, st, side):
    """Colour of the last power acting on that goal (or None)."""
    hl = None
    for e in st.get("effects", []):
      if e["target"] == f"goal{side}":
        hl = _power_color(e["power"])
    return hl

  def pose(self, i, p, phase):
    """(boot angle, head hop in native px)."""
    if p["frozen"]:
      return 0, 0
    celebrating = phase in (protocol.PHASE_GOAL, protocol.PHASE_FINISHED)
    if p["celebrate"] and celebrating:
      return sprites.celebrate_pose(self.t)
    if p["kick"] >= 0:
      return kick_angle(p["kick"]), 0
    if not p["ground"]:
      return (AIR_UP_ANGLE, 0) if p["vy"] < 0 else (AIR_DOWN_ANGLE, 0)
    if abs(p["vx"]) > WALK_MIN_SPEED:
      return _walk_pose(p["stride"])
    return sprites.idle_pose(self.t, i)

  def _player_image(self, i, p, st):
    """Sprite of the player, charred if it is burnt."""
    f = 1 if p["facing"] >= 0 else -1
    ang, bob = self.pose(i, p, st["phase"])
    img, (fx, fy) = self.sprites.player(
        self.chars[i], f, ang, bob, config.PLAYER_COLORS[i], p["frozen"],
        p["scale"])
    if p.get("burned"):
      img = _burnt(img)
    return img, (fx, fy), f

  def _player(self, surf, i, p, st):
    f = self._player_body(surf, i, p, st)
    mine = [e for e in st.get("effects", []) if e["target"] == f"p{i}"]
    self._player_effects(surf, p, f, mine)
    if KICK_ARC_FROM <= p["kick"] <= KICK_ARC_TO:
      _draw_kick_arc(surf, p, f)
    self._over_head(surf, i, p, mine, st.get("last_touch") == i)

  def _player_body(self, surf, i, p, st):
    img, (fx, fy), facing = self._player_image(i, p, st)
    pos = (round(p["x"] - fx), round(p["y"] - fy))
    if not p.get("burned"):
      surf.blit(img, pos)
      return facing
    back, front, rect = _flame_layers(p, self.t)
    surf.blit(back, rect)
    surf.blit(img, pos)
    surf.blit(front, rect)
    _effect_time(surf, rect, p.get("burned_left", 0.0), BURN_TEXT_GAP)
    return facing

  def _over_head(self, surf, i, p, mine, last):
    """Arrow of the player and its active effects over the head."""
    spec = config.PlayerSpec
    top = (p["y"] - (spec.HEAD_OFFSET_Y + spec.HEAD_RADIUS) * p["scale"]
           - INDICATOR_GAP)
    if p.get("frozen") or p.get("burned"):
      top = min(top, effects_state.ice_box(p)[1] - EFFECT_INDICATOR_GAP)
    self._indicator(surf, p["x"], top, i, last)
    marks = [e for e in mine if e.get("prop") not in WORLD_TIMERS]
    for k, e in enumerate(marks):
      cx = p["x"] + (k - (len(marks) - 1) / 2) * MINI_EFFECT_STEP
      _draw_mini_effect(surf, e, (cx, top - MINI_EFFECT_RAISE))

  def _player_effects(self, surf, p, f, mine):
    """Ice, no kick sign, speed lines and spring of a player."""
    props = {config.POWERS_BY_ID[e["power"]].prop: e for e in mine}
    if p["frozen"]:
      _draw_ice(surf, p, props.get(effects_state.ICE_PROP))
    if "no_kick" in props:
      _draw_no_kick(surf, snap(p["x"] - f * NO_KICK_BEHIND),
                    int(p["y"] - NO_KICK_HEIGHT))
    if "speed" in props and abs(p["vx"]) > SPEED_LINES_MIN:
      _draw_speed_lines(surf, p, _power_color(props["speed"]["power"]),
                        self.t)
    if "jump" in props:
      _draw_spring(surf, p, _power_color(props["jump"]["power"]))

  def _indicator(self, surf, x, y, i, last):
    col = config.PLAYER_COLORS[i]
    x = snap(x)
    pygame.draw.polygon(surf, palette.INK,
                        [(x + dx, y + dy) for dx, dy in ARROW_OUTER])
    pygame.draw.polygon(surf, col,
                        [(x + dx, y + dy) for dx, dy in ARROW_INNER])
    if last:                       # last touch: small ball by the arrow
      ball = self.ball_sprite.frame(LAST_TOUCH_BALL_R, 0)
      dx, dy = LAST_TOUCH_BALL_AT
      surf.blit(ball, ball.get_rect(midleft=(x + dx, y + dy)))

  def _ball(self, surf, ball, st):
    sp = math.hypot(ball["vx"], ball["vy"])
    self.trail.append((ball["x"], ball["y"], ball["r"]))
    if sp > TRAIL_SPEED:
      self._trail(surf)
    for e in st.get("effects", []):
      if e["target"] == "ball":
        pygame.draw.circle(surf, _power_color(e["power"]),
                           (int(ball["x"]), int(ball["y"])),
                           int(ball["r"] + BALL_RING_GAP),
                           EFFECT_RING_LINE)
    self.ball_sprite.draw(surf, ball["x"], ball["y"], ball["r"],
                          ball["angle"])

  def _trail(self, surf):
    pts = list(self.trail)[:-1]
    for k, (x, y, r) in enumerate(pts):
      share = TRAIL_MIN_SHARE + TRAIL_EXTRA_SHARE * k / max(1, len(pts))
      sz = max(PX, snap(r * share))
      layer = pygame.Surface((sz, sz), pygame.SRCALPHA)
      layer.fill((*palette.WHITE, TRAIL_ALPHA + TRAIL_ALPHA_STEP * k))
      surf.blit(layer, (int(x - sz / 2), int(y - sz / 2)))

  def _pickup(self, surf, pk):
    pdef = config.POWERS_BY_ID[pk["power"]]
    col = config.CATEGORY_COLORS[pdef.category]
    bob = PX * round(math.sin(self.t * PICKUP_BOB_HZ))
    x, y = int(pk["x"]), int(pk["y"] + bob)
    r = config.PowerRules.PICKUP_RADIUS
    if not self._pickup_blinks(pk):
      _draw_pickup_icon(surf, pk["power"], x, y, col,
                        _pickup_pulse(pk, self.t))
    timer_bar(surf, x - r, y + r + PICKUP_RING_GAP, 2 * r,
              pk["ttl"] / pk["ttl_max"], col)
    lab = _label(pdef.label)
    surf.blit(lab, lab.get_rect(midtop=(x, y + r + PICKUP_LABEL_GAP)))

  def _pickup_blinks(self, pk):
    """True on the frames the pickup hides (it is about to expire)."""
    return (pk["ttl"] < PICKUP_BLINK_TIME
            and int(self.t * PICKUP_BLINK_HZ) % 2 == 0)

  def _bomb(self, surf, b):
    x, y = int(b["x"]), int(b["y"])
    frac = b["fuse"] / b["fuse_max"]
    hz = BOMB_BLINK_HZ + BOMB_BLINK_EXTRA * (1 - frac)
    on = int(self.t * hz) % 2 == 0
    _draw_blast_ring(surf, x, y, self.t)
    _draw_bomb_body(surf, x, y, on)
    lab = _label(f"{b['fuse']:.1f}")
    surf.blit(lab, lab.get_rect(midbottom=(x, y - BOMB_LABEL_GAP)))

  # ------------------------------------------------------------ HUD
  def draw_hud(self, surf, st):
    board = pygame.Rect((0, 0), BOARD)
    board.midtop = (layout.CENTER_X, BOARD_TOP)
    led_area = self._board(surf, board)
    for i in (0, 1):
      self._plate(surf, led_area, i, st["score"][i])
    if st["clock"] is not None:
      self._clock(surf, led_area, st)
    self._state_label(surf, led_area, st)
    for i in (0, 1):
      self._name_sign(surf, board, i)
    self._effects(surf, board, st)

  def _board(self, surf, board):
    """Frame of the scoreboard; returns its LED area."""
    pygame.draw.rect(surf, palette.INK,
                     board.move(layout.SHADOW_OFFSET, layout.SHADOW_OFFSET))
    pygame.draw.rect(surf, palette.STRUCT_DARK, board)
    pygame.draw.rect(surf, palette.INK, board, layout.FRAME_LINE)
    shrink = -BOARD_INSET - BOARD_INSET
    led_area = board.inflate(shrink, shrink)
    pygame.draw.rect(surf, palette.LED_BG, led_area)
    return led_area

  def _plate(self, surf, led_area, i, score):
    """Face of player i on its colour and its goals in LED."""
    head = self.sprites.mini_head(self.chars[i], 1, 1 if i == 0 else -1)
    plate = pygame.Rect((0, 0), PLATE)
    if i == 0:
      plate.midleft = (led_area.left + PLATE_INSET, led_area.centery)
    else:
      plate.midright = (led_area.right - PLATE_INSET, led_area.centery)
    pygame.draw.rect(surf, config.PLAYER_COLORS[i], plate)
    pygame.draw.rect(surf, palette.INK, plate, PLATE_LINE)
    surf.blit(head, head.get_rect(center=plate.center))
    _draw_score(surf, led_area, i, score)

  def _clock(self, surf, led_area, st):
    low = (st["clock"] <= CLOCK_WARNING
           and st["phase"] == protocol.PHASE_PLAYING
           and int(self.t * CLOCK_BLINK_HZ) % 2 == 0)
    golden = st.get("golden")
    text = "ORO" if golden else fmt_clock(st["clock"])
    color = palette.LED_ON_2 if (low or golden) else palette.LED_ON
    clock = pixelfont.render_led(text, CLOCK_LED_SCALE, color,
                                 palette.LED_OFF)
    surf.blit(clock, clock.get_rect(
        center=(led_area.centerx, led_area.centery - CLOCK_RAISE)))

  def _state_label(self, surf, led_area, st):
    state_txt = STATE_TEXTS[st["phase"]]
    if st.get("golden") and st["phase"] in (protocol.PHASE_PLAYING,
                                            protocol.PHASE_COUNTDOWN):
      state_txt = "GOL DE ORO"
    if st["paused"]:
      state_txt = "EN PAUSA"
    lab = retro.scale_px(pixelfont.render(state_txt, 1, STATE_TEXT_COLOR))
    surf.blit(lab, lab.get_rect(
        center=(led_area.centerx, led_area.bottom - STATE_TEXT_BOTTOM)))

  def _name_sign(self, surf, board, i):
    ch = characters.CHARACTERS_BY_ID[self.chars[i]]
    name = _label(characters.short_name(ch).upper())
    r = name.get_rect()
    if i == 0:
      r.topright = (board.left - NAME_GAP, board.top + NAME_TOP)
    else:
      r.topleft = (board.right + NAME_GAP, board.top + NAME_TOP)
    retro.bevel_box(surf, r.inflate(*NAME_PAD), config.PLAYER_COLORS[i])
    surf.blit(name, r)

  def _effects(self, surf, board, st):
    """Active effects: P1 on the left, P2 on the right, ball and match
        in the centre."""
    cols = {0: [], 1: [], "c": []}
    for e in st.get("effects", []):
      cols[_column(e["target"])].append(e)
    effect_w = HUD_EFFECT[0]
    self._side_column(surf, board, cols[0],
                      board.left - NAME_GAP - effect_w)
    self._side_column(surf, board, cols[1], board.right + NAME_GAP)
    top = board.bottom + CENTER_EFFECTS_GAP
    if self.center_note:
      top = self._note(surf, board)
    for k, e in enumerate(cols["c"]):
      self._hud_effect(surf, e, (board.centerx - effect_w // 2,
                                 top + k * HUD_EFFECT_STEP))

  def _side_column(self, surf, board, effects, x):
    for k, e in enumerate(effects):
      y = board.top + HUD_EFFECTS_TOP + k * HUD_EFFECT_STEP
      self._hud_effect(surf, e, (x, y))

  def _note(self, surf, board):
    """Small note below the board; returns the y below it."""
    width = (pixelfont.text_width(self.center_note, LABEL_SCALE)
             + NOTE_PADDING)
    note = pygame.Rect(0, 0, width, NOTE_H)
    note.midtop = (board.centerx, board.bottom + NOTE_GAP)
    inner = retro.bevel_box(surf, note, palette.CREAM, shadow=False)
    assets.draw_text(surf, self.center_note, layout.FONT_SMALL,
                     inner.center, palette.INK, outline=None)
    return note.bottom + NOTE_BOTTOM_GAP

  def _hud_effect(self, surf, e, topleft):
    inner = retro.bevel_box(surf, pygame.Rect(topleft, HUD_EFFECT),
                            palette.CREAM)
    icon = effect_icon(e, HUD_ICON)
    surf.blit(icon, (inner.left + HUD_ICON_INSET,
                     inner.top + HUD_ICON_INSET))
    assets.draw_text(surf, self._target_label(e["target"]),
                     layout.FONT_SMALL,
                     (inner.left + HUD_TEXT_X, inner.top + HUD_TEXT_Y),
                     palette.INK, anchor="topleft", outline=None)
    _draw_time_left(surf, inner, e, effect_color(e))

  def _target_label(self, target):
    if target == "ball":
      return "PELOTA"
    if target.startswith("goal"):
      return "ARCO"
    return self.who(int(target[1]), side_if_same=False).upper()

  # ------------------------------------------------------------ signs
  def draw_center_messages(self, surf, st):
    """Countdown, go sign, golden goal and goal."""
    if st["phase"] == protocol.PHASE_COUNTDOWN and not st["paused"]:
      self._countdown(surf, st["phase_left"])
    if self.kickoff_flash > 0:
      _title(surf, "¡YA!", layout.FONT_GO,
             (layout.CENTER_X, COUNTDOWN_Y), palette.WHITE)
    if self.golden_flash > 0:
      _draw_golden_sign(surf)
    if self.goal_banner:
      self._goal_band(surf, self.goal_banner[1])

  def _countdown(self, surf, phase_left):
    n = max(1, math.ceil(phase_left))
    frac = phase_left - math.floor(phase_left)
    size = (layout.FONT_COUNTDOWN
            + int(COUNTDOWN_GROWTH * frac) // FONT_STEP * FONT_STEP)
    _title(surf, str(n), size, (layout.CENTER_X, COUNTDOWN_Y),
           palette.GOLD)

  def _goal_band(self, surf, g):
    col = config.PLAYER_COLORS[g["scorer"]]
    _draw_goal_band(surf, col)
    wob = GOAL_WOBBLE_PX if int(self.t * GOAL_WOBBLE_HZ) % 2 else 0
    _title(surf, "¡GOOOL!", layout.FONT_GOAL,
           (layout.CENTER_X, GOAL_TEXT_Y - wob), col)
    sub = self.who(g["scorer"])
    if g.get("own_goal"):
      sub += "  (en contra)"
    assets.draw_text(surf, sub, layout.FONT_TEXT,
                     (layout.CENTER_X, GOAL_SCORER_Y), palette.INK,
                     outline=None)
