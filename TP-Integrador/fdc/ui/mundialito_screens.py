"""Pantallas del Mundialito (1 jugador contra la computadora, sólo local).

Flujo:  elegir personaje -> llave del torneo -> partido -> resultado -> ...
El progreso vive en app.tournament mientras el juego está abierto:
  * terminar un partido e ir al menú NO pierde el progreso (se continúa desde
    "Jugar > Mundialito");
  * ir al menú desde la PAUSA de un partido es abandonar: se pierde el torneo.
"""
import math
import random

import pygame

from .. import protocol as P
from ..bot import LEVELS, Bot
from ..config import PLAYER_COLORS
from ..mundialito import BOT_SLOT, CHAMPION, ELIMINATED, GROUP_STAGES, HUMAN_SLOT, STAGES, Tournament, ordinal
from . import palette as C
from . import pixelfont
from .assets import draw_text
from .characters import CHARACTER_IDS, CHARACTERS_BY_ID, short_name
from .match_screens import MatchScreen
from .retro import bevel_box
from .screens import BACK_KEYS, Menu, MenuScreen, Screen, button, dim, footer, panel, title

LABELS = ("CPU", "VOS")          # la persona juega a la derecha (lugar 1)


def open_mundialito(app):
    """Entrada desde "Jugar": continúa el torneo en curso o empieza uno nuevo."""
    t = getattr(app, "tournament", None)
    if t is not None and not t.finished:
        app.switch(HubScreen(app))
    else:
        app.tournament = None
        app.switch(PickScreen(app))


def draw_trophy(surf, center, k=4):
    """Copa del Mundo en pixel art (dibujada a resolución nativa y agrandada)."""
    s = pygame.Surface((26, 44), pygame.SRCALPHA)
    gold, gold_d, gold_l, green = (240, 190, 40), (190, 135, 20), (255, 236, 140), (40, 140, 70)
    pygame.draw.circle(s, gold_d, (13, 9), 8)                     # globo
    pygame.draw.circle(s, gold, (13, 9), 7)
    pygame.draw.line(s, gold_d, (6, 9), (20, 9))
    pygame.draw.line(s, gold_d, (13, 2), (13, 16))
    s.fill(gold_l, (9, 4, 3, 2))
    pygame.draw.polygon(s, gold, [(7, 15), (19, 15), (16, 30), (10, 30)])   # cuerpo
    pygame.draw.polygon(s, gold_d, [(7, 15), (19, 15), (16, 30), (10, 30)], 1)
    for y in (19, 23, 27):                                        # espirales
        pygame.draw.line(s, gold_d, (9, y), (17, y - 2))
    s.fill(gold_l, (11, 17, 1, 10))
    pygame.draw.rect(s, gold, (7, 30, 12, 3))                     # base
    pygame.draw.rect(s, green, (6, 33, 14, 3))
    pygame.draw.rect(s, gold, (6, 36, 14, 2))
    pygame.draw.rect(s, green, (5, 38, 16, 3))
    pygame.draw.rect(s, gold_d, (5, 41, 16, 2))
    img = pygame.transform.scale(s, (26 * k, 44 * k))
    surf.blit(img, img.get_rect(center=center))


# ---------------------------------------------------------------------------
# Elegir personaje (una persona)
# ---------------------------------------------------------------------------
class PickScreen(Screen):
    CARD_W, CARD_H, GAP = 150, 168, 14

    def __init__(self, app):
        super().__init__(app)
        last = app.last_characters[1] if app.last_characters else CHARACTER_IDS[0]
        self.cursor = CHARACTER_IDS.index(last)
        self.ok_rect = pygame.Rect(0, 0, 220, 48)
        self.ok_rect.center = (1030, 426)
        self.hover_ok = False

    def card_rect(self, k):
        total = len(CHARACTER_IDS) * self.CARD_W + (len(CHARACTER_IDS) - 1) * self.GAP
        return pygame.Rect(640 - total / 2 + k * (self.CARD_W + self.GAP), 508, self.CARD_W, self.CARD_H)

    def move(self, d):
        self.cursor = (self.cursor + d) % len(CHARACTER_IDS)
        self.app.audio.play("select")

    def confirm(self):
        self.app.audio.play("confirm")
        cid = CHARACTER_IDS[self.cursor]
        self.app.tournament = Tournament(cid, random.Random(self.app.options.seed))
        self.app.switch(HubScreen(self.app))

    def handle_event(self, ev):
        if ev.type == pygame.KEYDOWN:
            if ev.key in BACK_KEYS:
                from .screens import PlayMenuScreen
                self.app.audio.play("back")
                self.app.switch(PlayMenuScreen(self.app))
            elif ev.key in (pygame.K_a, pygame.K_LEFT):
                self.move(-1)
            elif ev.key in (pygame.K_d, pygame.K_RIGHT):
                self.move(1)
            elif ev.key in (pygame.K_SPACE, pygame.K_p, pygame.K_RETURN, pygame.K_KP_ENTER):
                self.confirm()
        elif ev.type == pygame.MOUSEMOTION:
            self.hover_ok = self.ok_rect.collidepoint(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.ok_rect.collidepoint(ev.pos):
                self.confirm()
                return
            for k in range(len(CHARACTER_IDS)):
                if self.card_rect(k).collidepoint(ev.pos):
                    self.cursor = k
                    self.app.audio.play("select")

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, 120)
        title(surf, "MUNDIALITO", (640, 40), 56)
        draw_text(surf, "Elegí tu personaje: vas a enfrentar a los otros 6, uno por uno.", 16, (640, 88),
                  C.INK, outline=C.WHITE)
        info = pygame.Rect(70, 120, 640, 290)
        inner = panel(surf, info)
        lines = ["Sólo avanzás si ganás. Si perdés, quedás eliminado.",
                 "Cada rival es más difícil que el anterior.",
                 "Si el partido termina empatado: gol de oro.",
                 "Jugás a la DERECHA: valen A/D/W + Espacio",
                 "y también las flechas + P."]
        for i, ln in enumerate(lines):
            draw_text(surf, ln, 16, (inner.left + 12, inner.top + 10 + i * 26), C.INK, anchor="topleft", outline=None)
        for i, st in enumerate(STAGES):
            col = C.GREEN if i < GROUP_STAGES else (C.RED if i == len(STAGES) - 1 else C.BLUE)
            r = pygame.Rect(inner.left + 12 + (i % 3) * 200, inner.top + 150 + (i // 3) * 54, 190, 44)
            bevel_box(surf, r, C.CREAM, shadow=False)
            pygame.draw.rect(surf, col, (r.left + 2, r.top + 2, 6, r.height - 4))
            draw_text(surf, st, 16, (r.left + 16, r.centery), C.INK, anchor="midleft", outline=None)
        cid = CHARACTER_IDS[self.cursor]
        ped = pygame.Rect(0, 0, 200, 18)
        ped.midtop = (1030, 372)
        bevel_box(surf, ped, C.STRUCT)
        bob = -1 if (self.t * 1.6) % 2 < 1 else 0
        img, (fx, fy) = self.app.sprites.player(cid, -1, 0, bob, PLAYER_COLORS[HUMAN_SLOT], False, 1.9)
        surf.blit(img, (1030 - fx, 376 - fy))
        draw_text(surf, short_name(CHARACTERS_BY_ID[cid]).upper(), 32, (1030, 132), C.GOLD, kind="title",
                  outline=C.INK, shadow=True)
        button(surf, self.ok_rect, "¡A JUGAR!", self.hover_ok, True, 24, self.t)
        for k, c in enumerate(CHARACTER_IDS):
            r = self.card_rect(k)
            rr = r.move(0, -8 if k == self.cursor else 0)
            pygame.draw.rect(surf, C.INK, rr.move(6, 6))
            surf.blit(self.app.sprites.portrait(c), rr)
            pygame.draw.rect(surf, C.INK, rr, 4)
            draw_text(surf, short_name(CHARACTERS_BY_ID[c]).upper(), 16, (rr.centerx, rr.bottom - 14), C.WHITE,
                      outline=C.INK)
            if k == self.cursor:
                pygame.draw.rect(surf, PLAYER_COLORS[HUMAN_SLOT], rr.inflate(12, 12), 6)
        footer(surf, "A/D o flechas: elegir  -  Espacio, P o Enter: confirmar  -  Esc: volver  -  Mouse: clic")


# ---------------------------------------------------------------------------
# Llave del torneo
# ---------------------------------------------------------------------------
class HubScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        t = app.tournament
        self.menu = Menu([(f"Jugar {t.stage_name}", self.play), ("Menú principal", self.to_menu),
                          ("Abandonar Mundialito", self.abandon)], (640, 560), width=420, height=50, gap=10)

    def play(self):
        self.app.switch(MundialitoMatchScreen(self.app, self.app.tournament))

    def to_menu(self):
        self.app.switch(MenuScreen(self.app))       # el progreso queda guardado

    def abandon(self):
        self.app.tournament = None
        self.app.switch(MenuScreen(self.app))

    def handle_event(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key in BACK_KEYS:
            self.app.audio.play("back")
            self.to_menu()
            return
        self.menu.handle_event(ev, self.app.audio)

    def update(self, dt):
        super().update(dt)
        self.menu.update(dt)

    def draw(self, surf):
        t = self.app.tournament
        surf.blit(self.app.background, (0, 0))
        dim(surf, 120)
        title(surf, "MUNDIALITO", (640, 40), 56)
        me = CHARACTERS_BY_ID[t.player]
        draw_text(surf, f"Jugás con {short_name(me)}  -  Próximo: {t.stage_name} contra "
                        f"{short_name(CHARACTERS_BY_ID[t.rival])} (dificultad {LEVELS[t.level]['name']})",
                  16, (640, 86), C.INK, outline=C.WHITE)
        w, gap = 186, 20
        x0 = 640 - (6 * w + 5 * gap) / 2
        for i, (stage, rival) in enumerate(zip(STAGES, t.rivals)):
            r = pygame.Rect(x0 + i * (w + gap), 140, w, 300)
            current = i == t.stage
            done = i < len(t.results)
            face = C.GOLD if current else (C.CREAM if done or i < t.stage else C.CREAM_DARK)
            inner = bevel_box(surf, r.move(0, -6 if current and int(self.t * 3) % 2 else 0), face)
            group = "GRUPOS" if i < GROUP_STAGES else "ELIMINACIÓN"
            draw_text(surf, group, 16, (inner.centerx, inner.top + 12), C.INK_SOFT, outline=None)
            draw_text(surf, stage, 16, (inner.centerx, inner.top + 36), C.INK, outline=None)
            portrait = self.app.sprites.portrait(rival)
            pr = portrait.get_rect(midtop=(inner.centerx, inner.top + 58))
            surf.blit(portrait, pr)
            pygame.draw.rect(surf, C.INK, pr, 4)
            if not done and not current:
                veil = pygame.Surface(pr.size, pygame.SRCALPHA)
                veil.fill((255, 255, 255, 120))
                surf.blit(veil, pr)
            draw_text(surf, short_name(CHARACTERS_BY_ID[rival]).upper(), 16, (inner.centerx, pr.bottom + 14),
                      C.INK, outline=None)
            if done:
                _, _, mine, theirs = t.results[i]
                draw_text(surf, f"GANADO {mine}-{theirs}", 16, (inner.centerx, inner.bottom - 14), C.GREEN,
                          outline=C.INK)
            elif current:
                draw_text(surf, "PRÓXIMO", 16, (inner.centerx, inner.bottom - 14), C.RED, outline=C.WHITE)
        draw_trophy(surf, (1196, 560), 2)
        self.menu.draw(surf)
        footer(surf, "Ir al menú guarda tu progreso.  Abandonar lo descarta.")


# ---------------------------------------------------------------------------
# Partido del Mundialito
# ---------------------------------------------------------------------------
class MundialitoMatchScreen(MatchScreen):
    labels = LABELS

    def __init__(self, app, tournament):
        self.tournament = tournament
        chars = [None, None]
        chars[BOT_SLOT] = tournament.rival
        chars[HUMAN_SLOT] = tournament.player
        super().__init__(app, chars)
        seed = app.options.seed if app.options.seed is not None else random.randrange(10 ** 9)
        self.bot = Bot(BOT_SLOT, tournament.level, seed + tournament.stage)
        self._dt = 1 / 60

    # ganchos
    def pause_items(self):
        return [("Continuar", self.resume), ("Abandonar Mundialito", self.abandon)]

    def extra_payload(self):
        return {"golden_goal": True}

    def controls(self, active):
        out = [None, None]
        out[HUMAN_SLOT] = self.app.input.snapshot_single(active)
        out[BOT_SLOT] = self.bot.controls(self.state, self._dt)
        return out

    def update(self, dt):
        self._dt = dt
        super().update(dt)

    def on_match_over(self):
        score = self.end_info["score"]
        won = self.tournament.record(score[HUMAN_SLOT], score[BOT_SLOT])
        self.app.switch(MundialitoResultScreen(self.app, self.tournament, score, won))

    def abandon(self):
        """Ir al menú desde la pausa de un partido = abandonar el Mundialito."""
        self.app.tournament = None
        self._send(P.CMD_END)
        self.app.switch(MenuScreen(self.app))

    def draw(self, surf):
        super().draw(surf)
        if self.state is not None and self.pause_state is None:
            t = self.tournament
            r = pygame.Rect(0, 0, 330, 34)
            r.midbottom = (640, 714)
            inner = bevel_box(surf, r, C.CREAM, shadow=False)
            draw_text(surf, f"MUNDIALITO - {t.stage_name.upper()}", 16, inner.center, C.INK, outline=None)


# ---------------------------------------------------------------------------
# Resultado de cada partido
# ---------------------------------------------------------------------------
class MundialitoResultScreen(Screen):
    def __init__(self, app, tournament, score, won):
        super().__init__(app)
        self.t_ = tournament
        self.score = score
        self.won = won
        self.confetti_t = 0.0
        if tournament.status == CHAMPION:
            items = [("Jugar otro Mundialito", self.again), ("Menú principal", self.to_menu)]
            app.tournament = None
        elif tournament.status == ELIMINATED:
            items = [("Empezar de nuevo", self.again), ("Menú principal", self.to_menu)]
            app.tournament = None
        else:
            items = [("Siguiente partido", self.next_match), ("Menú principal", self.to_menu)]
        self.menu = Menu(items, (640, 590), width=420, height=50, gap=10)

    def enter(self):
        self.app.audio.crowd(False)
        self.app.fx.clear()
        if self.t_.status == CHAMPION:
            self.app.audio.play("goal")

    def next_match(self):
        self.app.switch(MundialitoMatchScreen(self.app, self.t_))

    def again(self):
        self.app.switch(PickScreen(self.app))

    def to_menu(self):
        self.app.switch(MenuScreen(self.app))       # si el torneo sigue, queda guardado

    def handle_event(self, ev):
        self.menu.handle_event(ev, self.app.audio)

    def update(self, dt):
        super().update(dt)
        self.menu.update(dt)
        self.app.fx.update(dt)
        if self.won:
            self.confetti_t -= dt
            if self.confetti_t <= 0:
                self.confetti_t = 1.2
                self.app.fx.confetti(640, 300, [PLAYER_COLORS[HUMAN_SLOT], C.WHITE, C.GOLD])

    def draw(self, surf):
        t = self.t_
        surf.blit(self.app.background, (0, 0))
        dim(surf, 100)
        stage, rival, mine, theirs = t.results[-1]
        if t.status == CHAMPION:
            title(surf, "¡CAMPEÓN DEL MUNDO!", (640, 70), 56)
            draw_trophy(surf, (700, 300), 5)
            ang, bob = -50 + 50 * math.sin(self.t * 14), -int(abs(math.sin(self.t * 7)) * 6)
            img, (fx, fy) = self.app.sprites.player(t.player, 1, ang, bob, PLAYER_COLORS[HUMAN_SLOT], False, 2.2)
            surf.blit(img, (500 - fx, 400 - fy))
            draw_text(surf, f"{short_name(CHARACTERS_BY_ID[t.player])} ganó los 6 partidos del Mundialito", 24,
                      (640, 470), C.INK, outline=C.WHITE)
        else:
            head = "¡GANASTE!" if self.won else "ELIMINADO"
            title(surf, head, (640, 70), 64, C.GREEN if self.won else C.RED)
            box = pygame.Rect(0, 0, 340, 110)
            box.center = (640, 250)
            pygame.draw.rect(surf, C.INK, box.move(6, 6))
            pygame.draw.rect(surf, C.STRUCT_DARK, box)
            pygame.draw.rect(surf, C.INK, box, 4)
            led = box.inflate(-16, -16)
            pygame.draw.rect(surf, C.LED_BG, led)
            sc = pixelfont.render_led(f"{theirs}-{mine}", 9, C.LED_ON, C.LED_OFF)
            surf.blit(sc, sc.get_rect(center=led.center))
            draw_text(surf, f"{stage}: CPU {short_name(CHARACTERS_BY_ID[rival])} {theirs} - {mine} VOS", 24,
                      (640, 330), C.INK, outline=C.WHITE)
            if self.won:
                draw_text(surf, f"Pasás a {t.stage_name} contra {short_name(CHARACTERS_BY_ID[t.rival])}", 24,
                          (640, 380), C.INK, outline=C.WHITE)
            else:
                pos = t.position
                extra = " (subcampeón)" if pos == 2 else ""
                draw_text(surf, f"Terminaste en el {ordinal(pos)} puesto{extra}", 32, (640, 384), C.GOLD,
                          kind="title", outline=C.INK, shadow=True)
            for slot, x in ((BOT_SLOT, 220), (HUMAN_SLOT, 1060)):
                cid = rival if slot == BOT_SLOT else t.player
                f = 1 if slot == BOT_SLOT else -1
                happy = (slot == HUMAN_SLOT) == self.won
                ang, bob = ((-50 + 50 * math.sin(self.t * 14), -int(abs(math.sin(self.t * 7)) * 6))
                            if happy else (0, 0))
                img, (fx, fy) = self.app.sprites.player(cid, f, ang, bob, PLAYER_COLORS[slot], False, 1.8)
                surf.blit(img, (x - fx, 470 - fy))
                draw_text(surf, LABELS[slot], 24, (x, 494), PLAYER_COLORS[slot], outline=C.INK)
        self.app.fx.draw(surf)
        self.menu.draw(surf)
        if t.status not in (CHAMPION, ELIMINATED):
            footer(surf, "Si vas al menú, el Mundialito queda guardado y lo seguís desde Jugar > Mundialito.")

