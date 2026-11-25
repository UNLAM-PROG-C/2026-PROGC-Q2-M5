"""Sparks of the effects chain (positions on the CPU, drawing on the GPU).

The pool is a few numpy arrays: x, y, velocity, life and colour. Each frame
it advances with simple arithmetic and the live rows are what the
`particles` kernel turns into light. When the budget is full the oldest
sparks are recycled, so the memory never grows.
"""
import math

import numpy as np

from fdc import config

SEED = 20251105         # fixed seed: the sparks look the same every run
TWO_PI = math.pi * 2.0  # full turn in radians
COL_CHANNELS = 4        # r, g, b and size of a spark
RGB = 3                 # colour channels (the fourth is the size)
SIZE_COLUMN = 3         # column of the size inside `col`
SIZE_JITTER = 0.6       # fraction of the size that varies per spark
MIN_LIFE = 0.01         # s: below this the row is free


class Field:
  """Pool of sparks: `spawn` adds, `update` moves, `live` reads."""

  def __init__(self, count=None):
    size = count or config.Gpu.PARTICLES
    self.count = size
    self.pos = np.zeros((size, 2), np.float32)
    self.vel = np.zeros((size, 2), np.float32)
    self.life = np.zeros(size, np.float32)
    self.total = np.ones(size, np.float32)
    self.col = np.zeros((size, COL_CHANNELS), np.float32)
    self.rng = np.random.default_rng(SEED)
    self.cursor = 0        # next row to reuse when there is no free one

  def spawn(self, x, y, rgb, count=None):
    """`count` sparks at (x, y) with colour rgb (0-1)."""
    amount = count or config.Gpu.PARTICLE_PER_TOUCH
    rows = self._free(amount)
    if len(rows) == 0:
      return
    self._set_rows(rows, x, y, rgb)

  def _set_rows(self, rows, x, y, rgb):
    """Position, speed, life and colour of the chosen rows."""
    speeds = config.Gpu.PARTICLE_SPEED
    lives = config.Gpu.PARTICLE_LIFE
    speed = self.rng.uniform(speeds[0], speeds[1], len(rows))
    angle = self.rng.uniform(0.0, TWO_PI, len(rows))
    self.pos[rows] = (x, y)
    self.vel[rows, 0] = np.cos(angle) * speed
    self.vel[rows, 1] = np.sin(angle) * speed
    self.life[rows] = self.rng.uniform(lives[0], lives[1], len(rows))
    self.total[rows] = self.life[rows]
    self.col[rows, :RGB] = np.array(rgb, np.float32)
    jitter = 1.0 + self.rng.uniform(-SIZE_JITTER, SIZE_JITTER, len(rows))
    self.col[rows, SIZE_COLUMN] = config.Gpu.PARTICLE_SIZE * jitter

  def update(self, dt):
    """Moves the sparks one frame and fades the dying ones."""
    alive = self.life > 0
    self.vel[alive, 1] += config.Gpu.PARTICLE_GRAVITY * dt
    self.pos[alive] += self.vel[alive] * dt
    self.life[alive] -= dt
    self.life[self.life < MIN_LIFE] = 0.0

  def live(self):
    """(positions, colours) of the sparks still alive."""
    rows = self.life > 0
    if not rows.any():
      return self.pos[:0], self.col[:0]
    fade = (self.life[rows] / self.total[rows])[:, None]
    colour = self.col[rows].copy()
    colour[:, :RGB] *= fade
    colour[:, SIZE_COLUMN] *= fade[:, 0]
    return self.pos[rows], colour

  def clear(self):
    """Kills every spark (new match, menu...)."""
    self.life[:] = 0.0

  def _free(self, amount):
    """Rows for new sparks: the free ones first, then the oldest."""
    dead = np.flatnonzero(self.life <= 0)
    if len(dead) >= amount:
      return dead[:amount]
    start = self.cursor
    self.cursor = (start + amount) % self.count
    return np.arange(start, start + amount) % self.count
