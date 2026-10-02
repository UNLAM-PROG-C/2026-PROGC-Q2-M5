"""Pantallas del Mundialito (1 jugador contra la computadora, sólo local).

Flujo:  elegir personaje -> llave del torneo -> partido -> resultado -> ...
El progreso vive en app.tournament mientras el juego está abierto:
  * terminar un partido e ir al menú NO pierde el progreso (se continúa desde
    "Jugar > Mundialito");
  * ir al menú desde la PAUSA de un partido es abandonar: se pierde el torneo.
"""
import random

import pygame

from .. import protocol as P
from ..bot import LEVELS, Bot
from ..config import PLAYER_COLORS, UI_FPS
from ..mundialito import BOT_SLOT, CHAMPION, ELIMINATED, GROUP_STAGES, HUMAN_SLOT, STAGES, Tournament, ordinal
from . import palette as C
from .assets import draw_text
from .characters import CHARACTER_IDS, CHARACTERS_BY_ID, short_name
from .layout import (CENTER_X, FONT_LARGE, FONT_SMALL, FONT_TEXT, FONT_TITLE_L, FONT_TITLE_XL, FRAME_LINE,
                     SCREEN_H, VEIL_OVERLAY, VEIL_RESULT)
from .match_screens import FACING, SELECTION_LINE, SELECTION_MARGIN, MatchScreen, card_rect, draw_card
from .retro import bevel_box
from .screens import BACK_KEYS, BackButton, Menu, MenuScreen, Screen, button, dim, footer, panel, scoreboard, title
from .sprites import celebrate_pose, idle_pose

RUNNER_UP = 2                      # puesto del que pierde la final
BOT_SEED_RANGE = 10 ** 9           # semillas posibles del bot cuando no se fija una (--seed)
MENU_W = 420                       # ancho de los botones de las pantallas del Mundialito
MENU_BUTTON_H = 50                 # alto de esos botones
MENU_GAP = 10                      # px entre esos botones
TITLE_Y = 40                       # "MUNDIALITO"

# --- la copa, en px nativos (se dibuja chica y se agranda sin suavizar)
TROPHY_SIZE = (26, 44)             # lienzo de la copa (ancho, alto)
TROPHY_GOLD = (240, 190, 40)       # dorado
TROPHY_GOLD_DARK = (190, 135, 20)  # dorado en sombra (contornos)
TROPHY_GOLD_LIGHT = (255, 236, 140)  # brillos
TROPHY_GREEN = (40, 140, 70)       # franjas verdes de la base
TROPHY_GLOBE = (13, 9)             # centro del globo de arriba
TROPHY_GLOBE_R = 8                 # radio del globo (con contorno)
TROPHY_MERIDIANS = (((6, 9), (20, 9)), ((13, 2), (13, 16)))   # líneas del globo (horizontal y vertical)
TROPHY_GLOBE_SHINE = (9, 4, 3, 2)  # brillo del globo (x, y, ancho, alto)
TROPHY_BODY = [(7, 15), (19, 15), (16, 30), (10, 30)]   # cuerpo: trapecio que se angosta hacia abajo
TROPHY_SPIRALS_Y = (19, 23, 27)    # altura de las espirales del cuerpo
TROPHY_SPIRAL_X = (9, 17)          # las espirales van de x = 9 a x = 17...
TROPHY_SPIRAL_RISE = 2             # ...subiendo 2 px
TROPHY_BODY_SHINE = (11, 17, 1, 10)  # brillo vertical del cuerpo
# la base, de arriba hacia abajo: (color, (x, y, ancho, alto))
TROPHY_BASE = ((TROPHY_GOLD, (7, 30, 12, 3)), (TROPHY_GREEN, (6, 33, 14, 3)), (TROPHY_GOLD, (6, 36, 14, 2)),
               (TROPHY_GREEN, (5, 38, 16, 3)), (TROPHY_GOLD_DARK, (5, 41, 16, 2)))
TROPHY_SCALE = 4                   # agrandado por defecto de la copa


def open_mundialito(app):
    """Entrada desde "Jugar": continúa el torneo en curso o empieza uno nuevo."""
    t = getattr(app, "tournament", None)
    if t is not None and not t.finished:
        app.switch(HubScreen(app))
    else:
        app.tournament = None
        app.switch(PickScreen(app))


def draw_trophy(surf, center, k=TROPHY_SCALE):
    """Copa del Mundo en pixel art (dibujada a resolución nativa y agrandada k veces)."""
    s = pygame.Surface(TROPHY_SIZE, pygame.SRCALPHA)
    pygame.draw.circle(s, TROPHY_GOLD_DARK, TROPHY_GLOBE, TROPHY_GLOBE_R)          # globo
    pygame.draw.circle(s, TROPHY_GOLD, TROPHY_GLOBE, TROPHY_GLOBE_R - 1)
    for a, b in TROPHY_MERIDIANS:
        pygame.draw.line(s, TROPHY_GOLD_DARK, a, b)
    s.fill(TROPHY_GOLD_LIGHT, TROPHY_GLOBE_SHINE)
    pygame.draw.polygon(s, TROPHY_GOLD, TROPHY_BODY)                                # cuerpo
    pygame.draw.polygon(s, TROPHY_GOLD_DARK, TROPHY_BODY, 1)
    x0, x1 = TROPHY_SPIRAL_X
    for y in TROPHY_SPIRALS_Y:                                                      # espirales
        pygame.draw.line(s, TROPHY_GOLD_DARK, (x0, y), (x1, y - TROPHY_SPIRAL_RISE))
    s.fill(TROPHY_GOLD_LIGHT, TROPHY_BODY_SHINE)
    for color, rect in TROPHY_BASE:                                                 # base
        pygame.draw.rect(s, color, rect)
    w, h = TROPHY_SIZE
    img = pygame.transform.scale(s, (w * k, h * k))
    surf.blit(img, img.get_rect(center=center))


# ---------------------------------------------------------------------------
# Elegir personaje (una persona)
# ---------------------------------------------------------------------------
class PickScreen(Screen):
    PLAYER_X = 1030                    # x del personaje elegido (juega a la derecha)
    OK_SIZE = (220, 48)                # botón "¡A JUGAR!" (ancho, alto)
    OK_Y = 426                         # centro vertical de ese botón
    SUBTITLE_Y = 88                    # "Elegí tu personaje..."
    INFO = (70, 120, 640, 290)         # recuadro con las reglas (x, y, ancho, alto)
    INFO_PADDING = 12                  # px de aire dentro del recuadro
    RULES_TOP = 10                     # primera regla, desde arriba del recuadro
    RULE_STEP = 26                     # px entre reglas
    STAGES_PER_ROW = 3                 # etapas del torneo por fila
    STAGE_TOP = 150                    # primera fila de etapas, desde arriba del recuadro
    STAGE_SIZE = (190, 44)             # cada etapa (ancho, alto)
    STAGE_STEP = (200, 54)             # px entre etapas (horizontal, vertical)
    STAGE_BAR = (2, 6)                 # franja de color de la etapa (separación del borde, ancho)
    STAGE_TEXT_X = 16                  # nombre de la etapa, desde el borde izquierdo
    PEDESTAL = (200, 18)               # pedestal bajo el personaje (ancho, alto)
    PEDESTAL_TOP = 372                 # borde superior del pedestal
    FEET_Y = 376                       # y de los pies del personaje
    PLAYER_SCALE = 1.9                 # tamaño del personaje
    NAME_Y = 132                       # nombre del personaje elegido

    def __init__(self, app):
        super().__init__(app)
        last = app.last_characters[1] if app.last_characters else CHARACTER_IDS[0]
        self.cursor = CHARACTER_IDS.index(last)
        self.ok_rect = pygame.Rect((0, 0), self.OK_SIZE)
        self.ok_rect.center = (self.PLAYER_X, self.OK_Y)
        self.hover_ok = False
        self.back_button = BackButton(self.back)

    def back(self):
        from .screens import PlayMenuScreen
        self.app.audio.play("back")
        self.app.switch(PlayMenuScreen(self.app))

    def move(self, d):
        self.cursor = (self.cursor + d) % len(CHARACTER_IDS)
        self.app.audio.play("select")

    def confirm(self):
        self.app.audio.play("confirm")
        cid = CHARACTER_IDS[self.cursor]
        self.app.tournament = Tournament(cid, random.Random(self.app.options.seed))
        self.app.switch(HubScreen(self.app))

    def handle_event(self, ev):
        if self.back_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key in BACK_KEYS:
                self.back()
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
                if card_rect(k).collidepoint(ev.pos):
                    self.cursor = k
                    self.app.audio.play("select")

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_OVERLAY)
        title(surf, "MUNDIALITO", (CENTER_X, TITLE_Y), FONT_TITLE_L)
        draw_text(surf, f"Elegí tu personaje: vas a enfrentar a los otros {len(STAGES)}, uno por uno.", FONT_SMALL,
                  (CENTER_X, self.SUBTITLE_Y), C.INK, outline=C.WHITE)
        info = pygame.Rect(self.INFO)
        inner = panel(surf, info)
        lines = ["Sólo avanzás si ganás. Si perdés, quedás eliminado.",
                 "Cada rival es más difícil que el anterior.",
                 "Si el partido termina empatado: gol de oro.",
                 "Jugás a la DERECHA: valen A/D/W + Espacio",
                 "y también las flechas + P."]
        pad = self.INFO_PADDING
        for i, ln in enumerate(lines):
            draw_text(surf, ln, FONT_SMALL, (inner.left + pad, inner.top + self.RULES_TOP + i * self.RULE_STEP), C.INK,
                      anchor="topleft", outline=None)
        step_x, step_y = self.STAGE_STEP
        bar_gap, bar_w = self.STAGE_BAR
        for i, st in enumerate(STAGES):
            col = C.GREEN if i < GROUP_STAGES else (C.RED if i == len(STAGES) - 1 else C.BLUE)
            row, col_k = divmod(i, self.STAGES_PER_ROW)
            r = pygame.Rect((inner.left + pad + col_k * step_x, inner.top + self.STAGE_TOP + row * step_y),
                            self.STAGE_SIZE)
            bevel_box(surf, r, C.CREAM, shadow=False)
            pygame.draw.rect(surf, col, (r.left + bar_gap, r.top + bar_gap, bar_w, r.height - 2 * bar_gap))
            draw_text(surf, st, FONT_SMALL, (r.left + self.STAGE_TEXT_X, r.centery), C.INK, anchor="midleft",
                      outline=None)
        cid = CHARACTER_IDS[self.cursor]
        ped = pygame.Rect((0, 0), self.PEDESTAL)
        ped.midtop = (self.PLAYER_X, self.PEDESTAL_TOP)
        bevel_box(surf, ped, C.STRUCT)
        ang, bob = idle_pose(self.t)
        img, (fx, fy) = self.app.sprites.player(cid, FACING[HUMAN_SLOT], ang, bob, PLAYER_COLORS[HUMAN_SLOT], False,
                                                self.PLAYER_SCALE)
        surf.blit(img, (self.PLAYER_X - fx, self.FEET_Y - fy))
        draw_text(surf, short_name(CHARACTERS_BY_ID[cid]).upper(), FONT_LARGE, (self.PLAYER_X, self.NAME_Y), C.GOLD,
                  kind="title", outline=C.INK, shadow=True)
        button(surf, self.ok_rect, "¡A JUGAR!", self.hover_ok, True, FONT_TEXT, self.t)
        for k in range(len(CHARACTER_IDS)):
            rr = draw_card(surf, self.app.sprites, k, k == self.cursor)
            if k == self.cursor:
                frame = rr.inflate(2 * SELECTION_MARGIN, 2 * SELECTION_MARGIN)
                pygame.draw.rect(surf, PLAYER_COLORS[HUMAN_SLOT], frame, SELECTION_LINE)
        footer(surf, "A/D o flechas: elegir  -  Espacio, P o Enter: confirmar  -  Esc: volver  -  Mouse: clic")
        self.back_button.draw(surf, self.t)


# ---------------------------------------------------------------------------
# Llave del torneo
# ---------------------------------------------------------------------------
class HubScreen(Screen):
    MENU_CENTER = (CENTER_X, 560)      # botones Jugar / Menú / Abandonar
    SUBTITLE_Y = 86                    # "Jugás con ... - Próximo: ..."
    STAGE_W = 186                      # px: ancho de cada columna de la llave
    STAGE_GAP = 20                     # px entre columnas
    STAGE_TOP = 140                    # borde superior de las columnas
    STAGE_H = 300                      # px: alto de cada columna
    CURRENT_BOB_PX = 6                 # px que salta la columna del próximo partido...
    CURRENT_BOB_HZ = 3                 # ...y cuántas veces por segundo cambia
    GROUP_Y = 12                       # "GRUPOS"/"ELIMINACIÓN", desde arriba de la columna
    STAGE_NAME_Y = 36                  # nombre de la etapa, desde arriba de la columna
    PORTRAIT_Y = 58                    # retrato del rival, desde arriba de la columna
    UPCOMING_VEIL = (255, 255, 255, 120)   # velo blanco sobre los rivales que todavía no tocan
    RIVAL_NAME_GAP = 14                # nombre del rival, debajo del retrato
    STATUS_BOTTOM = 14                 # "GANADO 2-1"/"PRÓXIMO", desde abajo de la columna
    TROPHY_CENTER = (1196, 560)        # copa chica, abajo a la derecha
    TROPHY_SCALE = 2                   # tamaño de esa copa

    def __init__(self, app):
        super().__init__(app)
        t = app.tournament
        self.menu = Menu([(f"Jugar {t.stage_name}", self.play), ("Menú principal", self.to_menu),
                          ("Abandonar Mundialito", self.abandon)], self.MENU_CENTER, width=MENU_W,
                         height=MENU_BUTTON_H, gap=MENU_GAP)
        self.back_button = BackButton(self.back)

    def back(self):
        """Vuelve a "Jugar" (el progreso queda guardado)."""
        from .screens import PlayMenuScreen
        self.app.audio.play("back")
        self.app.switch(PlayMenuScreen(self.app))

    def play(self):
        self.app.switch(MundialitoMatchScreen(self.app, self.app.tournament))

    def to_menu(self):
        self.app.switch(MenuScreen(self.app))       # el progreso queda guardado

    def abandon(self):
        self.app.tournament = None
        self.app.switch(MenuScreen(self.app))

    def handle_event(self, ev):
        if self.back_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN and ev.key in BACK_KEYS:
            self.back()
            return
        self.menu.handle_event(ev, self.app.audio)

    def update(self, dt):
        super().update(dt)
        self.menu.update(dt)

    def draw(self, surf):
        t = self.app.tournament
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_OVERLAY)
        title(surf, "MUNDIALITO", (CENTER_X, TITLE_Y), FONT_TITLE_L)
        me = CHARACTERS_BY_ID[t.player]
        draw_text(surf, f"Jugás con {short_name(me)}  -  Próximo: {t.stage_name} contra "
                        f"{short_name(CHARACTERS_BY_ID[t.rival])} (dificultad {LEVELS[t.level]['name']})",
                  FONT_SMALL, (CENTER_X, self.SUBTITLE_Y), C.INK, outline=C.WHITE)
        w, gap = self.STAGE_W, self.STAGE_GAP
        n = len(STAGES)
        x0 = CENTER_X - (n * w + (n - 1) * gap) / 2
        for i, (stage, rival) in enumerate(zip(STAGES, t.rivals)):
            r = pygame.Rect(x0 + i * (w + gap), self.STAGE_TOP, w, self.STAGE_H)
            current = i == t.stage
            done = i < len(t.results)
            face = C.GOLD if current else (C.CREAM if done or i < t.stage else C.CREAM_DARK)
            bob = self.CURRENT_BOB_PX if current and int(self.t * self.CURRENT_BOB_HZ) % 2 else 0
            inner = bevel_box(surf, r.move(0, -bob), face)
            group = "GRUPOS" if i < GROUP_STAGES else "ELIMINACIÓN"
            draw_text(surf, group, FONT_SMALL, (inner.centerx, inner.top + self.GROUP_Y), C.INK_SOFT, outline=None)
            draw_text(surf, stage, FONT_SMALL, (inner.centerx, inner.top + self.STAGE_NAME_Y), C.INK, outline=None)
            portrait = self.app.sprites.portrait(rival)
            pr = portrait.get_rect(midtop=(inner.centerx, inner.top + self.PORTRAIT_Y))
            surf.blit(portrait, pr)
            pygame.draw.rect(surf, C.INK, pr, FRAME_LINE)
            if not done and not current:
                veil = pygame.Surface(pr.size, pygame.SRCALPHA)
                veil.fill(self.UPCOMING_VEIL)
                surf.blit(veil, pr)
            draw_text(surf, short_name(CHARACTERS_BY_ID[rival]).upper(), FONT_SMALL,
                      (inner.centerx, pr.bottom + self.RIVAL_NAME_GAP), C.INK, outline=None)
            status_y = inner.bottom - self.STATUS_BOTTOM
            if done:
                _, _, mine, theirs = t.results[i]
                draw_text(surf, f"GANADO {mine}-{theirs}", FONT_SMALL, (inner.centerx, status_y), C.GREEN,
                          outline=C.INK)
            elif current:
                draw_text(surf, "PRÓXIMO", FONT_SMALL, (inner.centerx, status_y), C.RED, outline=C.WHITE)
        draw_trophy(surf, self.TROPHY_CENTER, self.TROPHY_SCALE)
        self.menu.draw(surf)
        footer(surf, "Volver o ir al menú guarda tu progreso.  Abandonar lo descarta.")
        self.back_button.draw(surf, self.t)


# ---------------------------------------------------------------------------
# Partido del Mundialito
# ---------------------------------------------------------------------------
class MundialitoMatchScreen(MatchScreen):
    STAGE_TAG = (330, 34)              # cartelito "MUNDIALITO - FECHA 1" abajo al centro (ancho, alto)
    STAGE_TAG_BOTTOM = 6               # px entre ese cartelito y el borde inferior de la pantalla

    def __init__(self, app, tournament):
        self.tournament = tournament
        chars = [None, None]
        chars[BOT_SLOT] = tournament.rival
        chars[HUMAN_SLOT] = tournament.player
        super().__init__(app, chars)
        seed = app.options.seed if app.options.seed is not None else random.randrange(BOT_SEED_RANGE)
        self.bot = Bot(BOT_SLOT, tournament.level, seed + tournament.stage)
        self._dt = 1 / UI_FPS

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
            r = pygame.Rect((0, 0), self.STAGE_TAG)
            r.midbottom = (CENTER_X, SCREEN_H - self.STAGE_TAG_BOTTOM)
            inner = bevel_box(surf, r, C.CREAM, shadow=False)
            draw_text(surf, f"MUNDIALITO - {t.stage_name.upper()}", FONT_SMALL, inner.center, C.INK, outline=None)


# ---------------------------------------------------------------------------
# Resultado de cada partido
# ---------------------------------------------------------------------------
class MundialitoResultScreen(Screen):
    MENU_CENTER = (CENTER_X, 590)      # botones Siguiente / Menú
    CONFETTI_EVERY = 1.2               # s entre tandas de papelitos al ganar
    CONFETTI_AT = (CENTER_X, 300)      # de dónde salen los papelitos
    HEADLINE_Y = 70                    # "¡CAMPEÓN DEL MUNDO!" / "¡GANASTE!" / "ELIMINADO"
    TROPHY_CENTER = (700, 300)         # copa grande del campeón
    TROPHY_SCALE = 5                   # tamaño de esa copa
    CHAMPION_FEET = (500, 400)         # pies del campeón, al lado de la copa
    CHAMPION_SCALE = 2.2               # tamaño del campeón
    CHAMPION_TEXT_Y = 470              # "... ganó los 6 partidos del Mundialito"
    SCORE_CENTER = (CENTER_X, 250)     # tablero con el resultado
    SCORE_W = 340                      # ancho del tablero
    SUMMARY_Y = 330                    # "Fecha 1: Pelé 1 - 2 Messi"
    NEXT_Y = 380                       # "Pasás a ... contra ..."
    PLACE_Y = 384                      # "Terminaste en el 3.º puesto"
    PLAYER_X = {BOT_SLOT: 220, HUMAN_SLOT: 1060}   # x de cada jugador
    FEET_Y = 470                       # y de los pies de los jugadores
    PLAYER_SCALE = 1.8                 # tamaño de los jugadores
    NAME_Y = 494                       # nombre de cada jugador

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
        self.menu = Menu(items, self.MENU_CENTER, width=MENU_W, height=MENU_BUTTON_H, gap=MENU_GAP)

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
                self.confetti_t = self.CONFETTI_EVERY
                self.app.fx.confetti(*self.CONFETTI_AT, [PLAYER_COLORS[HUMAN_SLOT], C.WHITE, C.GOLD])

    def draw(self, surf):
        t = self.t_
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_RESULT)
        stage, rival, mine, theirs = t.results[-1]
        if t.status == CHAMPION:
            title(surf, "¡CAMPEÓN DEL MUNDO!", (CENTER_X, self.HEADLINE_Y), FONT_TITLE_L)
            draw_trophy(surf, self.TROPHY_CENTER, self.TROPHY_SCALE)
            ang, bob = celebrate_pose(self.t)
            img, (fx, fy) = self.app.sprites.player(t.player, 1, ang, bob, PLAYER_COLORS[HUMAN_SLOT], False,
                                                    self.CHAMPION_SCALE)
            x, y = self.CHAMPION_FEET
            surf.blit(img, (x - fx, y - fy))
            draw_text(surf, f"{short_name(CHARACTERS_BY_ID[t.player])} ganó los {len(STAGES)} partidos del Mundialito",
                      FONT_TEXT, (CENTER_X, self.CHAMPION_TEXT_Y), C.INK, outline=C.WHITE)
        else:
            head = "¡GANASTE!" if self.won else "ELIMINADO"
            title(surf, head, (CENTER_X, self.HEADLINE_Y), FONT_TITLE_XL, C.GREEN if self.won else C.RED)
            scoreboard(surf, self.SCORE_CENTER, self.SCORE_W, f"{theirs}-{mine}")
            draw_text(surf, f"{stage}: {short_name(CHARACTERS_BY_ID[rival])} {theirs} - {mine} "
                            f"{short_name(CHARACTERS_BY_ID[t.player])}", FONT_TEXT, (CENTER_X, self.SUMMARY_Y), C.INK,
                      outline=C.WHITE)
            if self.won:
                draw_text(surf, f"Pasás a {t.stage_name} contra {short_name(CHARACTERS_BY_ID[t.rival])}", FONT_TEXT,
                          (CENTER_X, self.NEXT_Y), C.INK, outline=C.WHITE)
            else:
                pos = t.position
                extra = " (subcampeón)" if pos == RUNNER_UP else ""
                draw_text(surf, f"Terminaste en el {ordinal(pos)} puesto{extra}", FONT_LARGE, (CENTER_X, self.PLACE_Y),
                          C.GOLD, kind="title", outline=C.INK, shadow=True)
            for slot in (BOT_SLOT, HUMAN_SLOT):
                x = self.PLAYER_X[slot]
                cid = rival if slot == BOT_SLOT else t.player
                happy = (slot == HUMAN_SLOT) == self.won
                ang, bob = celebrate_pose(self.t) if happy else (0, 0)
                img, (fx, fy) = self.app.sprites.player(cid, FACING[slot], ang, bob, PLAYER_COLORS[slot], False,
                                                        self.PLAYER_SCALE)
                surf.blit(img, (x - fx, self.FEET_Y - fy))
                draw_text(surf, short_name(CHARACTERS_BY_ID[cid]), FONT_TEXT, (x, self.NAME_Y), PLAYER_COLORS[slot],
                          outline=C.INK)
        self.app.fx.draw(surf)
        self.menu.draw(surf)
        if t.status not in (CHAMPION, ELIMINATED):
            footer(surf, "Si vas al menú, el Mundialito queda guardado y lo seguís desde Jugar > Mundialito.")

