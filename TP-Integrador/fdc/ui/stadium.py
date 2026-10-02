"""Estadio retro: fondo en pixel art, arcos, pelota y sombras.

El fondo se dibuja una vez a resolución nativa (640 x 360) con colores claros
y se agranda x2. Tribunas y público van en tonos pastel apagados para que la
pelota y los jugadores (con contorno) siempre se distingan.

Las medidas del fondo son px NATIVOS (la mitad de la pantalla lógica); las
de arcos, pelota y sombras, px de la pantalla lógica.
"""
import math
import random

import pygame

from ..config import Arena, GAME_NAME, PLAYER_COLORS
from . import art, pixelfont
from . import palette as C
from .assets import load_override_image
from .retro import PX, dither_ellipse, outline_native, pixelize, scale_px

W, H = Arena.WIDTH, Arena.HEIGHT
NW, NH = W // PX, H // PX
FLOOR = Arena.FLOOR_Y
HALF_BAR = Arena.BAR_THICKNESS / 2   # mitad del grosor del travesaño
GRASS_TOP = 252            # borde lejano del césped (nativo)

# --- cielo
STADIUM_SEED = 1986                # semilla del público y del césped: el estadio sale siempre igual
SKY_BOTTOM_Y = 40                  # el degradé del cielo va de y = 0 a 40
# matriz de trama ordenada 4 x 4 (Bayer): decide qué píxeles del degradé toman cada color
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
BAYER_SIZE = 4                     # lado de esa matriz
BAYER_LEVELS = 16                  # niveles de la trama (4 x 4)
CLOUDS = ((40, 8, 36), (230, 4, 28), (430, 10, 40), (580, 6, 24))   # nubes: (x, y, ancho)
CLOUD_PUFFS = ((0, 4, 6), (7, 0, 8), (16, 3, 7), (24, 5, 5))      # bollos de una nube: (dx, dy, radio)
CLOUD_W = 30                       # ancho de nube para el que están medidos esos bollos
CLOUD_SHADE_DROP = 2               # px que baja la sombra de cada bollo
# --- techo
ROOF_TOP, ROOF_BOTTOM = 24, 46     # el techo va de y = 24 a 46
ROOF_EDGE = 4                      # franja en sombra al pie del techo
ROOF_TRUSS = 16                    # px entre las V del reticulado
ROOF_TRUSS_TOP = 1                 # el reticulado arranca 1 px bajo el borde de arriba...
ROOF_TRUSS_BOTTOM = 6              # ...y termina 6 px sobre el pie
ROOF_SHADOW = 10                   # sombra bajo el techo (alto)
COLUMN_X0 = 20                     # primera columna...
COLUMN_EVERY = 120                 # ...y una cada 120 px
COLUMN_W = 3                       # ancho de una columna (con 1 px de luz en el medio)
FLOODLIGHTS = (60, 250, 390, 580)  # x de los reflectores
FLOODLIGHT = (18, 6)               # caja de un reflector (ancho, alto)
LAMPS = 4                          # lámparas por reflector
LAMP_FIRST_X = -7                  # primera lámpara, respecto del centro del reflector
LAMP_STEP = 4                      # px entre lámparas
LAMP_Y = -5                        # lámparas, respecto del borde del techo
LAMP_SIZE = 3                      # px: lado de una lámpara
LAMP_COLOR = (255, 250, 214)       # luz cálida
# --- tribunas
TIERS = ((56, 112), (116, 176), (180, 232))   # tres tribunas: (y de arriba, y de abajo)
TIER_RAIL = 4                      # baranda sobre cada tribuna (alto)
SEAT_ROW = 6                       # alto de cada fila de butacas
CROWD_COLORS = [(236, 170, 160), (170, 200, 236), (250, 226, 150), (180, 222, 180), (236, 236, 240),
                (214, 180, 226), (250, 200, 170), (200, 206, 214)]   # remeras del público (pastel)
SKIN_TONES = [(247, 214, 186), (232, 190, 150), (200, 150, 110), (160, 112, 80)]   # tonos de piel
CROWD_START_MAX = 3                # la primera persona de cada fila arranca entre x = 0 y 3
CROWD_FILL = 0.78                  # probabilidad de que un asiento esté ocupado
ARMS_UP = 0.06                     # probabilidad de que alguien tenga los brazos arriba
CROWD_GAP = (5, 7)                 # px entre una persona y la siguiente (al azar)
BODY = (0, 2, 4, 3)                # cuerpo de una persona (dx, dy, ancho, alto)
HEAD = (1, 0, 2, 2)                # cabeza
ARMS = ((-1, -2, 1, 2), (4, -2, 1, 2))   # brazos levantados
STAIRS_X0 = 64                     # primera escalera...
STAIRS_EVERY = 128                 # ...y una cada 128 px
STAIRS_W = 8                       # ancho de una escalera
STEP_H = 3                         # alto de cada escalón
# --- muro y carteles de publicidad
WALL_Y = 232                       # muro bajo la última tribuna...
WALL_H = 3                         # ...y su alto
BOARD_Y = WALL_Y + WALL_H          # carteles, pegados al muro...
BOARD_H = 17                       # ...hasta el borde del césped
BOARD_TOP_STRIPE = 3               # franja de color de arriba del cartel
BOARD_BOTTOM_STRIPE = 2            # franja de color de abajo
BOARD_TEXT_DROP = 1                # el texto va 1 px por debajo del centro
# --- césped
STRIPE_FAR = 36                    # ancho de las franjas del césped en el fondo...
STRIPE_GROWTH = 20                 # ...que se abren hasta 36 + 20 adelante (perspectiva)
STRIPE_OFFSET = 100                # corre el número de franja para que nunca sea negativo
GRASS_BLADES = 900                 # briznas oscuras sueltas
BLADES_BELOW = 2                   # empiezan 2 px bajo el borde del césped
FAR_LINE = 4                       # línea de cal del fondo: px bajo el borde del césped
NEAR_LINE = 6                      # línea de cal de adelante: px sobre el borde de abajo
CENTER_CIRCLE = (64, 280, 128, 44)  # círculo central (cuánto empieza a la izquierda del centro, y, ancho, alto)
CENTER_SPOT = (1, 301, 3, 2)       # punto central (ídem)
AREA_TOP = 10                      # áreas: px bajo la línea del fondo...
AREA_BOTTOM = 8                    # ...y sobre la línea de adelante
AREA_FAR_W = 58                    # ancho del área en el fondo...
AREA_NEAR_W = 74                   # ...y adelante (perspectiva)

# --- arcos
NET_FILL = (255, 255, 255, 40)     # red: blanco casi transparente...
NET_LINE_COLOR = (255, 255, 255, 150)  # ...con hilos más marcados
NET_CELL = 8                       # px entre hilos de la red
GOAL_SHADOW_H = 5                  # px nativos: alto de la sombra del arco
GOAL_SHADOW_ALPHA = 80             # opacidad de esa sombra
GOAL_SHADOW_RAISE = 6              # px sobre el piso
POST_W = 6                         # px: ancho del poste del fondo
POST_INSET = 6                     # px desde el costado de la pantalla
FLAG_INSET = 24                    # banderita: px desde el costado de la pantalla
FLAG_POLE_H = 34                   # alto del palo sobre el arco
FLAG_W = 30                        # largo del triángulo
FLAG_H = 18                        # alto del triángulo
BAR_RADIUS = 6                     # esquinas redondeadas del contorno del travesaño...
BAR_INNER_RADIUS = 5               # ...y del travesaño
GLOW_MARGIN = 8                    # px que sobresale el brillo del travesaño con un poder
GLOW_ALPHA = 70                    # opacidad de ese brillo
GOAL_LINE_MARK = 10                # px: marca de cal bajo la boca del arco

# --- pelota
BALL_WHITE = (250, 250, 250)       # blanco de la pelota (apenas gris: se distingue de los brillos)
PENTAGON_SIDES = 5                 # parches negros: pentágonos...
PENTAGON_STEP = 72                 # ...con un vértice cada 72 grados
UP_ANGLE = -90                     # grados: vértice hacia arriba
CENTER_PATCH = 0.38                # parche del centro: radio, en fracción del radio de la pelota
PATCH_OFFSET = 36                  # grados: los parches de alrededor van entre los vértices del central
PATCH_DISTANCE = 0.98              # a esta fracción del radio desde el centro
PATCH_SIZE = 0.36                  # radio de esos parches (fracción del radio)
PATCH_FLIP = 180                   # grados: los parches de afuera van al revés del central
MIN_BALL_PX = 6                    # diámetro mínimo de la pelota en px nativos
ANGLE_STEP = 15                    # grados entre cuadros guardados de la pelota girando...
ANGLE_BUCKETS = 24                 # ...24 cuadros = una vuelta
BALL_SHADE = (0, 0, 0, 60)         # sombra fija abajo a la derecha (no gira con la pelota)
SHADE_AT = (0.3, 0.32)             # corrimiento de esa sombra (fracción del radio)
SHADE_R = 0.95                     # radio de esa sombra (fracción del radio)
BALL_SHINE = (255, 255, 255, 200)  # brillo arriba a la izquierda
SHINE_AT = (0.68, 0.62)            # posición del brillo (fracción del radio)
SHINE_R = 0.18                     # radio del brillo (fracción del radio)

# --- sombras en el piso
SHADOW_ALPHA = 90                  # opacidad de una sombra en el piso
SHADOW_MIN_SCALE = 0.25            # la sombra se achica con la altura hasta un cuarto...
SHADOW_FADE_HEIGHT = 380           # ...a esta altura (px)
SHADOW_MIN_W = 4                   # px nativos: ancho mínimo
SHADOW_FLATNESS = 0.28             # alto de la sombra = 28 % de su ancho
SHADOW_BOOST = 1.6                 # la trama se ve más clara: se compensa la opacidad
SHADOW_ALPHA_STEP = 10             # opacidades parecidas comparten la misma imagen guardada
SHADOW_DROP = 2                    # px bajo el piso


def _dither_band(s, y0, y1, c_top, c_bot):
    """Degradé en dos colores con trama ordenada (look 16 bits)."""
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0 - 1)
        for x in range(NW):
            thr = (BAYER[y % BAYER_SIZE][x % BAYER_SIZE] + 0.5) / BAYER_LEVELS
            s.set_at((x, y), c_bot if t > thr else c_top)


def _cloud(s, x, y, w):
    for col, dy0 in ((C.CLOUD_SHADE, CLOUD_SHADE_DROP), (C.CLOUD, 0)):
        for dx, dy, r in CLOUD_PUFFS:
            pygame.draw.circle(s, col, (x + int(dx * w / CLOUD_W), y + dy + dy0), int(r * w / CLOUD_W))


def _at(x, y, rect):
    """Rectángulo (dx, dy, ancho, alto) relativo al punto (x, y)."""
    dx, dy, w, h = rect
    return x + dx, y + dy, w, h


def _roof(s):
    """Techo con reticulado, columnas y reflectores."""
    y0, y1 = ROOF_TOP, ROOF_BOTTOM
    pygame.draw.rect(s, C.ROOF, (0, y0, NW, y1 - y0))
    pygame.draw.rect(s, C.STRUCT_SHADE, (0, y1 - ROOF_EDGE, NW, ROOF_EDGE))
    pygame.draw.line(s, C.STRUCT_DARK, (0, y0), (NW, y0))
    pygame.draw.line(s, C.STRUCT_DARK, (0, y1 - ROOF_EDGE - 1), (NW, y1 - ROOF_EDGE - 1))
    half = ROOF_TRUSS // 2
    for x in range(0, NW + ROOF_TRUSS, ROOF_TRUSS):
        pygame.draw.line(s, C.STRUCT_SHADE, (x, y0 + ROOF_TRUSS_TOP), (x + half, y1 - ROOF_TRUSS_BOTTOM))
        pygame.draw.line(s, C.STRUCT_SHADE, (x + ROOF_TRUSS, y0 + ROOF_TRUSS_TOP), (x + half, y1 - ROOF_TRUSS_BOTTOM))
    pygame.draw.rect(s, C.STRUCT_SHADE, (0, y1, NW, ROOF_SHADOW))      # sombra bajo el techo
    pygame.draw.line(s, C.STRUCT_DARK, (0, y1 + ROOF_SHADOW - 1), (NW, y1 + ROOF_SHADOW - 1))
    for x in range(COLUMN_X0, NW, COLUMN_EVERY):
        pygame.draw.rect(s, C.STRUCT_DARK, (x, y1, COLUMN_W, ROOF_SHADOW))
        pygame.draw.rect(s, C.STRUCT, (x + 1, y1, 1, ROOF_SHADOW))
    fw, fh = FLOODLIGHT
    for x in FLOODLIGHTS:                    # reflectores
        pygame.draw.rect(s, C.STRUCT_DARK, (x - fw // 2, y0 - fh, fw, fh))
        for k in range(LAMPS):
            pygame.draw.rect(s, LAMP_COLOR, (x + LAMP_FIRST_X + k * LAMP_STEP, y0 + LAMP_Y, LAMP_SIZE, LAMP_SIZE))


def _stands(s, rng):
    """Tres tribunas con butacas, público al azar y escaleras."""
    for y0, y1 in TIERS:
        pygame.draw.rect(s, C.STRUCT, (0, y0 - TIER_RAIL, NW, TIER_RAIL))
        pygame.draw.line(s, C.WHITE, (0, y0 - TIER_RAIL), (NW, y0 - TIER_RAIL))
        for row_y in range(y0, y1, SEAT_ROW):
            seat = C.SEAT_RED if (row_y // SEAT_ROW) % 2 == 0 else C.SEAT_RED_DARK
            pygame.draw.rect(s, seat, (0, row_y, NW, SEAT_ROW))
            pygame.draw.line(s, C.SEAT_RED_DARK, (0, row_y + SEAT_ROW - 1), (NW, row_y + SEAT_ROW - 1))
            x = rng.randint(0, CROWD_START_MAX)
            while x < NW:
                if rng.random() < CROWD_FILL:
                    s.fill(rng.choice(CROWD_COLORS), _at(x, row_y, BODY))
                    skin = rng.choice(SKIN_TONES)
                    s.fill(skin, _at(x, row_y, HEAD))
                    if rng.random() < ARMS_UP:          # brazos arriba
                        for arm in ARMS:
                            s.fill(skin, _at(x, row_y, arm))
                x += rng.randint(*CROWD_GAP)
        for x in range(STAIRS_X0, NW, STAIRS_EVERY):             # escaleras
            pygame.draw.rect(s, C.STRUCT, (x, y0, STAIRS_W, y1 - y0))
            for yy in range(y0, y1, STEP_H):
                pygame.draw.line(s, C.STRUCT_SHADE, (x, yy), (x + STAIRS_W - 1, yy))


def _boards(s):
    """Muro y carteles de publicidad."""
    pygame.draw.rect(s, C.STRUCT_SHADE, (0, WALL_Y, NW, WALL_H))
    boards = [(GAME_NAME.upper(), C.BLUE), ("PROGRAMACION CONCURRENTE", C.RED),
              ("PROCESOS  COLAS  EVENTOS", C.GREEN), (GAME_NAME.upper(), C.PURPLE)]
    bw = NW // len(boards)
    for i, (label, col) in enumerate(boards):
        r = pygame.Rect(i * bw, BOARD_Y, bw, BOARD_H)
        pygame.draw.rect(s, C.WHITE, r)
        pygame.draw.rect(s, col, (r.x, r.y, r.w, BOARD_TOP_STRIPE))
        pygame.draw.rect(s, col, (r.x, r.bottom - BOARD_BOTTOM_STRIPE, r.w, BOARD_BOTTOM_STRIPE))
        pygame.draw.line(s, C.STRUCT_DARK, (r.x, r.y), (r.x, r.bottom))
        img = pixelfont.render(label, 1, col)
        s.blit(img, img.get_rect(center=(r.centerx, r.centery + BOARD_TEXT_DROP)))


def _pitch(s, rng):
    """Césped con franjas que se abren hacia adelante (perspectiva) y líneas de cal."""
    for y in range(GRASS_TOP, NH):
        t = (y - GRASS_TOP) / (NH - GRASS_TOP)
        stripe_w = STRIPE_FAR + STRIPE_GROWTH * t
        for x in range(NW):
            k = int((x - NW / 2) / stripe_w + STRIPE_OFFSET)
            s.set_at((x, y), C.GRASS_A if k % 2 == 0 else C.GRASS_B)
    for _ in range(GRASS_BLADES):                          # briznas sueltas
        s.set_at((rng.randrange(NW), rng.randrange(GRASS_TOP + BLADES_BELOW, NH)), C.GRASS_DARK)
    far, near = GRASS_TOP + FAR_LINE, NH - NEAR_LINE      # líneas de cal
    pygame.draw.line(s, C.LINE, (0, far), (NW, far))
    pygame.draw.line(s, C.LINE, (0, near), (NW, near))
    pygame.draw.line(s, C.LINE, (NW // 2, far), (NW // 2, near))
    left, y, w, h = CENTER_CIRCLE
    pygame.draw.ellipse(s, C.LINE, (NW // 2 - left, y, w, h), 1)
    left, y, w, h = CENTER_SPOT
    s.fill(C.LINE, (NW // 2 - left, y, w, h))
    top, bottom = far + AREA_TOP, near - AREA_BOTTOM
    for side in (0, 1):
        def edge(x):
            return x if side == 0 else NW - x
        box = [(edge(0), top), (edge(AREA_FAR_W), top), (edge(AREA_NEAR_W), bottom), (edge(0), bottom)]
        pygame.draw.lines(s, C.LINE, False, box, 1)


def build_background():
    custom = load_override_image("fondos", "estadio.png")
    if custom is not None:
        return pygame.transform.scale(custom, (W, H)).convert()
    rng = random.Random(STADIUM_SEED)
    s = pygame.Surface((NW, NH))
    _dither_band(s, 0, SKY_BOTTOM_Y, C.SKY_TOP, C.SKY_BOTTOM)     # cielo
    for x, y, w in CLOUDS:
        _cloud(s, x, y, w)
    _roof(s)
    _stands(s, rng)
    _boards(s)
    _pitch(s, rng)
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
    net.fill(NET_FILL)
    nw, nh = net.get_size()
    for gx in range(0, nw, NET_CELL):
        net.fill(NET_LINE_COLOR, (gx, 0, PX, nh))
    for gy in range(0, nh, NET_CELL):
        net.fill(NET_LINE_COLOR, (0, gy, nw, PX))
    surf.blit(net, (x0, top))
    sh = dither_ellipse((x1 - x0) // PX, GOAL_SHADOW_H, alpha=GOAL_SHADOW_ALPHA)
    surf.blit(scale_px(sh), (x0, FLOOR - GOAL_SHADOW_RAISE))
    px = POST_INSET if side == 0 else W - POST_INSET - POST_W
    pygame.draw.rect(surf, C.INK, (px - PX, top, POST_W + 2 * PX, FLOOR - top))
    pygame.draw.rect(surf, C.WHITE, (px, top, POST_W, FLOOR - top))
    col = PLAYER_COLORS[side]                     # banderita del dueño del arco
    fx = FLAG_INSET if side == 0 else W - FLAG_INSET
    fy = top - FLAG_POLE_H
    pygame.draw.rect(surf, C.INK, (fx - PX, fy, 2 * PX, top - fy))
    d = 1 if side == 0 else -1
    pts = [(fx, fy), (fx + d * FLAG_W, fy + FLAG_H // 2), (fx, fy + FLAG_H)]
    pygame.draw.polygon(surf, col, pts)
    pygame.draw.polygon(surf, C.INK, pts, PX)


def draw_goal_front(surf, side, height, highlight=None):
    """Travesaño (delante de todo) con punta redondeada."""
    mouth, x0, x1 = _goal_x(side)
    y = int(goal_bar_y(height))
    t = int(Arena.BAR_THICKNESS)
    a, b = (x0, mouth + t // 2) if side == 0 else (mouth - t // 2, x1)
    bar = pygame.Rect(a, y - t // 2, b - a, t)
    pygame.draw.rect(surf, C.INK, bar.inflate(2 * PX, 2 * PX), border_radius=BAR_RADIUS)
    pygame.draw.rect(surf, C.WHITE, bar, border_radius=BAR_INNER_RADIUS)
    pygame.draw.rect(surf, C.STRUCT_SHADE, (bar.x, bar.bottom - PX, bar.w, PX))
    if highlight:
        glow = pygame.Surface((bar.w + 2 * GLOW_MARGIN, bar.h + 2 * GLOW_MARGIN), pygame.SRCALPHA)
        glow.fill((*highlight, GLOW_ALPHA))
        surf.blit(glow, (bar.x - GLOW_MARGIN, bar.y - GLOW_MARGIN))
    pygame.draw.rect(surf, C.LINE, (mouth - PX // 2, FLOOR, PX, GOAL_LINE_MARK))


# ---------------------------------------------------------------------------
# Pelota pixel art (cuadros por ángulo y tamaño)
# ---------------------------------------------------------------------------
class BallSprite:
    VECTOR_R = 64          # px: radio del dibujo de la pelota antes de pasarlo a pixel art

    def __init__(self):
        custom = load_override_image("sprites", "pelota.png")
        self.pattern = (pygame.transform.smoothscale(custom, (self.VECTOR_R * 2, self.VECTOR_R * 2))
                        if custom is not None else self._vector_pattern())
        self.frames = {}

    def _vector_pattern(self):
        R = self.VECTOR_R
        s = art.canvas(R * 2, R * 2)
        art.circle(s, BALL_WHITE, (R, R), R)

        def pent(cx, cy, r, rot):
            return [(cx + math.cos(math.radians(rot + k * PENTAGON_STEP)) * r,
                     cy + math.sin(math.radians(rot + k * PENTAGON_STEP)) * r) for k in range(PENTAGON_SIDES)]
        art.poly(s, C.INK, pent(R, R, R * CENTER_PATCH, UP_ANGLE))
        for k in range(PENTAGON_SIDES):
            rot = UP_ANGLE + PATCH_OFFSET + k * PENTAGON_STEP
            a = math.radians(rot)
            art.poly(s, C.INK, pent(R + math.cos(a) * R * PATCH_DISTANCE, R + math.sin(a) * R * PATCH_DISTANCE,
                                    R * PATCH_SIZE, rot + PATCH_FLIP))
        mask = art.canvas(R * 2, R * 2)
        art.circle(mask, C.WHITE, (R, R), R)
        art.clip(s, mask)
        return s

    def frame(self, radius, angle):
        d = max(MIN_BALL_PX, int(round(radius * 2 / PX)))           # diámetro nativo
        abucket = int(angle // ANGLE_STEP) % ANGLE_BUCKETS
        key = (d, abucket)
        img = self.frames.get(key)
        if img is None:
            R = self.VECTOR_R
            rot = pygame.transform.rotozoom(self.pattern, abucket * ANGLE_STEP, 1.0)
            cx, cy = rot.get_width() / 2, rot.get_height() / 2
            crop = rot.subsurface(pygame.Rect(round(cx - R), round(cy - R), 2 * R, 2 * R)).copy()
            # sombreado fijo (no gira con la pelota)
            shade = art.canvas(2 * R, 2 * R)
            shade_x, shade_y = SHADE_AT
            art.circle(shade, BALL_SHADE, (R + R * shade_x, R + R * shade_y), R * SHADE_R)
            m = art.canvas(2 * R, 2 * R)
            art.circle(m, C.WHITE, (R, R), R)
            art.clip(shade, m)
            crop.blit(shade, (0, 0))
            shine_x, shine_y = SHINE_AT
            art.circle(crop, BALL_SHINE, (R * shine_x, R * shine_y), R * SHINE_R)
            native = outline_native(pixelize(crop, d), C.INK, 1)
            img = scale_px(native)
            self.frames[key] = img
        return img

    def draw(self, surf, x, y, r, angle):
        img = self.frame(r, angle)
        surf.blit(img, img.get_rect(center=(round(x), round(y))))


_shadows = {}


def draw_shadow(surf, x, width, height_above, alpha=SHADOW_ALPHA):
    """Sombra con trama; se achica y aclara con la altura."""
    k = max(SHADOW_MIN_SCALE, 1 - height_above / SHADOW_FADE_HEIGHT)
    w = max(SHADOW_MIN_W, int(width * k / PX))
    h = max(2, int(w * SHADOW_FLATNESS))
    a = min(C.MAX_CHANNEL, int(alpha * k * SHADOW_BOOST))
    key = (w, h, a // SHADOW_ALPHA_STEP)
    img = _shadows.get(key)
    if img is None:
        img = scale_px(dither_ellipse(w, h, alpha=a))
        _shadows[key] = img
    surf.blit(img, (round(x - img.get_width() / 2), FLOOR - img.get_height() // 2 + SHADOW_DROP))
