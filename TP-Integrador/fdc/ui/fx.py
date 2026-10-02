"""Efectos visuales efímeros (partículas, anillos, destellos).

Son sólo presentación: se disparan a partir de eventos que envía la
simulación (patada, rebote, gol, poder, explosión) y no influyen en el juego.

Cada efecto es una "receta": cuántas partículas, a qué velocidad (px/s),
cuánto viven (s), de qué tamaño (px) y con qué gravedad (px/s², positiva
hacia abajo). Los rangos (mín, máx) se sortean para cada partícula.
"""
import math
import random

import pygame

from . import art
from . import palette as C
from .retro import PX

SEED = 1234                 # semilla fija: los efectos se ven igual en cada corrida (pruebas reproducibles)
MAX_PARTICLES = 600         # partículas vivas como máximo; las que sobran no se crean
SPIN_RANGE = 8              # rad/s: giro máximo de una partícula, en cualquier sentido
START_ANGLE_MAX = 6.28      # rad: ángulo inicial al azar, entre 0 y casi una vuelta
UP = -math.pi / 2           # dirección "hacia arriba" (la y crece hacia abajo)
RING_WIDTH = 4              # px: grosor por defecto de un anillo
THICK_RING = 6              # desde este grosor el anillo se dibuja con trazo doble

# --- ráfaga genérica (valores por defecto de burst)
BURST_SPEED = (80, 260)     # px/s
BURST_LIFE = (0.25, 0.5)    # s
BURST_SIZE = (2, 4)         # px
BURST_GRAVITY = 500.0       # px/s²
# --- golpe a la pelota (patada, cabezazo, travesaño): chispas + anillo; crecen con la fuerza
IMPACT_SPARKS = 6           # chispas con fuerza 0...
IMPACT_SPARKS_EXTRA = 8     # ...más estas con fuerza 1
IMPACT_SPEED_MIN = 60       # px/s: chispa más lenta
IMPACT_SPEED_MAX = 200      # px/s: chispa más rápida con fuerza 0...
IMPACT_SPEED_EXTRA = 200    # ...más esto con fuerza 1
IMPACT_LIFE = (0.12, 0.3)   # s
IMPACT_SIZE = (1.5, 3.5)    # px
IMPACT_RING_START = 8       # px: radio inicial del anillo
IMPACT_RING_END = 26        # px: radio final con fuerza 0...
IMPACT_RING_EXTRA = 20      # ...más esto con fuerza 1
IMPACT_RING_LIFE = 0.22     # s
IMPACT_RING_WIDTH = 3       # px
KICK_SPARK = (255, 245, 200)  # chispas de la patada: blanco cálido
# --- polvo del pique fuerte contra el piso
DUST_PARTICLES = 4          # nubecitas con fuerza 0...
DUST_PARTICLES_EXTRA = 6    # ...más estas con fuerza 1
DUST_COLOR = (220, 210, 180)  # tierra clara
DUST_SPEED = (30, 110)      # px/s
DUST_LIFE = (0.3, 0.6)      # s
DUST_SIZE = (2, 5)          # px
DUST_GRAVITY = -30          # sube despacio
# --- papelitos del gol y del campeón
CONFETTI_COUNT = 120        # papelitos por festejo
CONFETTI_SPEED = (200, 650)  # px/s
CONFETTI_LIFE = (1.2, 2.2)  # s
CONFETTI_SIZE = (3, 6)      # px
CONFETTI_GRAVITY = 420      # px/s²
CONFETTI_SPREAD = math.pi * 0.9   # abanico hacia arriba, casi media vuelta
CONFETTI_DRAG = 1.5         # frenado horizontal del aire (por segundo)
CONFETTI_MAX_FALL = 160     # px/s: los papelitos caen planeando, no más rápido que esto
# --- explosión de la bomba
EXPLOSION_FLASH = 0.35      # s: destello blanco de toda la pantalla
EXPLOSION_SHAKE = 0.35      # s: temblor de la cámara
FLASH_COLOR = (255, 250, 230)  # destello: blanco cálido
FLASH_ALPHA = 170           # opacidad del destello al empezar
BLAST_RING_START = 20       # px: onda expansiva naranja, radio inicial
BLAST_RING_LIFE = 0.45      # s
BLAST_RING_COLOR = (255, 210, 120)   # naranja fuego
BLAST_RING_WIDTH = 10       # px
CORE_RING_START = 10        # px: onda blanca interior, radio inicial
CORE_RING_SHARE = 0.7       # llega al 70 % del radio de la explosión
CORE_RING_LIFE = 0.35       # s
CORE_RING_WIDTH = 6         # px
FIRE_COUNT = 60             # chispas de fuego
FIRE_COLORS = [(255, 200, 60), (255, 120, 40), (255, 240, 180)]   # amarillo, naranja y blanco cálido
FIRE_SPEED = (150, 600)     # px/s
FIRE_LIFE = (0.3, 0.7)      # s
FIRE_SIZE = (3, 7)          # px
FIRE_GRAVITY = 300          # px/s²
SMOKE_COUNT = 24            # bocanadas de humo
SMOKE_COLOR = (90, 86, 92)  # gris humo
SMOKE_SPEED = (40, 160)     # px/s
SMOKE_LIFE = (0.7, 1.3)     # s
SMOKE_SIZE = (8, 16)        # px
SMOKE_GRAVITY = -60         # el humo sube
# --- poder activado: anillo + estrellitas del color de la categoría
SPARKLE_RING_START = 10     # px
SPARKLE_RING_END = 70       # px
SPARKLE_RING_LIFE = 0.4     # s
SPARKLE_RING_WIDTH = 5      # px
SPARKLE_COUNT = 26          # estrellitas
SPARKLE_SPEED = (80, 320)   # px/s
SPARKLE_LIFE = (0.3, 0.7)   # s
# --- aparece un objeto de poder en la cancha
SPAWN_RING_START = 10       # px
SPAWN_RING_END = 60         # px
SPAWN_RING_LIFE = 0.35      # s
# --- un objeto de poder desaparece sin que nadie lo toque
VANISH_COUNT = 14           # nubecitas de humo
VANISH_COLOR = (230, 230, 240)  # humito blanco
VANISH_SPEED = (40, 120)    # px/s
VANISH_SIZE = (4, 8)        # px
# --- patada bloqueada (jugador sin patada): chispitas rojas delante del botín
BLOCKED_COUNT = 8           # chispitas
BLOCKED_COLOR = (255, 80, 80)   # rojo: "no se puede"
BLOCKED_SPEED = (40, 120)   # px/s
BLOCKED_AHEAD = 30          # px delante del jugador
BLOCKED_HEIGHT = 20         # px sobre los pies
# --- copos sobre el jugador congelado
SNOW_COUNT = 2              # copos por tanda
SNOW_COLOR = (220, 245, 255)  # celeste hielo
SNOW_SPEED = (10, 40)       # px/s
SNOW_LIFE = (0.5, 0.9)      # s
SNOW_SIZE = (2, 3)          # px
SNOW_GRAVITY = 40           # caen despacio
SNOW_TICK_HZ = 20           # el reloj de los copos marca 20 pasos por segundo...
SNOW_EVERY = 3              # ...y cae una tanda cada 3 pasos
SNOW_SWEEP = 97             # px/s con los que la tanda barre el ancho de la cabeza (parece al azar)
SNOW_SPREAD = 60            # px: ancho de la zona donde caen los copos
SNOW_HEIGHT = 120           # px sobre los pies (a escala 1) desde donde caen
# --- dibujo
SHAKE_PX = 22               # px de temblor por cada segundo de temblor que queda
RING_BLINK_HZ = 10          # en su segunda mitad, el anillo parpadea (cambios por segundo)
PUFF_GROWTH = 1.6           # la nubecita crece hasta 1,6 veces su tamaño al desaparecer
DITHER_CELL = 4             # px: celdas del tablero de ajedrez con que se desvanecen las nubecitas
GLOW_DOT_STRENGTH = 0.8     # intensidad del brillo difuso de glow_dot

_rng = random.Random(SEED)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color", "kind", "g", "spin", "angle")

    def __init__(self, x, y, vx, vy, life, size, color, kind="dot", g=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size, self.color, self.kind, self.g = size, color, kind, g
        self.spin = _rng.uniform(-SPIN_RANGE, SPIN_RANGE)
        self.angle = _rng.uniform(0, START_ANGLE_MAX)


class Ring:
    __slots__ = ("x", "y", "r0", "r1", "life", "max_life", "color", "width")

    def __init__(self, x, y, r0, r1, life, color, width=RING_WIDTH):
        self.x, self.y, self.r0, self.r1 = x, y, r0, r1
        self.life = self.max_life = life
        self.color, self.width = color, width


class Effects:
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

    # ------------------------------------------------------------------ emisores
    def burst(self, x, y, n, color, speed=BURST_SPEED, life=BURST_LIFE, size=BURST_SIZE, g=BURST_GRAVITY,
              kind="dot", spread=math.tau, direction=0.0):
        for _ in range(n):
            if len(self.parts) >= self.MAX:
                break
            a = direction + _rng.uniform(-spread / 2, spread / 2)
            sp = _rng.uniform(*speed)
            col = color if not callable(color) else color()
            self.parts.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp,
                                       _rng.uniform(*life), _rng.uniform(*size), col, kind, g))

    def ring(self, x, y, r0, r1, life, color, width=RING_WIDTH):
        self.rings.append(Ring(x, y, r0, r1, life, color, width))

    def impact(self, x, y, strength=1.0, color=C.WHITE):
        self.burst(x, y, int(IMPACT_SPARKS + IMPACT_SPARKS_EXTRA * strength), color,
                   speed=(IMPACT_SPEED_MIN, IMPACT_SPEED_MAX + IMPACT_SPEED_EXTRA * strength),
                   life=IMPACT_LIFE, size=IMPACT_SIZE, g=0, kind="spark")
        self.ring(x, y, IMPACT_RING_START, IMPACT_RING_END + IMPACT_RING_EXTRA * strength, IMPACT_RING_LIFE, color,
                  IMPACT_RING_WIDTH)

    def kick_impact(self, x, y):
        self.impact(x, y, 1.0, KICK_SPARK)

    def dust(self, x, y, strength=1.0):
        self.burst(x, y, int(DUST_PARTICLES + DUST_PARTICLES_EXTRA * strength), DUST_COLOR, speed=DUST_SPEED,
                   life=DUST_LIFE, size=DUST_SIZE, g=DUST_GRAVITY, kind="puff", spread=math.pi, direction=UP)

    def confetti(self, x, y, colors):
        self.burst(x, y, CONFETTI_COUNT, lambda: _rng.choice(colors), speed=CONFETTI_SPEED, life=CONFETTI_LIFE,
                   size=CONFETTI_SIZE, g=CONFETTI_GRAVITY, kind="confetti", spread=CONFETTI_SPREAD, direction=UP)

    def explosion(self, x, y, radius):
        self.flash = EXPLOSION_FLASH
        self.shake = EXPLOSION_SHAKE
        self.ring(x, y, BLAST_RING_START, radius, BLAST_RING_LIFE, BLAST_RING_COLOR, BLAST_RING_WIDTH)
        self.ring(x, y, CORE_RING_START, radius * CORE_RING_SHARE, CORE_RING_LIFE, C.WHITE, CORE_RING_WIDTH)
        self.burst(x, y, FIRE_COUNT, lambda: _rng.choice(FIRE_COLORS), speed=FIRE_SPEED, life=FIRE_LIFE,
                   size=FIRE_SIZE, g=FIRE_GRAVITY, kind="spark")
        self.burst(x, y, SMOKE_COUNT, SMOKE_COLOR, speed=SMOKE_SPEED, life=SMOKE_LIFE, size=SMOKE_SIZE,
                   g=SMOKE_GRAVITY, kind="puff")

    def sparkle(self, x, y, color):
        self.ring(x, y, SPARKLE_RING_START, SPARKLE_RING_END, SPARKLE_RING_LIFE, color, SPARKLE_RING_WIDTH)
        self.burst(x, y, SPARKLE_COUNT, color, speed=SPARKLE_SPEED, life=SPARKLE_LIFE, size=BURST_SIZE, g=0,
                   kind="star")

    def power_spawn(self, x, y, color):
        self.ring(x, y, SPAWN_RING_START, SPAWN_RING_END, SPAWN_RING_LIFE, color)

    def vanish(self, x, y):
        self.burst(x, y, VANISH_COUNT, VANISH_COLOR, speed=VANISH_SPEED, g=0, kind="puff", size=VANISH_SIZE)

    def kick_blocked(self, x, y, facing):
        self.burst(x + BLOCKED_AHEAD * facing, y - BLOCKED_HEIGHT, BLOCKED_COUNT, BLOCKED_COLOR,
                   speed=BLOCKED_SPEED, g=0)

    def snow(self, x, y):
        self.burst(x, y, SNOW_COUNT, SNOW_COLOR, speed=SNOW_SPEED, life=SNOW_LIFE, size=SNOW_SIZE, g=SNOW_GRAVITY,
                   kind="dot")

    def frozen(self, t, x, y, scale):
        """Copos sobre un jugador congelado (se llama en cada cuadro; cae una tanda de vez en cuando)."""
        if int(t * SNOW_TICK_HZ) % SNOW_EVERY == 0:
            self.snow(x + (t * SNOW_SWEEP % SNOW_SPREAD) - SNOW_SPREAD / 2, y - SNOW_HEIGHT * scale)

    # ------------------------------------------------------------------ ciclo
    def update(self, dt):
        alive = []
        for p in self.parts:
            p.life -= dt
            if p.life <= 0:
                continue
            p.vy += p.g * dt
            if p.kind == "confetti":
                p.vx *= math.exp(-CONFETTI_DRAG * dt)
                p.vy = min(p.vy, CONFETTI_MAX_FALL)
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.angle += p.spin * dt
            alive.append(p)
        self.parts = alive
        self.rings = [r for r in self.rings if self._tick(r, dt)]
        self.flash = max(0.0, self.flash - dt)
        self.shake = max(0.0, self.shake - dt)

    @staticmethod
    def _tick(r, dt):
        r.life -= dt
        return r.life > 0

    def shake_offset(self):
        if self.shake <= 0:
            return 0, 0
        k = self.shake * SHAKE_PX
        return _rng.uniform(-k, k), _rng.uniform(-k, k)

    def draw(self, surf, offset=(0, 0)):
        """Todo en "píxeles de arte" de PX x PX (estilo retro)."""
        ox, oy = offset
        rgb = C.RGB_CHANNELS
        for r in self.rings:
            t = 1 - r.life / r.max_life
            rad = r.r0 + (r.r1 - r.r0) * (1 - (1 - t) ** 2)
            w = PX if r.width < THICK_RING else 2 * PX
            if int(t * RING_BLINK_HZ) % 2 == 0 or t < 0.5:
                pygame.draw.circle(surf, r.color[:rgb], (int(r.x + ox), int(r.y + oy)), int(rad), w)
        for p in self.parts:
            t = p.life / p.max_life
            x, y = int(p.x + ox) // PX * PX, int(p.y + oy) // PX * PX
            if p.kind == "puff":
                sz = int(p.size * (PUFF_GROWTH - t)) // PX * PX + PX
                if (int(p.x) // DITHER_CELL + int(p.y) // DITHER_CELL) % 2 == 0 or t > 0.5:
                    surf.fill(p.color[:rgb], (x - sz // 2, y - sz // 2, sz, sz))
            elif p.kind == "confetti":
                w = 2 * PX if abs(math.cos(p.angle)) > 0.5 else PX      # papelito de frente o de canto
                surf.fill(p.color[:rgb], (x, y, w, 2 * PX))
            elif p.kind == "star":
                sz = PX if t < 0.5 else 2 * PX
                surf.fill(p.color[:rgb], (x - sz, y, sz * 2 + PX, PX))
                surf.fill(p.color[:rgb], (x, y - sz, PX, sz * 2 + PX))
            elif p.kind == "spark":
                sz = 2 * PX if t > 0.5 else PX
                surf.fill(p.color[:rgb], (x, y, sz, sz))
            else:
                sz = 2 * PX if p.size * t > PX else PX
                surf.fill(p.color[:rgb], (x, y, sz, sz))
        if self.flash > 0:
            fl = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            fl.fill((*FLASH_COLOR, int(FLASH_ALPHA * self.flash / EXPLOSION_FLASH)))
            surf.blit(fl, (0, 0))


def glow_dot(radius, color):
    return art.radial_glow(radius, color, GLOW_DOT_STRENGTH)
