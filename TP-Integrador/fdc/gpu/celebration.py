"""Goal celebration: confetti, sign and flash before the replay (F10).

Two pieces, both plain Python so the rules are tested without a window:

  - `Celebration`: the clock of the party. It says how much shake and flash
    the goal deserves, when the next confetti burst is due and whether the
    replay can start. Everything comes from the clock, so the automatic demo
    repeats it frame by frame.
  - `ConfettiField`: the pool of paper bits. It advances with simple
    arithmetic and the `confetti` kernel (or its numpy version) turns the live
    rows into paper on the image: one thread per bit and the only atomics are
    in the splat, like the particles of the course.
"""
import math

import numpy as np

from fdc import config

G = config.Gpu
ARENA = config.Arena
SEED = 20251106         # fixed seed: the confetti looks the same every run
TWO_PI = math.pi * 2.0  # full turn in radians
COL_CHANNELS = 5        # r, g, b, half width and half height of a bit
RGB = 3                 # colour channels (the other two are the sizes)
HW_COLUMN = 3           # column of the half width inside `col`
HH_COLUMN = 4           # column of the half height inside `col`
MIN_LIFE = 0.01         # s: below this a bit is free again
MIN_SIZE = 1.0          # px: a bit is never thinner than this
DIM_SHARE = 0.5         # share of the life in which a bit keeps its colour
# Seconds after the goal of each burst: the party starts with two and keeps
# throwing paper while the sign is on.
BURSTS = (0.0, 0.3, 0.62, 0.95, 1.3, 1.65)
# Where the bursts come from, as a share of the width (the first two always
# open the party; the rest alternate with the goal mouth).
BURST_X = (0.16, 0.84, 0.34, 0.66, 0.5)
# Same for the height: from the sides of the pitch, like cannons, so the
# paper flies over the green and pops (the crowd is already a pixel party
# and hides it).
BURST_Y = (0.78, 0.78, 0.86, 0.86, 0.70)
# Colours of the paper (0-1): white, gold, the two shirts and two more.
COLOURS = ((1.0, 1.0, 1.0), (1.0, 0.85, 0.2), (0.35, 0.75, 1.0),
           (1.0, 0.36, 0.45), (0.45, 1.0, 0.6))
LEFT_SIDE = 0           # side of the left goal in the goal event
RIGHT_SIDE = 1          # side of the right goal in the goal event


class Celebration:
  """The party after a goal, before the replay."""

  def __init__(self, now, goal=None, duration=None):
    self.start = now
    self.goal = goal or {}
    self.duration = max(duration or G.GOAL_CELEBRATION, MIN_LIFE)
    self.fired = 0          # bursts already thrown

  def elapsed(self, now):
    """Seconds since the goal (negative if the clock went back)."""
    return now - self.start

  def progress(self, now):
    """0 at the goal, 1 when the party is over (clamped)."""
    return min(1.0, max(0.0, self.elapsed(now) / self.duration))

  def finished(self, now):
    """True when the replay can start."""
    return self.elapsed(now) >= self.duration

  def due(self, now):
    """How many bursts should have been thrown by `now`."""
    elapsed = self.elapsed(now)
    return sum(1 for delay in BURSTS if delay <= elapsed)

  def due_bursts(self, now):
    """Indexes of the bursts that are due and were not thrown yet."""
    count = self.due(now)
    new = list(range(self.fired, max(self.fired, count)))
    self.fired = max(self.fired, count)
    return new

  def burst_shape(self, index):
    """(x, y) of the burst number `index`."""
    x = BURST_X[index % len(BURST_X)]
    y = BURST_Y[index % len(BURST_Y)]
    if index >= len(BURST_X):      # after the first round: from the goal
      x = self.mouth_x() / ARENA.WIDTH
    return x * ARENA.WIDTH, y * ARENA.HEIGHT

  def mouth_x(self):
    """x of the goal that was scored (the middle of the pitch if none)."""
    side = self.goal.get("side")
    if side == LEFT_SIDE:
      return ARENA.GOAL_DEPTH
    if side == RIGHT_SIDE:
      return ARENA.WIDTH - ARENA.GOAL_DEPTH
    return ARENA.WIDTH / 2.0

  def shake(self, now):
    """0-1 camera shake: strong at the goal, gone in a few frames."""
    left = 1.0 - self.progress(now)
    return left * left

  def flash(self, now):
    """0-1 white flash of the first frames."""
    left = 1.0 - self.elapsed(now) / max(G.CONFETTI_FLASH_TIME, MIN_LIFE)
    return max(0.0, left) * G.CONFETTI_FLASH


class ConfettiField:
  """Pool of paper bits: `burst` adds, `update` moves, `live` reads."""

  def __init__(self, count=None, seed=SEED):
    size = count or G.CONFETTI
    self.count = size
    self.pos = np.zeros((size, 2), np.float32)
    self.vel = np.zeros((size, 2), np.float32)
    self.sway = np.zeros(size, np.float32)   # px/s of the flutter
    self.spin = np.zeros(size, np.float32)   # rad/s of the turn
    self.phase = np.zeros(size, np.float32)  # rad, where the turn is
    self.life = np.zeros(size, np.float32)
    self.total = np.ones(size, np.float32)
    self.col = np.zeros((size, COL_CHANNELS), np.float32)
    self.rng = np.random.default_rng(seed)
    self.cursor = 0            # next row to reuse when there is no free

  def burst(self, x, y, count=None):
    """Throws `count` bits from (x, y)."""
    amount = int(count or G.CONFETTI_PER_BURST)
    rows = self._free(amount)
    if len(rows) == 0:
      return
    self._place(rows, (x, y))
    self._colour(rows)

  def _place(self, rows, origin):
    """Puts the bits in the burst and gives them speeds and life."""
    speeds = G.CONFETTI_SPEED
    lives = G.CONFETTI_LIFE
    speed = self.rng.uniform(speeds[0], speeds[1], len(rows))
    angle = self.rng.uniform(-math.pi, 0.0, len(rows))   # upwards
    self.pos[rows] = origin
    self.vel[rows, 0] = np.cos(angle) * speed
    self.vel[rows, 1] = np.sin(angle) * speed
    self.sway[rows] = self.rng.uniform(*G.CONFETTI_SWAY, len(rows))
    self.spin[rows] = self.rng.uniform(*G.CONFETTI_SPIN, len(rows))
    self.phase[rows] = self.rng.uniform(0.0, TWO_PI, len(rows))
    self.life[rows] = self.rng.uniform(lives[0], lives[1], len(rows))
    self.total[rows] = self.life[rows]

  def _colour(self, rows):
    """Colour and half width of the bits."""
    palette = np.array(COLOURS, np.float32)
    pick = self.rng.integers(0, len(COLOURS), len(rows))
    self.col[rows, :RGB] = palette[pick]
    self.col[rows, HW_COLUMN] = self.rng.uniform(*G.CONFETTI_SIZE,
                                                  len(rows))

  def update(self, dt):
    """Moves the bits one frame and frees the dead ones."""
    alive = self.life > 0
    if not alive.any():
      return
    drag = math.exp(-G.CONFETTI_DRAG * dt)
    self.vel[alive, 1] += G.CONFETTI_GRAVITY * dt
    self.vel[alive] *= drag
    self.pos[alive, 0] += (self.vel[alive, 0] + self.sway[alive]) * dt
    self.pos[alive, 1] += self.vel[alive, 1] * dt
    self.phase[alive] += self.spin[alive] * dt
    self.life[alive] -= dt
    self.life[self.life < MIN_LIFE] = 0.0

  def live(self):
    """(positions, colours) of the bits still alive."""
    rows = self.life > 0
    if not rows.any():
      return self.pos[:0], self.col[:0]
    colour = self.col[rows].copy()
    self._fade(colour, self.life[rows], self.total[rows])
    self._turn(colour, self.phase[rows])
    return self.pos[rows], colour

  def _fade(self, colour, life, total):
    """Dims the paper in the last part of its life."""
    fade = np.minimum(1.0, (life / total) / DIM_SHARE)
    colour[:, :RGB] *= fade[:, None]

  def _turn(self, colour, phase):
    """Height of the bit: it shows its edge when it turns."""
    width = np.maximum(MIN_SIZE, colour[:, HW_COLUMN])
    height = width * G.CONFETTI_THICK * np.abs(np.cos(phase))
    colour[:, HW_COLUMN] = width
    colour[:, HH_COLUMN] = np.maximum(MIN_SIZE, height)

  def clear(self):
    """Kills every bit (new match, menu...)."""
    self.life[:] = 0.0

  def alive(self):
    """True while there is paper on the screen."""
    return bool((self.life > 0).any())

  def _free(self, amount):
    """Rows for new bits: the free ones first, then the oldest."""
    dead = np.flatnonzero(self.life <= 0)
    if len(dead) >= amount:
      return dead[:amount]
    start = self.cursor
    self.cursor = (start + amount) % self.count
    return np.arange(start, start + amount) % self.count
