"""Personajes en pixel art: cabeza grande + botín que se mueve.

Los sprites (assets/personajes/) miran a la IZQUIERDA; para la derecha se
espejan. El botín cuelga de una "cadera" invisible debajo del centro de la
cabeza: en reposo queda atrás (como en los dibujos originales) y al patear
barre en arco hacia adelante mientras gira. Todo se compone a resolución
nativa y se agranda x2 (retro.PX) sin suavizado.
"""
import json
import math
import os

import pygame

from ..config import PlayerSpec
from . import palette as C
from .assets import ROOT
from .characters import CHARACTERS_BY_ID
from .retro import PX

SPRITE_DIR = os.path.join(ROOT, "assets", "personajes")
HIP = (2.0, 12.0)          # cadera respecto del centro de la cabeza (px nativos, mirando a la izq.)
CANVAS = (84, 76)          # lienzo nativo de composición
ORIGIN = (42, 70)          # posición de la suela dentro del lienzo
FRONT_ANGLE = -40          # desde este ángulo el botín se dibuja delante de la cabeza


def _rot(vx, vy, deg):
    """Rotación en pantalla (y hacia abajo), mismo sentido que pygame.transform.rotate."""
    a = math.radians(deg)
    return vx * math.cos(a) + vy * math.sin(a), -vx * math.sin(a) + vy * math.cos(a)


class CharacterSprites:
    def __init__(self):
        with open(os.path.join(SPRITE_DIR, "sprites.json"), encoding="utf-8") as fh:
            self.meta = json.load(fh)
        self.heads = {}
        for cid, info in self.meta["heads"].items():
            img = pygame.image.load(os.path.join(SPRITE_DIR, info["file"])).convert_alpha()
            self.heads[(cid, -1)] = img
            self.heads[(cid, 1)] = pygame.transform.flip(img, True, False)
        self.boot_angles = sorted(self.meta["boot"]["angles"])
        self.boots = {}
        for ang in self.boot_angles:
            fr = self.meta["boot"]["frames"][str(ang)]
            img = pygame.image.load(os.path.join(SPRITE_DIR, fr["file"])).convert_alpha()
            px, py = fr["pivot"]
            self.boots[(ang, -1)] = (img, (px, py))
            self.boots[(ang, 1)] = (pygame.transform.flip(img, True, False), (img.get_width() - px, py))
        self.cache = {}
        self.portraits = {}
        self.minis = {}
        self._layout = {}

    # ------------------------------------------------------------------ geometría
    def _frame_angle(self, ang):
        return min(self.boot_angles, key=lambda a: abs(a - ang))

    def layout(self, cid):
        """Posiciones nativas (mirando a la izquierda) relativas a la suela."""
        lay = self._layout.get(cid)
        if lay:
            return lay
        info = self.meta["heads"][cid]
        head_c = (0.0, -PlayerSpec.HEAD_OFFSET_Y / PX)
        ax, ay = info["anchor"]
        head_tl = (head_c[0] - ax, head_c[1] - ay)
        bx, by = info["boot_pivot"]
        rest_img, (rpx, rpy) = self.boots[(0, -1)]
        # el tobillo en reposo queda donde lo dibujó el original, pero con la
        # suela apoyada en el piso
        p0 = (head_tl[0] + bx, -(rest_img.get_height() - rpy))
        hip = (head_c[0] + HIP[0], head_c[1] + HIP[1])
        lay = {"head_c": head_c, "head_tl": head_tl, "anchor": (ax, ay),
               "hip": hip, "r0": (p0[0] - hip[0], p0[1] - hip[1])}
        self._layout[cid] = lay
        return lay

    # ------------------------------------------------------------------ composición
    def compose(self, cid, facing, leg_angle=0.0, bob=0, rim=None, frozen=False):
        """Superficie NATIVA del jugador completo (con contorno) y posición de la suela."""
        f = 1 if facing >= 0 else -1
        ang = self._frame_angle(leg_angle)
        key = (cid, f, ang, int(bob), rim, frozen)
        hit = self.cache.get(key)
        if hit:
            return hit
        lay = self.layout(cid)
        canvas = pygame.Surface(CANVAS, pygame.SRCALPHA)
        ox, oy = ORIGIN
        mirror = (lambda x: x) if f == -1 else (lambda x: -x)
        head = self.heads[(cid, f)]
        hx = lay["head_tl"][0] if f == -1 else -(lay["head_tl"][0] + head.get_width())
        head_pos = (ox + hx, oy + lay["head_tl"][1] + bob)
        rx, ry = _rot(lay["r0"][0], lay["r0"][1], ang)
        pivot = (ox + mirror(lay["hip"][0] + rx), oy + lay["hip"][1] + ry + bob * 0.5)
        boot, (bpx, bpy) = self.boots[(ang, f)]     # para la derecha: cuadro espejado
        boot_pos = (round(pivot[0] - bpx), round(pivot[1] - bpy))
        front = ang <= FRONT_ANGLE
        if not front:
            canvas.blit(boot, boot_pos)
        canvas.blit(head, (round(head_pos[0]), round(head_pos[1])))
        if front:
            canvas.blit(boot, boot_pos)
        if frozen:
            ice = pygame.mask.from_surface(canvas, 20).to_surface(setcolor=(150, 215, 255, 120),
                                                                   unsetcolor=(0, 0, 0, 0))
            canvas.blit(ice, (0, 0))
        if rim:
            sil = pygame.mask.from_surface(canvas, 20).to_surface(setcolor=(*rim, 255), unsetcolor=(0, 0, 0, 0))
            out = pygame.Surface(CANVAS, pygame.SRCALPHA)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                out.blit(sil, (dx, dy))
            out.blit(canvas, (0, 0))
            canvas = out
        res = (canvas, ORIGIN)
        if len(self.cache) > 3000:
            self.cache.clear()
        self.cache[key] = res
        return res

    def player(self, cid, facing, leg_angle=0.0, bob=0, rim=None, frozen=False, scale=1.0):
        """Superficie lógica (x2) y posición de la suela dentro de ella."""
        native, (ox, oy) = self.compose(cid, facing, leg_angle, bob, rim, frozen)
        k = PX * scale
        key = ("big", cid, 1 if facing >= 0 else -1, self._frame_angle(leg_angle), int(bob), rim, frozen,
               round(scale, 2))
        big = self.cache.get(key)
        if big is None:
            w, h = native.get_size()
            big = pygame.transform.scale(native, (max(1, round(w * k)), max(1, round(h * k))))
            self.cache[key] = big
        return big, (ox * k, oy * k)

    # ------------------------------------------------------------------ retratos
    def head(self, cid, facing=-1):
        return self.heads[(cid, 1 if facing >= 0 else -1)]

    def mini_head(self, cid, scale=1, facing=-1):
        key = (cid, scale, facing)
        if key not in self.minis:
            h = self.head(cid, facing)
            self.minis[key] = pygame.transform.scale(h, (h.get_width() * scale, h.get_height() * scale))
        return self.minis[key]

    def portrait(self, cid, w=150, h=180):
        """Tarjeta retro: franjas con los colores de la camiseta y la cabeza x3."""
        key = (cid, w, h)
        if key in self.portraits:
            return self.portraits[key]
        ch = CHARACTERS_BY_ID[cid]
        c1, c2 = ch["colors"]
        nw, nh = w // PX, h // PX
        card = pygame.Surface((nw, nh))
        light = tuple(min(255, int(v * 0.35 + 255 * 0.65)) for v in c1)
        light2 = tuple(min(255, int(v * 0.25 + 255 * 0.75)) for v in c2)
        card.fill(light)
        for x in range(-nh, nw, 10):
            pygame.draw.polygon(card, light2, [(x, nh), (x + 5, nh), (x + 5 + nh, 0), (x + nh, 0)])
        pygame.draw.rect(card, c1, (0, nh - 14, nw, 14))
        pygame.draw.rect(card, c2, (0, nh - 14, nw, 2))
        head = self.heads[(cid, -1)]
        hx = (nw - head.get_width()) // 2
        card.blit(head, (hx, 6))
        big = pygame.transform.scale(card, (nw * PX, nh * PX))
        self.portraits[key] = big
        return big

    def warm(self, cid):
        """Precalcula las combinaciones más usadas (evita tirones en el partido)."""
        for f in (-1, 1):
            for ang in self.boot_angles:
                self.compose(cid, f, ang)
