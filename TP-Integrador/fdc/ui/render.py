"""Dibujo del partido a partir del ÚLTIMO estado recibido de la simulación.

La interfaz no calcula posiciones, goles ni efectos: sólo decide cómo se ven
(qué ángulo tiene el botín, cuánto rebota la cabeza, partículas, textos).
Estilo retro: píxeles de 2x2, fuente pixel art, tablero LED.
"""
import math
from collections import deque

import pygame

from .. import protocol as P
from ..config import (CATEGORY_COLORS, PLAYER_COLORS, PLAYER_LABELS, POWERS_BY_ID,
                      PlayerSpec, PowerRules)
from . import palette as C
from . import pixelfont
from .assets import draw_text
from .characters import CHARACTERS_BY_ID, short_name
from .icons import power_icon
from .retro import bevel_box, scale_px
from .stadium import FLOOR, draw_goal_back, draw_goal_front, draw_shadow

TARGET_LABELS = {"p0": "J1", "p1": "J2", "goal0": "ARCO J1", "goal1": "ARCO J2", "ball": "PELOTA"}


def fmt_clock(secs):
    secs = max(0, int(math.ceil(secs - 1e-6)))
    return f"{secs // 60:01d}:{secs % 60:02d}"


def kick_angle(prog):
    """Ángulo del botín durante la patada (0 = reposo; negativo = hacia adelante)."""
    if prog < 0.15:
        return 25 * prog / 0.15
    if prog < 0.45:
        return 25 - 125 * (prog - 0.15) / 0.30
    if prog < 0.70:
        return -100
    return -100 + 100 * (prog - 0.70) / 0.30


def timer_bar(surf, x, y, w, frac, color):
    """Barra de tiempo restante estilo retro."""
    pygame.draw.rect(surf, C.INK, (x, y, w, 6))
    pygame.draw.rect(surf, C.CREAM_DARK, (x + 2, y + 2, w - 4, 2))
    fill = int((w - 4) * max(0.0, min(1.0, frac)))
    if fill > 0:
        pygame.draw.rect(surf, color, (x + 2, y + 2, fill, 2))


class MatchRenderer:
    def __init__(self, app, characters, labels=PLAYER_LABELS):
        self.app = app
        self.labels = tuple(labels)
        self.sprites = app.sprites
        self.ball_sprite = app.ball_sprite
        self.background = app.background
        self.chars = list(characters)
        self.t = 0.0
        self.trail = deque(maxlen=6)
        self.kickoff_flash = 0.0
        self.goal_banner = None      # (tiempo restante, datos del gol)
        self.golden_flash = 0.0

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

    # ------------------------------------------------------------------ mundo
    def draw_world(self, surf, st, offset=(0, 0)):
        surf.blit(self.background, offset)
        goals = st["goals"]
        for side in (0, 1):
            draw_goal_back(surf, side, goals[side], self.labels)
        for b in st.get("bombs", []):
            self._bomb(surf, b)
        if st.get("pickup"):
            self._pickup(surf, st["pickup"])
        ball = st["ball"]
        draw_shadow(surf, ball["x"], ball["r"] * 2.4, FLOOR - ball["y"] - ball["r"])
        for p in st["players"]:
            draw_shadow(surf, p["x"], 84 * p["scale"], FLOOR - p["y"], 110)
        for i in sorted(range(2), key=lambda k: st["players"][k]["y"]):
            self._player(surf, i, st["players"][i], st)
        self._ball(surf, ball, st)
        for side in (0, 1):
            hl = None
            for e in st.get("effects", []):
                if e["target"] == f"goal{side}":
                    hl = CATEGORY_COLORS[POWERS_BY_ID[e["power"]].category]
            draw_goal_front(surf, side, goals[side], hl)

    def pose(self, i, p, phase):
        """(ángulo del botín, rebote de la cabeza en px nativos)."""
        t = self.t
        if p["frozen"]:
            return 0, 0
        if p["celebrate"] and phase in (P.PHASE_GOAL, P.PHASE_FINISHED):
            return -50 + 50 * math.sin(t * 14), -int(abs(math.sin(t * 7)) * 6)
        if p["kick"] >= 0:
            return kick_angle(p["kick"]), 0
        if not p["ground"]:
            return (-30, 0) if p["vy"] < 0 else (10, 0)
        if abs(p["vx"]) > 25:
            ph = p["stride"] / 14.0
            return 22 * math.sin(ph), (-1 if abs(math.cos(ph)) > 0.8 else 0)
        return 0, (-1 if (t * 1.6 + i * 0.5) % 2 < 1 else 0)

    def _player(self, surf, i, p, st):
        f = 1 if p["facing"] >= 0 else -1
        ang, bob = self.pose(i, p, st["phase"])
        img, (fx, fy) = self.sprites.player(self.chars[i], f, ang, bob, PLAYER_COLORS[i],
                                            p["frozen"], p["scale"])
        surf.blit(img, (round(p["x"] - fx), round(p["y"] - fy)))
        s = p["scale"]
        mine = [e for e in st.get("effects", []) if e["target"] == f"p{i}"]
        props = {POWERS_BY_ID[e["power"]].prop: e for e in mine}
        if p["frozen"]:
            self._ice(surf, p)
        if "no_kick" in props:
            bx, by = int(p["x"] - f * 8) // 2 * 2, int(p["y"] - 14)
            pygame.draw.rect(surf, C.INK, (bx - 8, by - 8, 16, 16))
            pygame.draw.rect(surf, C.WHITE, (bx - 6, by - 6, 12, 12))
            pygame.draw.rect(surf, C.RED, (bx - 4, by - 2, 8, 4))
            pygame.draw.rect(surf, C.RED, (bx - 2, by - 4, 4, 8))
        if "speed" in props and abs(p["vx"]) > 60:
            col = CATEGORY_COLORS[POWERS_BY_ID[props["speed"]["power"]].category]
            d = -1 if p["vx"] > 0 else 1
            for k, hh in enumerate((24, 50, 76)):
                x0 = p["x"] + d * (44 + k * 6) * s
                ln = int(18 + 8 * math.sin(self.t * 20 + k)) // 2 * 2
                pygame.draw.rect(surf, col, (min(x0, x0 + d * ln), p["y"] - hh * s, ln, 4))
        if "jump" in props:
            col = CATEGORY_COLORS[POWERS_BY_ID[props["jump"]["power"]].category]
            r = pygame.Rect(0, 0, int(70 * s), 14)
            r.center = (p["x"], FLOOR + 2)
            pygame.draw.ellipse(surf, col, r, 4)
        if 0.12 <= p["kick"] <= 0.75:
            self._kick_arc(surf, p, f)
        top = p["y"] - (PlayerSpec.HEAD_OFFSET_Y + PlayerSpec.HEAD_RADIUS) * s - 12
        self._indicator(surf, p["x"], top, i, st.get("last_touch") == i)
        for k, e in enumerate(mine):
            cx = p["x"] + (k - (len(mine) - 1) / 2) * 30
            self._mini_effect(surf, e, (cx, top - 40))

    def _indicator(self, surf, x, y, i, last):
        col = PLAYER_COLORS[i]
        x = int(x) // 2 * 2
        pygame.draw.polygon(surf, C.INK, [(x - 10, y - 12), (x + 10, y - 12), (x, y + 2)])
        pygame.draw.polygon(surf, col, [(x - 6, y - 10), (x + 6, y - 10), (x, y - 2)])
        lab = pixelfont.render(self.labels[i], 2, C.WHITE, outline=C.INK)
        r = lab.get_rect(midbottom=(x, y - 12))
        surf.blit(lab, r)
        if last:
            ball = self.ball_sprite.frame(10, 0)
            surf.blit(ball, ball.get_rect(midleft=(r.right + 4, r.centery)))

    def _mini_effect(self, surf, e, center):
        icon = power_icon(e["power"], 28)
        r = icon.get_rect(center=(round(center[0]), round(center[1])))
        surf.blit(icon, r)
        col = CATEGORY_COLORS[POWERS_BY_ID[e["power"]].category]
        timer_bar(surf, r.left, r.bottom + 2, r.width, e["left"] / max(0.001, e["dur"]), col)

    def _ice(self, surf, p):
        s = p["scale"]
        r = pygame.Rect(0, 0, int(96 * s) // 2 * 2, int((PlayerSpec.HEIGHT + 12) * s) // 2 * 2)
        r.midbottom = (p["x"], p["y"] + 4)
        ice = pygame.Surface(r.size, pygame.SRCALPHA)
        ice.fill((170, 225, 255, 80))
        pygame.draw.rect(ice, (240, 250, 255, 230), ice.get_rect(), 4)
        for k in range(3):
            x = int(r.width * (0.2 + 0.25 * k)) // 2 * 2
            for j in range(6):
                ice.fill((255, 255, 255, 180), (x - j * 2, 10 + j * 4, 2, 4))
        surf.blit(ice, r)

    def _kick_arc(self, surf, p, f):
        """Alcance visible de la patada: arco de píxeles blancos."""
        s = p["scale"]
        cx, cy = p["x"], p["y"] - 20 * s
        R = (PlayerSpec.KICK_REACH_X + PlayerSpec.KICK_RADIUS * 0.6) * s
        prog = min(1.0, (p["kick"] - 0.12) / 0.4)
        for k in range(7):
            a = math.radians(-10 + 110 * prog * k / 6)
            x = cx + math.sin(a) * R * f
            y = cy + math.cos(a) * R
            sz = 2 + (k * 2) // 3 * 2
            surf.fill(C.WHITE, (int(x) // 2 * 2 - sz // 2, int(y) // 2 * 2 - sz // 2, sz, sz))

    def _ball(self, surf, ball, st):
        sp = math.hypot(ball["vx"], ball["vy"])
        self.trail.append((ball["x"], ball["y"], ball["r"]))
        if sp > 560:
            pts = list(self.trail)[:-1]
            for k, (x, y, r) in enumerate(pts):
                sz = max(2, int(r * (0.4 + 0.6 * k / max(1, len(pts)))) // 2 * 2)
                layer = pygame.Surface((sz, sz), pygame.SRCALPHA)
                layer.fill((255, 255, 255, 70 + 20 * k))
                surf.blit(layer, (int(x - sz / 2), int(y - sz / 2)))
        for e in st.get("effects", []):
            if e["target"] == "ball":
                col = CATEGORY_COLORS[POWERS_BY_ID[e["power"]].category]
                pygame.draw.circle(surf, col, (int(ball["x"]), int(ball["y"])), int(ball["r"] + 6), 2)
        self.ball_sprite.draw(surf, ball["x"], ball["y"], ball["r"], ball["angle"])

    def _pickup(self, surf, pk):
        pdef = POWERS_BY_ID[pk["power"]]
        col = CATEGORY_COLORS[pdef.category]
        bob = 2 * round(math.sin(self.t * 3.2))
        x, y = int(pk["x"]), int(pk["y"] + bob)
        r = PowerRules.PICKUP_RADIUS
        blink = pk["ttl"] < 1.5 and int(self.t * 8) % 2 == 0
        if not blink:
            pygame.draw.circle(surf, col, (x, y), r + 6, 2)
            icon = power_icon(pk["power"], r * 2)
            surf.blit(icon, icon.get_rect(center=(x, y)))
        timer_bar(surf, x - r, y + r + 6, 2 * r, pk["ttl"] / pk["ttl_max"], col)
        lab = pixelfont.render(pdef.label, 2, C.WHITE, outline=C.INK)
        surf.blit(lab, lab.get_rect(midtop=(x, y + r + 14)))

    def _bomb(self, surf, b):
        x, y = int(b["x"]), int(b["y"])
        frac = b["fuse"] / b["fuse_max"]
        R = PowerRules.BOMB_BLAST_RADIUS
        on = int(self.t * (8 + 16 * (1 - frac))) % 2 == 0
        n = 40
        for k in range(n):
            if (k + int(self.t * 10)) % 2:
                a = 2 * math.pi * k / n
                surf.fill(C.RED, (int(x + math.cos(a) * R) // 2 * 2, int(y + math.sin(a) * R) // 2 * 2, 4, 4))
        pygame.draw.circle(surf, C.INK, (x, y), 20)
        pygame.draw.circle(surf, C.RED if on else C.INK, (x, y), 16)
        surf.fill(C.WHITE, (x - 8, y - 8, 4, 4))
        pygame.draw.rect(surf, C.INK, (x + 6, y - 22, 6, 8))
        surf.fill((255, 220, 90) if on else C.ORANGE, (x + 10, y - 28, 6, 6))
        lab = pixelfont.render(f"{b['fuse']:.1f}", 2, C.WHITE, outline=C.INK)
        surf.blit(lab, lab.get_rect(midbottom=(x, y - 30)))

    # ------------------------------------------------------------------ HUD
    def draw_hud(self, surf, st):
        board = pygame.Rect(0, 0, 500, 92)
        board.midtop = (640, 4)
        pygame.draw.rect(surf, C.INK, board.move(6, 6))
        pygame.draw.rect(surf, C.STRUCT_DARK, board)
        pygame.draw.rect(surf, C.INK, board, 4)
        led_area = board.inflate(-16, -16)
        pygame.draw.rect(surf, C.LED_BG, led_area)
        for i in (0, 1):
            ch = CHARACTERS_BY_ID[self.chars[i]]
            head = self.sprites.mini_head(ch["id"], 1, 1 if i == 0 else -1)
            plate = pygame.Rect(0, 0, 56, 60)
            if i == 0:
                plate.midleft = (led_area.left + 6, led_area.centery)
            else:
                plate.midright = (led_area.right - 6, led_area.centery)
            pygame.draw.rect(surf, PLAYER_COLORS[i], plate)
            pygame.draw.rect(surf, C.INK, plate, 2)
            surf.blit(head, head.get_rect(center=plate.center))
            score = pixelfont.render_led(str(st["score"][i]), 7, C.LED_ON, C.LED_OFF)
            sx = led_area.centerx - 118 if i == 0 else led_area.centerx + 118
            surf.blit(score, score.get_rect(center=(sx, led_area.centery - 4)))
        low = st["clock"] <= 10 and st["phase"] == P.PHASE_PLAYING and int(self.t * 4) % 2 == 0
        golden = st.get("golden")
        clock = pixelfont.render_led("ORO" if golden else fmt_clock(st["clock"]), 6,
                                     C.LED_ON_2 if (low or golden) else C.LED_ON, C.LED_OFF)
        surf.blit(clock, clock.get_rect(center=(led_area.centerx, led_area.centery - 6)))
        state_txt = {P.PHASE_COUNTDOWN: "PREPARADOS", P.PHASE_PLAYING: "EN JUEGO",
                     P.PHASE_GOAL: "GOL", P.PHASE_FINISHED: "FINAL"}[st["phase"]]
        if st.get("golden") and st["phase"] in (P.PHASE_PLAYING, P.PHASE_COUNTDOWN):
            state_txt = "GOL DE ORO"
        if st["paused"]:
            state_txt = "EN PAUSA"
        lab = scale_px(pixelfont.render(state_txt, 1, (180, 190, 200)))
        surf.blit(lab, lab.get_rect(center=(led_area.centerx, led_area.bottom - 10)))
        for i in (0, 1):                          # carteles con los nombres
            ch = CHARACTERS_BY_ID[self.chars[i]]
            name = pixelfont.render(f"{self.labels[i]} {short_name(ch).upper()}", 2, C.WHITE, outline=C.INK)
            r = name.get_rect()
            if i == 0:
                r.topright = (board.left - 12, board.top + 8)
            else:
                r.topleft = (board.right + 12, board.top + 8)
            bevel_box(surf, r.inflate(14, 10), PLAYER_COLORS[i])
            surf.blit(name, r)
        # efectos activos: J1 a la izquierda, J2 a la derecha, pelota en el centro
        cols = {0: [], 1: [], "c": []}
        for e in st.get("effects", []):
            t = e["target"]
            cols[0 if t in ("p0", "goal0") else 1 if t in ("p1", "goal1") else "c"].append(e)
        for k, e in enumerate(cols[0]):
            self._hud_effect(surf, e, (board.left - 190, board.top + 46 + k * 46))
        for k, e in enumerate(cols[1]):
            self._hud_effect(surf, e, (board.right + 12, board.top + 46 + k * 46))
        for k, e in enumerate(cols["c"]):
            self._hud_effect(surf, e, (board.centerx - 89, board.bottom + 12 + k * 46))

    def _hud_effect(self, surf, e, topleft):
        pdef = POWERS_BY_ID[e["power"]]
        col = CATEGORY_COLORS[pdef.category]
        inner = bevel_box(surf, pygame.Rect(topleft, (178, 40)), C.CREAM)
        surf.blit(power_icon(e["power"], 28), (inner.left + 2, inner.top + 2))
        draw_text(surf, TARGET_LABELS.get(e["target"], ""), 16, (inner.left + 36, inner.top + 4),
                  C.INK, anchor="topleft", outline=None)
        draw_text(surf, f"{max(0.0, e['left']):.1f}s", 16, (inner.right - 4, inner.top + 4), col,
                  anchor="topright", outline=C.INK)
        timer_bar(surf, inner.left + 36, inner.bottom - 10, inner.width - 40,
                  e["left"] / max(0.001, e["dur"]), col)

    def draw_center_messages(self, surf, st):
        """Cuenta regresiva, ¡YA!, gol."""
        if st["phase"] == P.PHASE_COUNTDOWN and not st["paused"]:
            n = max(1, math.ceil(st["phase_left"]))
            frac = st["phase_left"] - math.floor(st["phase_left"])
            draw_text(surf, str(n), 96 + int(32 * frac) // 8 * 8, (640, 330), C.GOLD, kind="title",
                      outline=C.INK, shadow=True)
        if self.kickoff_flash > 0:
            draw_text(surf, "¡YA!", 104, (640, 330), C.WHITE, kind="title", outline=C.INK, shadow=True)
        if self.golden_flash > 0:
            draw_text(surf, "¡GOL DE ORO!", 72, (640, 186), C.GOLD, kind="title", outline=C.INK, shadow=True)
            draw_text(surf, "Empate: el próximo gol gana", 24, (640, 240), C.INK, outline=C.WHITE)
        if self.goal_banner:
            left, g = self.goal_banner
            col = PLAYER_COLORS[g["scorer"]]
            band = pygame.Rect(0, 262, 1280, 132)
            pygame.draw.rect(surf, C.INK, band)
            pygame.draw.rect(surf, C.CREAM, band.inflate(0, -12))
            pygame.draw.rect(surf, col, (0, band.top + 6, 1280, 6))
            pygame.draw.rect(surf, col, (0, band.bottom - 12, 1280, 6))
            wob = 4 if int(self.t * 8) % 2 else 0
            draw_text(surf, "¡GOOOL!", 80, (640, 312 - wob), col, kind="title", outline=C.INK, shadow=True)
            ch = CHARACTERS_BY_ID[self.chars[g["scorer"]]]
            sub = f"{self.labels[g['scorer']]} - {short_name(ch)}"
            if g.get("own_goal"):
                sub += "  (en contra)"
            draw_text(surf, sub, 24, (640, 368), C.INK, outline=None)
