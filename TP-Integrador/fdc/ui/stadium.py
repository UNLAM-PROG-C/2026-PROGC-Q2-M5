"""Estadio retro: fondo en pixel art, arcos, pelota y sombras.

El fondo se dibuja una vez a resolución nativa (640 x 360) con colores claros
y se agranda x2. Tribunas y público van en tonos pastel apagados para que la
pelota y los jugadores (con contorno) siempre se distingan.
"""
import math
import random

import pygame

from ..config import Arena, GAME_NAME, PLAYER_COLORS, PLAYER_LABELS
from . import art, pixelfont
from . import palette as C
from .assets import load_override_image
from .retro import PX, dither_ellipse, outline_native, pixelize, scale_px

W, H = Arena.WIDTH, Arena.HEIGHT
NW, NH = W // PX, H // PX
FLOOR = Arena.FLOOR_Y
HALF_BAR = Arena.BAR_THICKNESS / 2
GRASS_TOP = 252            # borde lejano del césped (nativo)


def _dither_band(s, y0, y1, c_top, c_bot):
    """Degradé en dos colores con trama ordenada (look 16 bits)."""
    bayer = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0 - 1)
        for x in range(NW):
            thr = (bayer[y % 4][x % 4] + 0.5) / 16
            s.set_at((x, y), c_bot if t > thr else c_top)


def _cloud(s, x, y, w):
    parts = ((0, 4, 6), (7, 0, 8), (16, 3, 7), (24, 5, 5))
    for col, dy0 in ((C.CLOUD_SHADE, 2), (C.CLOUD, 0)):
        for dx, dy, r in parts:
            pygame.draw.circle(s, col, (x + int(dx * w / 30), y + dy + dy0), int(r * w / 30))


def build_background():
    custom = load_override_image("fondos", "estadio.png")
    if custom is not None:
        return pygame.transform.scale(custom, (W, H)).convert()
    rng = random.Random(1986)
    s = pygame.Surface((NW, NH))
    # cielo
    _dither_band(s, 0, 40, C.SKY_TOP, C.SKY_BOTTOM)
    for x, y, w in ((40, 8, 36), (230, 4, 28), (430, 10, 40), (580, 6, 24)):
        _cloud(s, x, y, w)

    # techo con reticulado
    roof_y0, roof_y1 = 24, 46
    pygame.draw.rect(s, C.ROOF, (0, roof_y0, NW, roof_y1 - roof_y0))
    pygame.draw.rect(s, C.STRUCT_SHADE, (0, roof_y1 - 4, NW, 4))
    pygame.draw.line(s, C.STRUCT_DARK, (0, roof_y0), (NW, roof_y0))
    pygame.draw.line(s, C.STRUCT_DARK, (0, roof_y1 - 5), (NW, roof_y1 - 5))
    for x in range(0, NW + 16, 16):
        pygame.draw.line(s, C.STRUCT_SHADE, (x, roof_y0 + 1), (x + 8, roof_y1 - 6))
        pygame.draw.line(s, C.STRUCT_SHADE, (x + 16, roof_y0 + 1), (x + 8, roof_y1 - 6))
    pygame.draw.rect(s, C.STRUCT_SHADE, (0, roof_y1, NW, 10))      # sombra bajo el techo
    pygame.draw.line(s, C.STRUCT_DARK, (0, roof_y1 + 9), (NW, roof_y1 + 9))
    for x in range(20, NW, 120):
        pygame.draw.rect(s, C.STRUCT_DARK, (x, roof_y1, 3, 10))
        pygame.draw.rect(s, C.STRUCT, (x + 1, roof_y1, 1, 10))
    for x in (60, 250, 390, 580):            # reflectores
        pygame.draw.rect(s, C.STRUCT_DARK, (x - 9, roof_y0 - 6, 18, 6))
        for k in range(4):
            pygame.draw.rect(s, (255, 250, 214), (x - 7 + k * 4, roof_y0 - 5, 3, 3))

    # tribunas: tres bandas con asientos y público pastel
    tiers = ((56, 112), (116, 176), (180, 232))
    crowd = [(236, 170, 160), (170, 200, 236), (250, 226, 150), (180, 222, 180), (236, 236, 240),
             (214, 180, 226), (250, 200, 170), (200, 206, 214)]
    skins = [(247, 214, 186), (232, 190, 150), (200, 150, 110), (160, 112, 80)]
    for y0, y1 in tiers:
        pygame.draw.rect(s, C.STRUCT, (0, y0 - 4, NW, 4))
        pygame.draw.line(s, C.WHITE, (0, y0 - 4), (NW, y0 - 4))
        for row_y in range(y0, y1, 6):
            seat = C.SEAT_RED if (row_y // 6) % 2 == 0 else C.SEAT_RED_DARK
            pygame.draw.rect(s, seat, (0, row_y, NW, 6))
            pygame.draw.line(s, C.SEAT_RED_DARK, (0, row_y + 5), (NW, row_y + 5))
            x = rng.randint(0, 3)
            while x < NW:
                if rng.random() < 0.78:
                    s.fill(rng.choice(crowd), (x, row_y + 2, 4, 3))
                    skin = rng.choice(skins)
                    s.fill(skin, (x + 1, row_y, 2, 2))
                    if rng.random() < 0.06:          # brazos arriba
                        s.fill(skin, (x - 1, row_y - 2, 1, 2))
                        s.fill(skin, (x + 4, row_y - 2, 1, 2))
                x += rng.randint(5, 7)
        for x in range(64, NW, 128):             # escaleras
            pygame.draw.rect(s, C.STRUCT, (x, y0, 8, y1 - y0))
            for yy in range(y0, y1, 3):
                pygame.draw.line(s, C.STRUCT_SHADE, (x, yy), (x + 7, yy))

    # muro y carteles
    pygame.draw.rect(s, C.STRUCT_SHADE, (0, 232, NW, 3))
    boards = [(GAME_NAME.upper(), C.BLUE), ("PROGRAMACION CONCURRENTE", C.RED),
              ("PROCESOS  COLAS  EVENTOS", C.GREEN), (GAME_NAME.upper(), C.PURPLE)]
    bw = NW // len(boards)
    for i, (label, col) in enumerate(boards):
        r = pygame.Rect(i * bw, 235, bw, 17)
        pygame.draw.rect(s, C.WHITE, r)
        pygame.draw.rect(s, col, (r.x, r.y, r.w, 3))
        pygame.draw.rect(s, col, (r.x, r.bottom - 2, r.w, 2))
        pygame.draw.line(s, C.STRUCT_DARK, (r.x, r.y), (r.x, r.bottom))
        img = pixelfont.render(label, 1, col)
        s.blit(img, img.get_rect(center=(r.centerx, r.centery + 1)))

    # césped con franjas que se abren hacia adelante (perspectiva)
    for y in range(GRASS_TOP, NH):
        t = (y - GRASS_TOP) / (NH - GRASS_TOP)
        stripe_w = 36 + 20 * t
        for x in range(NW):
            k = int((x - NW / 2) / stripe_w + 100)
            s.set_at((x, y), C.GRASS_A if k % 2 == 0 else C.GRASS_B)
    for _ in range(900):                          # briznas sueltas
        s.set_at((rng.randrange(NW), rng.randrange(GRASS_TOP + 2, NH)), C.GRASS_DARK)
    far, near = GRASS_TOP + 4, NH - 6             # líneas de cal
    pygame.draw.line(s, C.LINE, (0, far), (NW, far))
    pygame.draw.line(s, C.LINE, (0, near), (NW, near))
    pygame.draw.line(s, C.LINE, (NW // 2, far), (NW // 2, near))
    pygame.draw.ellipse(s, C.LINE, (NW // 2 - 64, 280, 128, 44), 1)
    s.fill(C.LINE, (NW // 2 - 1, 301, 3, 2))
    for side in (0, 1):
        if side == 0:
            box = [(0, far + 10), (58, far + 10), (74, near - 8), (0, near - 8)]
        else:
            box = [(NW, far + 10), (NW - 58, far + 10), (NW - 74, near - 8), (NW, near - 8)]
        pygame.draw.lines(s, C.LINE, False, box, 1)
    return scale_px(s).convert()


# ---------------------------------------------------------------------------
# Arcos (se dibujan cada cuadro: su altura cambia con los poderes)
# ---------------------------------------------------------------------------
def goal_bar_y(height):
    return FLOOR - height - HALF_BAR


def _goal_x(side):
    mouth = Arena.GOAL_DEPTH if side == 0 else W - Arena.GOAL_DEPTH
    x0, x1 = (0, mouth) if side == 0 else (mouth, W)
    return mouth, x0, x1


def draw_goal_back(surf, side, height):
    """Red, poste trasero y bandera del dueño (detrás de jugadores y pelota)."""
    mouth, x0, x1 = _goal_x(side)
    top = int(goal_bar_y(height) - HALF_BAR)
    top -= top % PX
    net = pygame.Surface((x1 - x0, FLOOR - top), pygame.SRCALPHA)
    net.fill((255, 255, 255, 40))
    nw, nh = net.get_size()
    for gx in range(0, nw, 8):
        net.fill((255, 255, 255, 150), (gx, 0, PX, nh))
    for gy in range(0, nh, 8):
        net.fill((255, 255, 255, 150), (0, gy, nw, PX))
    surf.blit(net, (x0, top))
    sh = dither_ellipse((x1 - x0) // PX, 5, alpha=80)
    surf.blit(scale_px(sh), (x0, FLOOR - 6))
    px = 6 if side == 0 else W - 12
    pygame.draw.rect(surf, C.INK, (px - PX, top, 6 + 2 * PX, FLOOR - top))
    pygame.draw.rect(surf, C.WHITE, (px, top, 6, FLOOR - top))
    col = PLAYER_COLORS[side]                     # banderita del dueño del arco
    fx = 24 if side == 0 else W - 24
    fy = top - 34
    pygame.draw.rect(surf, C.INK, (fx - PX, fy, 2 * PX, top - fy))
    d = 1 if side == 0 else -1
    pts = [(fx, fy), (fx + d * 30, fy + 9), (fx, fy + 18)]
    pygame.draw.polygon(surf, col, pts)
    pygame.draw.polygon(surf, C.INK, pts, PX)
    lab = pixelfont.render(PLAYER_LABELS[side], 1, C.WHITE, outline=C.INK)
    surf.blit(lab, lab.get_rect(center=(fx + d * 11, fy + 9)))


def draw_goal_front(surf, side, height, highlight=None):
    """Travesaño (delante de todo) con punta redondeada."""
    mouth, x0, x1 = _goal_x(side)
    y = int(goal_bar_y(height))
    t = int(Arena.BAR_THICKNESS)
    a, b = (x0, mouth + t // 2) if side == 0 else (mouth - t // 2, x1)
    bar = pygame.Rect(a, y - t // 2, b - a, t)
    pygame.draw.rect(surf, C.INK, bar.inflate(2 * PX, 2 * PX), border_radius=6)
    pygame.draw.rect(surf, C.WHITE, bar, border_radius=5)
    pygame.draw.rect(surf, C.STRUCT_SHADE, (bar.x, bar.bottom - PX, bar.w, PX))
    if highlight:
        glow = pygame.Surface((bar.w + 16, bar.h + 16), pygame.SRCALPHA)
        glow.fill((*highlight, 70))
        surf.blit(glow, (bar.x - 8, bar.y - 8))
    pygame.draw.rect(surf, C.LINE, (mouth - PX // 2, FLOOR, PX, 10))


# ---------------------------------------------------------------------------
# Pelota pixel art (cuadros por ángulo y tamaño)
# ---------------------------------------------------------------------------
class BallSprite:
    VECTOR_R = 64

    def __init__(self):
        custom = load_override_image("sprites", "pelota.png")
        self.pattern = (pygame.transform.smoothscale(custom, (self.VECTOR_R * 2, self.VECTOR_R * 2))
                        if custom is not None else self._vector_pattern())
        self.frames = {}

    def _vector_pattern(self):
        R = self.VECTOR_R
        s = art.canvas(R * 2, R * 2)
        art.circle(s, (250, 250, 250), (R, R), R)

        def pent(cx, cy, r, rot):
            return [(cx + math.cos(math.radians(rot + k * 72)) * r,
                     cy + math.sin(math.radians(rot + k * 72)) * r) for k in range(5)]
        art.poly(s, C.INK, pent(R, R, R * 0.38, -90))
        for k in range(5):
            a = math.radians(-90 + 36 + k * 72)
            art.poly(s, C.INK, pent(R + math.cos(a) * R * 0.98, R + math.sin(a) * R * 0.98, R * 0.36,
                                    -90 + 36 + k * 72 + 180))
        mask = art.canvas(R * 2, R * 2)
        art.circle(mask, (255, 255, 255), (R, R), R)
        art.clip(s, mask)
        return s

    def frame(self, radius, angle):
        d = max(6, int(round(radius * 2 / PX)))           # diámetro nativo
        abucket = int(angle // 15) % 24
        key = (d, abucket)
        img = self.frames.get(key)
        if img is None:
            R = self.VECTOR_R
            rot = pygame.transform.rotozoom(self.pattern, abucket * 15, 1.0)
            cx, cy = rot.get_width() / 2, rot.get_height() / 2
            crop = rot.subsurface(pygame.Rect(round(cx - R), round(cy - R), 2 * R, 2 * R)).copy()
            # sombreado fijo (no gira con la pelota)
            shade = art.canvas(2 * R, 2 * R)
            art.circle(shade, (0, 0, 0, 60), (R + R * 0.3, R + R * 0.32), R * 0.95)
            m = art.canvas(2 * R, 2 * R)
            art.circle(m, (255, 255, 255), (R, R), R)
            art.clip(shade, m)
            crop.blit(shade, (0, 0))
            art.circle(crop, (255, 255, 255, 200), (R * 0.68, R * 0.62), R * 0.18)
            native = outline_native(pixelize(crop, d), C.INK, 1)
            img = scale_px(native)
            self.frames[key] = img
        return img

    def draw(self, surf, x, y, r, angle):
        img = self.frame(r, angle)
        surf.blit(img, img.get_rect(center=(round(x), round(y))))


_shadows = {}


def draw_shadow(surf, x, width, height_above, alpha=90):
    """Sombra con trama; se achica y aclara con la altura."""
    k = max(0.25, 1 - height_above / 380)
    w = max(4, int(width * k / PX))
    h = max(2, int(w * 0.28))
    a = min(255, int(alpha * k * 1.6))
    key = (w, h, a // 10)
    img = _shadows.get(key)
    if img is None:
        img = scale_px(dither_ellipse(w, h, alpha=a))
        _shadows[key] = img
    surf.blit(img, (round(x - img.get_width() / 2), FLOOR - img.get_height() // 2 + 2))
