"""Efectos visuales efímeros (partículas, anillos, destellos).

Son sólo presentación: se disparan a partir de eventos que envía la
simulación (patada, rebote, gol, poder, explosión) y no influyen en el juego.
"""
import math
import random

import pygame

from . import art

_rng = random.Random(1234)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color", "kind", "g", "spin", "angle")

    def __init__(self, x, y, vx, vy, life, size, color, kind="dot", g=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size, self.color, self.kind, self.g = size, color, kind, g
        self.spin = _rng.uniform(-8, 8)
        self.angle = _rng.uniform(0, 6.28)


class Ring:
    __slots__ = ("x", "y", "r0", "r1", "life", "max_life", "color", "width")

    def __init__(self, x, y, r0, r1, life, color, width=4):
        self.x, self.y, self.r0, self.r1 = x, y, r0, r1
        self.life = self.max_life = life
        self.color, self.width = color, width


class Effects:
    MAX = 600

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
    def burst(self, x, y, n, color, speed=(80, 260), life=(0.25, 0.5), size=(2, 4), g=500.0,
              kind="dot", spread=math.tau, direction=0.0):
        for _ in range(n):
            if len(self.parts) >= self.MAX:
                break
            a = direction + _rng.uniform(-spread / 2, spread / 2)
            sp = _rng.uniform(*speed)
            col = color if not callable(color) else color()
            self.parts.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp,
                                       _rng.uniform(*life), _rng.uniform(*size), col, kind, g))

    def ring(self, x, y, r0, r1, life, color, width=4):
        self.rings.append(Ring(x, y, r0, r1, life, color, width))

    def impact(self, x, y, strength=1.0, color=(255, 255, 255)):
        self.burst(x, y, int(6 + 8 * strength), color, speed=(60, 200 + 200 * strength),
                   life=(0.12, 0.3), size=(1.5, 3.5), g=0, kind="spark")
        self.ring(x, y, 8, 26 + 20 * strength, 0.22, color, 3)

    def dust(self, x, y, strength=1.0):
        self.burst(x, y, int(4 + 6 * strength), (220, 210, 180), speed=(30, 110),
                   life=(0.3, 0.6), size=(2, 5), g=-30, kind="puff", spread=math.pi, direction=-math.pi / 2)

    def confetti(self, x, y, colors):
        self.burst(x, y, 120, lambda: _rng.choice(colors), speed=(200, 650), life=(1.2, 2.2),
                   size=(3, 6), g=420, kind="confetti", spread=math.pi * 0.9, direction=-math.pi / 2)

    def explosion(self, x, y, radius):
        self.flash = 0.35
        self.shake = 0.35
        self.ring(x, y, 20, radius, 0.45, (255, 210, 120), 10)
        self.ring(x, y, 10, radius * 0.7, 0.35, (255, 255, 255), 6)
        self.burst(x, y, 60, lambda: _rng.choice([(255, 200, 60), (255, 120, 40), (255, 240, 180)]),
                   speed=(150, 600), life=(0.3, 0.7), size=(3, 7), g=300, kind="spark")
        self.burst(x, y, 24, (90, 86, 92), speed=(40, 160), life=(0.7, 1.3), size=(8, 16),
                   g=-60, kind="puff")

    def sparkle(self, x, y, color):
        self.ring(x, y, 10, 70, 0.4, color, 5)
        self.burst(x, y, 26, color, speed=(80, 320), life=(0.3, 0.7), size=(2, 4), g=0, kind="star")

    def snow(self, x, y):
        self.burst(x, y, 2, (220, 245, 255), speed=(10, 40), life=(0.5, 0.9), size=(2, 3), g=40,
                   kind="dot")

    # ------------------------------------------------------------------ ciclo
    def update(self, dt):
        alive = []
        for p in self.parts:
            p.life -= dt
            if p.life <= 0:
                continue
            p.vy += p.g * dt
            if p.kind == "confetti":
                p.vx *= math.exp(-1.5 * dt)
                p.vy = min(p.vy, 160)
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
        k = self.shake * 22
        return _rng.uniform(-k, k), _rng.uniform(-k, k)

    def draw(self, surf, offset=(0, 0)):
        """Todo en "píxeles de arte" de 2x2 (estilo retro)."""
        ox, oy = offset
        for r in self.rings:
            t = 1 - r.life / r.max_life
            rad = r.r0 + (r.r1 - r.r0) * (1 - (1 - t) ** 2)
            w = 2 if r.width < 6 else 4
            if int(t * 10) % 2 == 0 or t < 0.5:
                pygame.draw.circle(surf, r.color[:3], (int(r.x + ox), int(r.y + oy)), int(rad), w)
        for p in self.parts:
            t = p.life / p.max_life
            x, y = int(p.x + ox) // 2 * 2, int(p.y + oy) // 2 * 2
            if p.kind == "puff":
                sz = int(p.size * (1.6 - t)) // 2 * 2 + 2
                if (int(p.x) // 4 + int(p.y) // 4) % 2 == 0 or t > 0.5:
                    surf.fill(p.color[:3], (x - sz // 2, y - sz // 2, sz, sz))
            elif p.kind == "confetti":
                w = 4 if abs(math.cos(p.angle)) > 0.5 else 2
                surf.fill(p.color[:3], (x, y, w, 4))
            elif p.kind == "star":
                sz = 2 if t < 0.5 else 4
                surf.fill(p.color[:3], (x - sz, y, sz * 2 + 2, 2))
                surf.fill(p.color[:3], (x, y - sz, 2, sz * 2 + 2))
            elif p.kind == "spark":
                surf.fill(p.color[:3], (x, y, 4 if t > 0.5 else 2, 4 if t > 0.5 else 2))
            else:
                sz = 4 if p.size * t > 2 else 2
                surf.fill(p.color[:3], (x, y, sz, sz))
        if self.flash > 0:
            fl = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            fl.fill((255, 250, 230, int(170 * self.flash / 0.35)))
            surf.blit(fl, (0, 0))


def glow_dot(radius, color):
    return art.radial_glow(radius, color, 0.8)
