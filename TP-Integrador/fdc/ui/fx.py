"""Short-lived visual effects (particles, rings, flashes).

They are only presentation: they are fired from events sent by the
simulation (kick, bounce, goal, power, explosion) and do not affect the
game.

Each effect is a "recipe": how many particles, how fast (px/s), how long
they live (s), how big (px) and with which gravity (px/s^2, positive
downwards). The ranges (min, max) are drawn for each particle.
"""
import math
import random

import pygame

from fdc.ui import art
from fdc.ui import palette
from fdc.ui import retro

PX = retro.PX
# Fixed seed: effects look the same on every run (repeatable tests).
SEED = 1234
MAX_PARTICLES = 600         # live particles at most; extra ones are skipped
SPIN_RANGE = 8              # rad/s: maximum spin of a particle, either way
START_ANGLE_MAX = 6.28      # rad: random start angle, from 0 to almost a turn
UP = -math.pi / 2           # "up" direction (y grows downwards)
RING_WIDTH = 4              # px: default thickness of a ring
THICK_RING = 6              # from this thickness a ring has a double stroke

# --- generic burst (default values of burst)
BURST_SPEED = (80, 260)     # px/s
BURST_LIFE = (0.25, 0.5)    # s
BURST_SIZE = (2, 4)         # px
BURST_GRAVITY = 500.0       # px/s^2
# --- hit on the ball (kick, header, crossbar): sparks + ring, by strength
IMPACT_SPARKS = 6           # sparks with strength 0...
IMPACT_SPARKS_EXTRA = 8     # ...plus these with strength 1
IMPACT_SPEED_MIN = 60       # px/s: slowest spark
IMPACT_SPEED_MAX = 200      # px/s: fastest spark with strength 0...
IMPACT_SPEED_EXTRA = 200    # ...plus this with strength 1
IMPACT_LIFE = (0.12, 0.3)   # s
IMPACT_SIZE = (1.5, 3.5)    # px
IMPACT_RING_START = 8       # px: start radius of the ring
IMPACT_RING_END = 26        # px: end radius with strength 0...
IMPACT_RING_EXTRA = 20      # ...plus this with strength 1
IMPACT_RING_LIFE = 0.22     # s
IMPACT_RING_WIDTH = 3       # px
KICK_SPARK = (255, 245, 200)  # kick sparks: warm white
# --- dust of a hard bounce on the floor
DUST_PARTICLES = 4          # little clouds with strength 0...
DUST_PARTICLES_EXTRA = 6    # ...plus these with strength 1
DUST_COLOR = (220, 210, 180)  # light soil
DUST_SPEED = (30, 110)      # px/s
DUST_LIFE = (0.3, 0.6)      # s
DUST_SIZE = (2, 5)          # px
DUST_GRAVITY = -30          # px/s^2: it rises slowly
# --- confetti of the goal and of the champion
CONFETTI_COUNT = 120        # pieces per celebration
CONFETTI_SPEED = (200, 650)  # px/s
CONFETTI_LIFE = (1.2, 2.2)  # s
CONFETTI_SIZE = (3, 6)      # px
CONFETTI_GRAVITY = 420      # px/s^2
CONFETTI_SPREAD = math.pi * 0.9   # rad: upward fan, almost half a turn
CONFETTI_DRAG = 1.5         # horizontal air drag (per second)
CONFETTI_MAX_FALL = 160     # px/s: confetti glides, never faster than this
# --- bomb explosion
EXPLOSION_FLASH = 0.35      # s: white flash of the whole screen
EXPLOSION_SHAKE = 0.35      # s: camera shake
FLASH_COLOR = (255, 250, 230)  # flash: warm white
FLASH_ALPHA = 170           # opacity of the flash when it starts
BLAST_RING_START = 20       # px: orange shock wave, start radius
BLAST_RING_LIFE = 0.45      # s
BLAST_RING_COLOR = (255, 210, 120)   # fire orange
BLAST_RING_WIDTH = 10       # px
CORE_RING_START = 10        # px: inner white wave, start radius
CORE_RING_SHARE = 0.7       # it reaches 70 % of the explosion radius
CORE_RING_LIFE = 0.35       # s
CORE_RING_WIDTH = 6         # px
FIRE_COUNT = 60             # fire sparks
# Yellow, orange and warm white (RGB).
FIRE_COLORS = [(255, 200, 60), (255, 120, 40), (255, 240, 180)]
FIRE_SPEED = (150, 600)     # px/s
FIRE_LIFE = (0.3, 0.7)      # s
FIRE_SIZE = (3, 7)          # px
FIRE_GRAVITY = 300          # px/s^2
SMOKE_COUNT = 24            # puffs of smoke
SMOKE_COLOR = (90, 86, 92)  # smoke grey
SMOKE_SPEED = (40, 160)     # px/s
SMOKE_LIFE = (0.7, 1.3)     # s
SMOKE_SIZE = (8, 16)        # px
SMOKE_GRAVITY = -60         # px/s^2: smoke rises
# --- power activated: ring + little stars of the category colour
SPARKLE_RING_START = 10     # px
SPARKLE_RING_END = 70       # px
SPARKLE_RING_LIFE = 0.4     # s
SPARKLE_RING_WIDTH = 5      # px
SPARKLE_COUNT = 26          # little stars
SPARKLE_SPEED = (80, 320)   # px/s
SPARKLE_LIFE = (0.3, 0.7)   # s
# --- a power object appears on the pitch
SPAWN_RING_START = 10       # px
SPAWN_RING_END = 60         # px
SPAWN_RING_LIFE = 0.35      # s
# --- a power object vanishes without anybody touching it
VANISH_COUNT = 14           # little clouds of smoke
VANISH_COLOR = (230, 230, 240)  # white smoke
VANISH_SPEED = (40, 120)    # px/s
VANISH_SIZE = (4, 8)        # px
# --- blocked kick (player without kick): red sparks in front of the boot
BLOCKED_COUNT = 8           # sparks
BLOCKED_COLOR = (255, 80, 80)   # red: not allowed
BLOCKED_SPEED = (40, 120)   # px/s
BLOCKED_AHEAD = 30          # px in front of the player
BLOCKED_HEIGHT = 20         # px above the feet
# --- snowflakes over a frozen player
SNOW_COUNT = 2              # flakes per batch
SNOW_COLOR = (220, 245, 255)  # ice blue
SNOW_SPEED = (10, 40)       # px/s
SNOW_LIFE = (0.5, 0.9)      # s
SNOW_SIZE = (2, 3)          # px
SNOW_GRAVITY = 40           # px/s^2: they fall slowly
SNOW_TICK_HZ = 20           # the snow clock ticks 20 times per second...
SNOW_EVERY = 3              # ...and a batch falls every 3 ticks
# px/s with which the batch sweeps the head width (it looks random).
SNOW_SWEEP = 97
SNOW_SPREAD = 60            # px: width of the zone where flakes fall
SNOW_HEIGHT = 120           # px above the feet (at scale 1) they fall from
# --- drawing
SHAKE_PX = 22               # px of shake per second of shake left
RING_BLINK_HZ = 10          # in its second half the ring blinks (per second)
PUFF_GROWTH = 1.6           # a puff grows up to 1.6 times when vanishing
DITHER_CELL = 4             # px: checkerboard cells that fade the puffs
GLOW_DOT_STRENGTH = 0.8     # strength of the soft glow of glow_dot

_rng = random.Random(SEED)


class Particle:
    """A moving dot, spark, star, puff or piece of confetti."""
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color",
                 "kind", "g", "spin", "angle")

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def __init__(self, x, y, vx, vy, life, size, color, kind="dot", g=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size, self.color, self.kind, self.g = size, color, kind, g
        self.spin = _rng.uniform(-SPIN_RANGE, SPIN_RANGE)
        self.angle = _rng.uniform(0, START_ANGLE_MAX)

    def move(self, dt):
        """Advances dt seconds; False when the particle is dead."""
        self.life -= dt
        if self.life <= 0:
            return False
        self.vy += self.g * dt
        if self.kind == "confetti":
            self.vx *= math.exp(-CONFETTI_DRAG * dt)
            self.vy = min(self.vy, CONFETTI_MAX_FALL)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        return True


class Ring:
    """A ring that grows from r0 to r1 px."""
    __slots__ = ("x", "y", "r0", "r1", "life", "max_life", "color", "width")

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def __init__(self, x, y, r0, r1, life, color, width=RING_WIDTH):
        self.x, self.y, self.r0, self.r1 = x, y, r0, r1
        self.life = self.max_life = life
        self.color, self.width = color, width

    def tick(self, dt):
        """Advances dt seconds; False when the ring is gone."""
        self.life -= dt
        return self.life > 0


# ---------------------------------------------------------------------------
# How each kind of particle is drawn (fill rects of PX x PX art pixels)
# ---------------------------------------------------------------------------
def _draw_puff(surf, p, x, y, t, color):
    sz = int(p.size * (PUFF_GROWTH - t)) // PX * PX + PX
    checker = (int(p.x) // DITHER_CELL + int(p.y) // DITHER_CELL) % 2 == 0
    if checker or t > 0.5:
        surf.fill(color, (x - sz // 2, y - sz // 2, sz, sz))


def _draw_confetti(surf, p, x, y, t, color):
    del t  # Unused.
    # A piece of paper seen from the front or from the side.
    w = 2 * PX if abs(math.cos(p.angle)) > 0.5 else PX
    surf.fill(color, (x, y, w, 2 * PX))


def _draw_star(surf, p, x, y, t, color):
    del p  # Unused.
    sz = PX if t < 0.5 else 2 * PX
    surf.fill(color, (x - sz, y, sz * 2 + PX, PX))
    surf.fill(color, (x, y - sz, PX, sz * 2 + PX))


def _draw_spark(surf, p, x, y, t, color):
    del p  # Unused.
    sz = 2 * PX if t > 0.5 else PX
    surf.fill(color, (x, y, sz, sz))


def _draw_dot(surf, p, x, y, t, color):
    sz = 2 * PX if p.size * t > PX else PX
    surf.fill(color, (x, y, sz, sz))


DRAWERS = {"puff": _draw_puff, "confetti": _draw_confetti,
           "star": _draw_star, "spark": _draw_spark}


class Effects:
    """All live particles and rings, plus the flash and the shake."""
    MAX = MAX_PARTICLES

    def __init__(self):
        self.parts = []
        self.rings = []
        self.flash = 0.0
        self.shake = 0.0

    def clear(self):
        self.parts.clear()
        self.rings.clear()
        self.flash = self.shake = 0.0

    # ------------------------------------------------------------ emitters
    # pylint: disable-next=too-many-arguments
    def burst(self, x, y, n, color, speed=BURST_SPEED, life=BURST_LIFE,
              size=BURST_SIZE, g=BURST_GRAVITY, kind="dot", spread=math.tau,
              direction=0.0):
        """n particles from (x, y); color may be a function (one each)."""
        for _ in range(n):
            if len(self.parts) >= self.MAX:
                break
            a = direction + _rng.uniform(-spread / 2, spread / 2)
            sp = _rng.uniform(*speed)
            col = color if not callable(color) else color()
            self.parts.append(Particle(
                x, y, math.cos(a) * sp, math.sin(a) * sp,
                _rng.uniform(*life), _rng.uniform(*size), col, kind, g))

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def ring(self, x, y, r0, r1, life, color, width=RING_WIDTH):
        self.rings.append(Ring(x, y, r0, r1, life, color, width))

    def impact(self, x, y, strength=1.0, color=palette.WHITE):
        """Hit on the ball: sparks and a ring that grow with strength."""
        self.burst(x, y, int(IMPACT_SPARKS + IMPACT_SPARKS_EXTRA * strength),
                   color, speed=(IMPACT_SPEED_MIN, IMPACT_SPEED_MAX
                                 + IMPACT_SPEED_EXTRA * strength),
                   life=IMPACT_LIFE, size=IMPACT_SIZE, g=0, kind="spark")
        self.ring(x, y, IMPACT_RING_START,
                  IMPACT_RING_END + IMPACT_RING_EXTRA * strength,
                  IMPACT_RING_LIFE, color, IMPACT_RING_WIDTH)

    def kick_impact(self, x, y):
        self.impact(x, y, 1.0, KICK_SPARK)

    def dust(self, x, y, strength=1.0):
        self.burst(x, y, int(DUST_PARTICLES + DUST_PARTICLES_EXTRA * strength),
                   DUST_COLOR, speed=DUST_SPEED, life=DUST_LIFE,
                   size=DUST_SIZE, g=DUST_GRAVITY, kind="puff",
                   spread=math.pi, direction=UP)

    def confetti(self, x, y, colors):
        self.burst(x, y, CONFETTI_COUNT, lambda: _rng.choice(colors),
                   speed=CONFETTI_SPEED, life=CONFETTI_LIFE,
                   size=CONFETTI_SIZE, g=CONFETTI_GRAVITY, kind="confetti",
                   spread=CONFETTI_SPREAD, direction=UP)

    def explosion(self, x, y, radius):
        self.flash = EXPLOSION_FLASH
        self.shake = EXPLOSION_SHAKE
        self.ring(x, y, BLAST_RING_START, radius, BLAST_RING_LIFE,
                  BLAST_RING_COLOR, BLAST_RING_WIDTH)
        self.ring(x, y, CORE_RING_START, radius * CORE_RING_SHARE,
                  CORE_RING_LIFE, palette.WHITE, CORE_RING_WIDTH)
        self.burst(x, y, FIRE_COUNT, lambda: _rng.choice(FIRE_COLORS),
                   speed=FIRE_SPEED, life=FIRE_LIFE, size=FIRE_SIZE,
                   g=FIRE_GRAVITY, kind="spark")
        self.burst(x, y, SMOKE_COUNT, SMOKE_COLOR, speed=SMOKE_SPEED,
                   life=SMOKE_LIFE, size=SMOKE_SIZE, g=SMOKE_GRAVITY,
                   kind="puff")

    def sparkle(self, x, y, color):
        self.ring(x, y, SPARKLE_RING_START, SPARKLE_RING_END,
                  SPARKLE_RING_LIFE, color, SPARKLE_RING_WIDTH)
        self.burst(x, y, SPARKLE_COUNT, color, speed=SPARKLE_SPEED,
                   life=SPARKLE_LIFE, size=BURST_SIZE, g=0, kind="star")

    def power_spawn(self, x, y, color):
        self.ring(x, y, SPAWN_RING_START, SPAWN_RING_END, SPAWN_RING_LIFE,
                  color)

    def vanish(self, x, y):
        self.burst(x, y, VANISH_COUNT, VANISH_COLOR, speed=VANISH_SPEED, g=0,
                   kind="puff", size=VANISH_SIZE)

    def kick_blocked(self, x, y, facing):
        self.burst(x + BLOCKED_AHEAD * facing, y - BLOCKED_HEIGHT,
                   BLOCKED_COUNT, BLOCKED_COLOR, speed=BLOCKED_SPEED, g=0)

    def snow(self, x, y):
        self.burst(x, y, SNOW_COUNT, SNOW_COLOR, speed=SNOW_SPEED,
                   life=SNOW_LIFE, size=SNOW_SIZE, g=SNOW_GRAVITY, kind="dot")

    def frozen(self, t, x, y, scale):
        """Flakes over a frozen player (called every frame; a batch falls
        now and then)."""
        if int(t * SNOW_TICK_HZ) % SNOW_EVERY == 0:
            self.snow(x + (t * SNOW_SWEEP % SNOW_SPREAD) - SNOW_SPREAD / 2,
                      y - SNOW_HEIGHT * scale)

    # ------------------------------------------------------------ cycle
    def update(self, dt):
        self.parts = [p for p in self.parts if p.move(dt)]
        self.rings = [r for r in self.rings if r.tick(dt)]
        self.flash = max(0.0, self.flash - dt)
        self.shake = max(0.0, self.shake - dt)

    def shake_offset(self):
        """Random camera offset (px) while the shake lasts."""
        if self.shake <= 0:
            return 0, 0
        k = self.shake * SHAKE_PX
        return _rng.uniform(-k, k), _rng.uniform(-k, k)

    def draw(self, surf, offset=(0, 0)):
        """Everything in art pixels of PX x PX (retro style)."""
        for r in self.rings:
            self._draw_ring(surf, r, offset)
        ox, oy = offset
        rgb = palette.RGB_CHANNELS
        for p in self.parts:
            x = int(p.x + ox) // PX * PX
            y = int(p.y + oy) // PX * PX
            draw = DRAWERS.get(p.kind, _draw_dot)
            draw(surf, p, x, y, p.life / p.max_life, p.color[:rgb])
        if self.flash > 0:
            self._draw_flash(surf)

    def _draw_ring(self, surf, r, offset):
        t = 1 - r.life / r.max_life
        rad = r.r0 + (r.r1 - r.r0) * (1 - (1 - t) ** 2)
        w = PX if r.width < THICK_RING else 2 * PX
        if int(t * RING_BLINK_HZ) % 2 == 0 or t < 0.5:
            pygame.draw.circle(surf, r.color[:palette.RGB_CHANNELS],
                               (int(r.x + offset[0]), int(r.y + offset[1])),
                               int(rad), w)

    def _draw_flash(self, surf):
        fl = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        fl.fill((*FLASH_COLOR,
                 int(FLASH_ALPHA * self.flash / EXPLOSION_FLASH)))
        surf.blit(fl, (0, 0))


def glow_dot(radius, color):
    """Soft glow circle used behind power objects."""
    return art.radial_glow(radius, color, GLOW_DOT_STRENGTH)
