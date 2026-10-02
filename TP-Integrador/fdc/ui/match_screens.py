"""Pantallas del partido: selección de personajes, juego y resultado."""
import math

import pygame

from .. import protocol as P
from ..config import (CATEGORY_BAD, CATEGORY_COLORS, CATEGORY_GLOBAL, PLAYER_COLORS, PLAYER_KEYS,
                      PLAYER_LABELS, POWER_IDS, POWERS_BY_ID, Arena, MatchRules)
from . import palette as C
from .assets import draw_text, text, wrap
from .retro import bevel_box
from .characters import CHARACTER_IDS, CHARACTERS_BY_ID, short_name
from .icons import power_icon
from .input import key_code, key_label
from .layout import (ARROW_BUTTON_W, BUTTON_SMALL_H, CENTER_X, FONT_BANNER, FONT_LARGE, FONT_SMALL, FONT_TEXT,
                     FONT_TITLE, FONT_TITLE_L, FONT_TITLE_S, FRAME_LINE, SHADOW_OFFSET, TEXT_LINE_H, VEIL_OVERLAY,
                     VEIL_RESULT)
from .render import MatchRenderer
from .screens import (BACK_KEYS, BackButton, Menu, MenuScreen, MultiplayerMenuScreen, Screen, button, dim,
                      footer, panel, scoreboard, title)
from .sprites import celebrate_pose, idle_pose

PLAYER_X = (250, 1030)             # x de cada jugador en la selección (J1 a la izquierda, J2 a la derecha)
FACING = (1, -1)                   # J1 mira a la derecha y J2 a la izquierda
# --- fila de tarjetas de personajes (selección local y Mundialito)
CARD_W = 150                       # px: ancho de cada tarjeta
CARD_H = 168                       # px: alto de cada tarjeta
CARD_GAP = 14                      # px entre tarjetas
CARDS_TOP = 508                    # borde superior de la fila
CARD_LIFT = 8                      # px que sube la tarjeta elegida
CARD_NAME_BOTTOM = 14              # nombre, desde el borde inferior de la tarjeta
SELECTION_MARGIN = 6               # px entre la tarjeta y el marco de quien la eligió
SELECTION_LINE = 6                 # px: grosor de ese marco (si la eligieron los dos, van uno adentro del otro)
# --- botones de mouse ◄ OK ► debajo de cada personaje
CHOICE_BUTTONS_Y = 402             # borde superior de la fila
OK_BUTTON_W = 172                  # ancho del botón OK / CANCELAR
BUTTON_GAP = 12                    # px entre los botones


def card_rect(k):
    """Lugar de la tarjeta del personaje k en la fila (centrada, abajo)."""
    n = len(CHARACTER_IDS)
    total = n * CARD_W + (n - 1) * CARD_GAP
    x0 = CENTER_X - total / 2
    return pygame.Rect(x0 + k * (CARD_W + CARD_GAP), CARDS_TOP, CARD_W, CARD_H)


def draw_card(surf, sprites, k, lifted):
    """Tarjeta del personaje k con su nombre (sube un poco si está elegida). Devuelve dónde quedó."""
    cid = CHARACTER_IDS[k]
    rr = card_rect(k).move(0, -CARD_LIFT if lifted else 0)
    pygame.draw.rect(surf, C.INK, rr.move(SHADOW_OFFSET, SHADOW_OFFSET))
    surf.blit(sprites.portrait(cid), rr)
    pygame.draw.rect(surf, C.INK, rr, FRAME_LINE)
    draw_text(surf, short_name(CHARACTERS_BY_ID[cid]).upper(), FONT_SMALL,
              (rr.centerx, rr.bottom - CARD_NAME_BOTTOM), C.WHITE, outline=C.INK)
    return rr


def choice_buttons(x):
    """Botones ◄  OK/CANCELAR  ► centrados en x, debajo del personaje."""
    half = OK_BUTTON_W // 2
    y = CHOICE_BUTTONS_Y
    return {"prev": pygame.Rect(x - half - BUTTON_GAP - ARROW_BUTTON_W, y, ARROW_BUTTON_W, BUTTON_SMALL_H),
            "ok": pygame.Rect(x - half, y, OK_BUTTON_W, BUTTON_SMALL_H),
            "next": pygame.Rect(x + half + BUTTON_GAP, y, ARROW_BUTTON_W, BUTTON_SMALL_H)}


def by_strength(weakest, k):
    """Valor entre 'weakest' (golpe suave, k = 0) y 1 (golpe fuerte, k = 1)."""
    return weakest + (1 - weakest) * k


# ---------------------------------------------------------------------------
# Selección de personajes (independiente para cada jugador)
# ---------------------------------------------------------------------------
class SelectScreen(Screen):
    LABEL_INSET_X = 6                  # etiqueta "J1"/"J2", desde el costado del marco
    LABEL_RAISE = 12                   # etiqueta, sobre el borde del marco
    LABEL_PAD = (4, 2)                 # px de aire alrededor de la etiqueta (horizontal, vertical)
    READY_DELAY = 0.9                  # s con los dos listos antes de ir a la cancha
    TITLE_Y = 40                       # título
    SUBTITLE_Y = 84                    # "Todos tienen las mismas capacidades..."
    TAG = (300, 70)                    # recuadro con el nombre del personaje (ancho, alto)
    TAG_TOP = 108                      # borde superior de ese recuadro
    TAG_BAR_H = 6                      # franja con el color del jugador
    TAG_NAME_Y = 22                    # nombre, desde arriba del recuadro
    TAG_TEAM_Y = 44                    # selección y camiseta, desde arriba del recuadro
    PEDESTAL = (200, 18)               # pedestal bajo el personaje (ancho, alto)
    PEDESTAL_TOP = 376                 # borde superior del pedestal
    FEET_Y = 380                       # y de los pies del personaje
    PLAYER_SCALE = 1.9                 # tamaño del personaje
    READY_X = 170                      # "¡LISTO!", hacia el centro desde el personaje
    READY_Y = 300                      # "¡LISTO!", altura
    READY_BOB_HZ = 6                   # saltitos por segundo del "¡LISTO!"
    READY_BOB_PX = 4                   # px de esos saltitos
    HINT_Y = 458                       # teclas de cada jugador
    VS_Y = 280                         # "VS"
    GO_Y = 360                         # "¡A LA CANCHA!"

    def __init__(self, app, preselect=None):
        super().__init__(app)
        pre = preselect or app.last_characters or (CHARACTER_IDS[0], CHARACTER_IDS[2])   # dos distintos
        self.cursor = [CHARACTER_IDS.index(pre[0]), CHARACTER_IDS.index(pre[1])]
        self.ready = [False, False]
        self.both_ready_t = None
        self.keys = [{a: key_code(n) for a, n in PLAYER_KEYS[i].items()} for i in (0, 1)]
        self.hover = None
        self.back_button = BackButton(self.back)

    def back(self):
        self.app.audio.play("back")
        self.app.switch(MultiplayerMenuScreen(self.app))

    # ------------------------------------------------------------------ geometría
    def buttons(self, i):
        """Botones de mouse de cada jugador: ◄  OK/CANCELAR  ►."""
        return choice_buttons(PLAYER_X[i])

    # ------------------------------------------------------------------ acciones
    def move(self, i, d):
        if not self.ready[i]:
            self.cursor[i] = (self.cursor[i] + d) % len(CHARACTER_IDS)
            self.app.audio.play("select")

    def toggle(self, i):
        self.ready[i] = not self.ready[i]
        self.both_ready_t = None
        self.app.audio.play("confirm" if self.ready[i] else "back")

    def handle_event(self, ev):
        if self.back_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key in BACK_KEYS:
                self.back()
                return
            for i in (0, 1):
                k = self.keys[i]
                if ev.key == k["left"]:
                    self.move(i, -1)
                elif ev.key == k["right"]:
                    self.move(i, 1)
                elif ev.key == k["kick"] and not self.ready[i]:
                    self.toggle(i)
                elif ev.key == k["jump"] and self.ready[i]:
                    self.toggle(i)
        elif ev.type == pygame.MOUSEMOTION:
            self.hover = None
            for i in (0, 1):
                for name, r in self.buttons(i).items():
                    if r.collidepoint(ev.pos):
                        self.hover = (i, name)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (pygame.BUTTON_LEFT, pygame.BUTTON_RIGHT):
            for i in (0, 1):
                b = self.buttons(i)
                if b["ok"].collidepoint(ev.pos):
                    self.toggle(i)
                    return
                if b["prev"].collidepoint(ev.pos):
                    self.move(i, -1)
                    return
                if b["next"].collidepoint(ev.pos):
                    self.move(i, 1)
                    return
            # tarjetas: clic izquierdo elige para J1, derecho para J2
            i = 0 if ev.button == pygame.BUTTON_LEFT else 1
            for k in range(len(CHARACTER_IDS)):
                if card_rect(k).collidepoint(ev.pos) and not self.ready[i]:
                    self.cursor[i] = k
                    self.app.audio.play("select")

    def update(self, dt):
        super().update(dt)
        if all(self.ready):
            if self.both_ready_t is None:
                self.both_ready_t = self.READY_DELAY
            self.both_ready_t -= dt
            if self.both_ready_t <= 0:
                chars = [CHARACTER_IDS[c] for c in self.cursor]
                self.app.last_characters = chars
                self.app.switch(MatchScreen(self.app, chars))

    # ------------------------------------------------------------------ dibujo
    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_OVERLAY)
        title(surf, "ELEGÍ TU PERSONAJE", (CENTER_X, self.TITLE_Y), FONT_TITLE)
        draw_text(surf, "Todos tienen las mismas capacidades: sólo cambia la apariencia. Pueden elegir el mismo.",
                  FONT_SMALL, (CENTER_X, self.SUBTITLE_Y), C.INK, outline=C.WHITE)
        sp = self.app.sprites
        for i in (0, 1):
            cid = CHARACTER_IDS[self.cursor[i]]
            ch = CHARACTERS_BY_ID[cid]
            x = PLAYER_X[i]
            tag = pygame.Rect((0, 0), self.TAG)
            tag.midtop = (x, self.TAG_TOP)
            inner = panel(surf, tag)
            pygame.draw.rect(surf, PLAYER_COLORS[i], (inner.left, inner.top, inner.width, self.TAG_BAR_H))
            draw_text(surf, f"{PLAYER_LABELS[i]}  {short_name(ch).upper()}", FONT_TEXT,
                      (x, inner.top + self.TAG_NAME_Y), PLAYER_COLORS[i], outline=C.INK)
            draw_text(surf, f"{ch['team']} - camiseta {ch['number']}", FONT_SMALL, (x, inner.top + self.TAG_TEAM_Y),
                      C.INK, outline=None)
            # pedestal y jugador (festeja al confirmar)
            ped = pygame.Rect((0, 0), self.PEDESTAL)
            ped.midtop = (x, self.PEDESTAL_TOP)
            bevel_box(surf, ped, C.STRUCT, shadow=True)
            ang, bob = celebrate_pose(self.t) if self.ready[i] else idle_pose(self.t, i)
            img, (fx, fy) = sp.player(cid, FACING[i], ang, bob, PLAYER_COLORS[i], False, self.PLAYER_SCALE)
            surf.blit(img, (x - fx, self.FEET_Y - fy))
            if self.ready[i]:
                bob = self.READY_BOB_PX if int(self.t * self.READY_BOB_HZ) % 2 else 0
                draw_text(surf, "¡LISTO!", FONT_LARGE, (x + self.READY_X * FACING[i], self.READY_Y + bob),
                          C.GREEN, kind="title", outline=C.INK, shadow=True)
            b = self.buttons(i)
            hv = self.hover
            button(surf, b["prev"], "◄", hv == (i, "prev"), not self.ready[i], FONT_TEXT, self.t)
            button(surf, b["ok"], "CANCELAR" if self.ready[i] else "OK", hv == (i, "ok"), True, FONT_TEXT, self.t)
            button(surf, b["next"], "►", hv == (i, "next"), not self.ready[i], FONT_TEXT, self.t)
            names = PLAYER_KEYS[i]
            hint = (f"{key_label(names['left'], True)}/{key_label(names['right'], True)} elegir  "
                    f"{key_label(names['kick'], True)} confirmar  {key_label(names['jump'], True)} cancelar")
            draw_text(surf, hint, FONT_SMALL, (x, self.HINT_Y), C.INK, outline=C.WHITE)
        draw_text(surf, "VS", FONT_BANNER, (CENTER_X, self.VS_Y), C.WHITE, kind="title", outline=C.INK, shadow=True)
        pad_x, pad_y = self.LABEL_PAD
        for k in range(len(CHARACTER_IDS)):
            sel = [i for i in (0, 1) if self.cursor[i] == k]
            rr = draw_card(surf, sp, k, bool(sel))
            for n, i in enumerate(sel):
                inset = SELECTION_LINE * n if len(sel) == 2 else 0
                grow = 2 * SELECTION_MARGIN - inset * 2
                fr = rr.inflate(grow, grow)
                pygame.draw.rect(surf, PLAYER_COLORS[i], fr, SELECTION_LINE)
                lab = text(PLAYER_LABELS[i], FONT_SMALL, C.WHITE, outline=C.INK)
                top = fr.top - self.LABEL_RAISE
                pos = ((fr.left + self.LABEL_INSET_X, top) if i == 0
                       else (fr.right - lab.get_width() - self.LABEL_INSET_X, top))
                pygame.draw.rect(surf, PLAYER_COLORS[i], (pos[0] - pad_x, pos[1] - pad_y, lab.get_width() + 2 * pad_x,
                                                          lab.get_height() + 2 * pad_y))
                surf.blit(lab, pos)
        if all(self.ready):
            draw_text(surf, "¡A LA CANCHA!", FONT_TITLE_S, (CENTER_X, self.GO_Y), C.GOLD, kind="title", outline=C.INK,
                      shadow=True)
        footer(surf, "Esc: volver  -  Mouse: botones de cada jugador; "
                     "clic izquierdo en una tarjeta elige J1, derecho J2")
        self.back_button.draw(surf, self.t)


# ---------------------------------------------------------------------------
# Partido
# ---------------------------------------------------------------------------
class MatchScreen(Screen):
    """Partido. El Mundialito la extiende redefiniendo los métodos "gancho"
    (extra_payload, controls, pause_items, on_match_over); el modo
    Multijugador Local usa los valores de esta clase."""
    PAUSE_MENU_CENTER = (CENTER_X, 420)  # botones del menú de pausa
    PAUSE_MENU_W = 380                 # ancho de esos botones
    PAUSE_BOX = (560, 380)             # recuadro de la pausa (ancho, alto)
    PAUSE_CENTER = (CENTER_X, 390)     # centro de ese recuadro
    PAUSE_TITLE_Y = 34                 # "PAUSA", desde arriba del recuadro
    PAUSE_REASON_Y = 78                # motivo de la pausa, desde arriba del recuadro
    PAUSE_TEXT_MARGIN = 20             # px de aire a los costados del motivo
    PAUSE_STATUS_Y = 30                # "Pausando..." / "Reanudando...", bajo el centro del recuadro
    MESSAGE_Y = 330                    # "Preparando partido..." y "¡FINAL DEL PARTIDO!"
    MESSAGE_NOTE_Y = 380               # aclaración bajo "Preparando partido..."
    GOLDEN_GOAL_BANNER = 2.5           # s que se muestra el cartel de gol de oro
    KICKOFF_BANNER = 0.8               # s que se muestra el "¡YA!"
    GOAL_SHAKE = 0.25                  # s que tiembla la cámara con el gol
    CONFETTI_INSET = 50                # px desde el costado de la cancha donde salen los papelitos del gol
    CONFETTI_HEIGHT = 120              # px sobre el piso donde salen esos papelitos
    FINAL_WAIT = 1.8                   # s entre el pitazo final y la pantalla del resultado
    WHOOSH_VOLUME = 0.7                # volumen del "fiuu" de la patada
    HARD_HIT_SPEED = 1100              # px/s: a esta velocidad de la pelota el golpe suena (y se ve) al máximo
    HEADER_MIN_VOLUME = 0.5            # volumen del cabezazo más suave (el más fuerte suena a 1)
    HEADER_MIN_FLASH = 0.5             # tamaño del destello del cabezazo más suave
    BAR_MIN_VOLUME = 0.4               # volumen del golpe más suave en el travesaño
    BOUNCE_MIN_VOLUME = 0.3            # volumen del pique más suave
    DUST_SPEED = 350                   # px/s: un pique más fuerte que esto levanta polvo
    TOAST_TIME = 2.6                   # s que dura un aviso de poder
    MAX_TOASTS = 3                     # avisos visibles a la vez (los más nuevos)
    TOAST_BLINK_TIME = 0.3             # s finales en los que el aviso parpadea antes de irse
    TOAST_BLINK_HZ = 20                # cambios por segundo de ese parpadeo
    TOAST_H = 40                       # px: alto de un aviso
    TOAST_TOP = 170                    # borde superior del primer aviso
    TOAST_STEP = 46                    # px entre avisos
    TOAST_PADDING = 28                 # px que se suman al texto (márgenes y franja de color)
    TOAST_ICON_ROOM = 30               # px extra si el aviso lleva ícono
    TOAST_BAR_W = 6                    # franja con el color de la categoría
    TOAST_TEXT_X = 12                  # ícono o texto, desde el borde izquierdo
    TOAST_ICON = 28                    # px: ícono del poder
    TOAST_ICON_ADVANCE = 34            # px que ocupa el ícono con su separación
    TEST_PANEL = (8, 646, 600, 68)     # recuadro del modo prueba, abajo a la izquierda (x, y, ancho, alto)
    TEST_ICON = 44                     # px: ícono del poder elegido
    TEST_ICON_INSET = 6                # ícono, desde la esquina del recuadro
    TEST_TEXT_X = 60                   # textos, desde el borde izquierdo
    TEST_LINE_Y = (8, 32)              # los dos renglones, desde el borde superior

    def __init__(self, app, characters):
        super().__init__(app)
        self.chars = list(characters)
        self.renderer = MatchRenderer(app, self.chars)
        self.filter = P.StateFilter()
        self.state = None
        self.match_id = None
        self.waiting = None          # "start" | "restart" mientras falta la confirmación
        self.pause_state = None      # None | "requested" | "paused" | "resuming"
        self.pause_reason = None
        self.pause_menu = Menu(self.pause_items(), self.PAUSE_MENU_CENTER, width=self.PAUSE_MENU_W)
        self.end_info = None
        self.end_timer = 0.0
        self.toasts = []
        self.last_count = None
        self.ignored_events = 0
        self.test_sel = 0
        self.expected_cid = {}
        self.pause_button = BackButton(self.request_pause, "II PAUSA")

    # ------------------------------------------------------------------ ciclo
    def enter(self):
        for cid in set(self.chars):
            self.app.sprites.warm(cid)   # antes de empezar: sin tirones durante el juego
        self.app.input.capture = True
        self.app.fx.clear()
        self._start(P.CMD_START)

    def leave(self):
        self.app.input.capture = False
        self.app.input.release_all()
        self.app.audio.crowd(False)

    def _start(self, cmd):
        self.match_id = self.app.next_match_id()
        self.filter.expect(self.match_id)   # desde ya se ignoran estados viejos
        self.state = None
        self.end_info = None
        self.renderer.reset()
        self.app.fx.clear()
        self.toasts.clear()
        payload = {"match": self.match_id, "characters": self.chars}
        payload.update(self.extra_payload())
        if self.app.options.seed is not None:
            payload["seed"] = self.app.options.seed
        cid = self.app.link.send_command(cmd, **payload)
        self.expected_cid[cid] = cmd
        self.waiting = "start" if cmd == P.CMD_START else "restart"

    def _send(self, cmd, **payload):
        cid = self.app.link.send_command(cmd, **payload)
        if cid is not None:
            self.expected_cid[cid] = cmd
        return cid

    # ------------------------------------------------------------------ ganchos
    def pause_items(self):
        return [("Continuar", self.resume), ("Reiniciar", self.restart), ("Menú principal", self.to_menu)]

    def extra_payload(self):
        return {}

    def controls(self, active):
        """Fotos de controles de los dos lugares (aquí: dos personas, un teclado)."""
        return self.app.input.snapshot(active)

    def on_match_over(self):
        self.app.switch(ResultScreen(self.app, self.chars, self.end_info, self.state))

    # ------------------------------------------------------------------ órdenes
    def request_pause(self, reason=P.PAUSE_REASON_USER):
        if self.waiting or self.pause_state is not None or self.state is None:
            return
        if self.state["phase"] == P.PHASE_FINISHED:
            return
        self.app.input.release_all()
        self.pause_state = "requested"
        self.pause_reason = reason
        self.pause_menu.sel = 0
        self._send(P.CMD_PAUSE, reason=reason)

    def resume(self):
        if self.pause_state != "paused":
            return
        self.pause_state = "resuming"
        self._send(P.CMD_RESUME)

    def restart(self):
        if self.pause_state != "paused":
            return
        self.pause_state = None
        self._start(P.CMD_RESTART)

    def to_menu(self):
        self._send(P.CMD_END)
        self.app.switch(MenuScreen(self.app))

    # ------------------------------------------------------------------ entrada
    def handle_event(self, ev):
        self.pause_button.visible = self.pause_state is None and self.state is not None
        if self.pause_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                if self.pause_state is None:
                    self.request_pause()
                elif self.pause_state == "paused":
                    self.app.audio.play("confirm")
                    self.resume()
                return
            if self.app.options.test_mode and self.pause_state is None:
                self._test_key(ev.key)
        if self.pause_state == "paused":
            self.pause_menu.handle_event(ev, self.app.audio)

    def _test_key(self, key):
        n = len(POWER_IDS)
        power = POWER_IDS[self.test_sel]
        if key == key_code("f5"):
            self.test_sel = (self.test_sel - 1) % n
        elif key == key_code("f6"):
            self.test_sel = (self.test_sel + 1) % n
        elif key == key_code("f7"):
            self._send(P.CMD_DEBUG_POWER, power=power, mode="spawn")
        elif key == key_code("f8"):
            self._send(P.CMD_DEBUG_POWER, power=power, mode="p0")
        elif key == key_code("f9"):
            self._send(P.CMD_DEBUG_POWER, power=power, mode="p1")
        elif key == key_code("f12"):
            self._send(P.CMD_DEBUG_CRASH)

    def on_focus_lost(self):
        self.request_pause(P.PAUSE_REASON_FOCUS)

    # ------------------------------------------------------------------ mensajes
    def on_link(self, msgs, state):
        for m in msgs:
            t = m["type"]
            if t == P.EV_ACK:
                self._on_ack(m)
                continue
            if m.get("match") != self.match_id:
                self.ignored_events += 1     # evento de un partido anterior
                continue
            self._on_event(m)
        if state is not None and self.filter.accept(state):
            self.state = state
            if self.waiting and state["match"] == self.match_id:
                self.waiting = None

    def _on_ack(self, m):
        cmd = self.expected_cid.pop(m["cid"], None)
        if cmd is None:
            return
        if cmd in (P.CMD_START, P.CMD_RESTART):
            if not m["ok"]:
                self.app.link.fail("La simulación rechazó el inicio del partido: " + m.get("detail", ""))
        elif cmd == P.CMD_PAUSE:
            if m["ok"]:
                self.pause_state = "paused"
                self.app.audio.play("back")
            else:
                self.pause_state = None
        elif cmd == P.CMD_RESUME:
            self.pause_state = None if m["ok"] else "paused"
        elif cmd == P.CMD_DEBUG_POWER and not m["ok"]:
            self.toast(f"Prueba rechazada: {m.get('detail', '')}", C.SOFT_RED)

    def _on_event(self, m):
        t = m["type"]
        au, fx, st = self.app.audio, self.app.fx, self.state
        if t == P.EV_GOLDEN_GOAL:
            self.renderer.golden_flash = self.GOLDEN_GOAL_BANNER
            au.play("whistle")
        elif t == P.EV_KICKOFF:
            self.renderer.kickoff_flash = self.KICKOFF_BANNER
            au.play("go")
            au.play("whistle")
        elif t == P.EV_GOAL:
            self.renderer.goal_banner = (MatchRules.GOAL_CELEBRATION, m)
            gx = self.CONFETTI_INSET if m["side"] == 0 else Arena.WIDTH - self.CONFETTI_INSET
            fx.confetti(gx, Arena.FLOOR_Y - self.CONFETTI_HEIGHT, [PLAYER_COLORS[m["scorer"]], C.WHITE, C.GOLD])
            fx.shake = self.GOAL_SHAKE
            au.play("goal")
        elif t == P.EV_MATCH_END:
            self.end_info = m
            self.end_timer = self.FINAL_WAIT
            au.play("whistle_end")
        elif t == P.EV_PAUSED:
            self.pause_state = "paused"
            self.pause_reason = m.get("reason")
            self.app.input.release_all()
        elif t == P.EV_POWER:
            pdef = POWERS_BY_ID[m["power"]]
            col = CATEGORY_COLORS[pdef.category]
            fx.sparkle(m["x"], m["y"], col)
            au.play({CATEGORY_BAD: "power_bad", CATEGORY_GLOBAL: "power_global"}.get(pdef.category, "power_good"))
            name = self.renderer.who
            who = name(m["receptor"]) if m["receptor"] is not None else "Partido"
            targets = ", ".join({"p0": name(0), "p1": name(1), "goal0": f"arco de {name(0)}",
                                 "goal1": f"arco de {name(1)}", "ball": "pelota"}.get(x, x)
                                for x in m["targets"])
            txt = f"{who}: {pdef.name}" + (f"  (sobre {targets})" if targets else "")
            self.toast(txt, col, m["power"])
        elif t == P.EV_POWER_SPAWN:
            fx.power_spawn(m["x"], m["y"], CATEGORY_COLORS[POWERS_BY_ID[m["power"]].category])
            au.play("spawn")
        elif t == P.EV_PICKUP_EXPIRED:
            fx.vanish(m["x"], m["y"])
        elif t == P.EV_BOMB_ARMED:
            au.play("bomb_tick")
        elif t == P.EV_BOMB_EXPLODE:
            fx.explosion(m["x"], m["y"], m["radius"])
            au.play("explosion")
        elif t == P.EV_KICK:
            au.play("whoosh", self.WHOOSH_VOLUME)
        elif t == P.EV_KICK_BLOCKED:
            au.play("blocked")
            if st:
                p = st["players"][m["player"]]
                fx.kick_blocked(p["x"], p["y"], p["facing"])
        elif t == P.EV_TOUCH:
            kind, sp = m["kind"], m.get("speed", 0)
            k = min(1.0, sp / self.HARD_HIT_SPEED)       # fuerza del golpe, de 0 a 1
            if kind == "kick":
                au.play("kick")
                fx.kick_impact(m["x"], m["y"])
            elif kind == "head":
                au.play("header", by_strength(self.HEADER_MIN_VOLUME, k))
                fx.impact(m["x"], m["y"], by_strength(self.HEADER_MIN_FLASH, k))
            elif kind == "bar":
                au.play("post", by_strength(self.BAR_MIN_VOLUME, k))
                fx.impact(m["x"], m["y"], k)
            elif kind == "floor":
                au.play("bounce", by_strength(self.BOUNCE_MIN_VOLUME, k))
                if sp > self.DUST_SPEED:
                    fx.dust(m["x"], Arena.FLOOR_Y, k)
            else:
                au.play("bounce", by_strength(self.BOUNCE_MIN_VOLUME, k))

    def toast(self, txt, color, power=None):
        self.toasts.append([txt, color, self.TOAST_TIME, power])
        self.toasts = self.toasts[-self.MAX_TOASTS:]

    # ------------------------------------------------------------------ ciclo
    def update(self, dt):
        super().update(dt)
        self.renderer.update(dt)
        self.app.fx.update(dt)
        self.pause_menu.enabled = self.pause_state == "paused"
        self.pause_menu.update(dt)
        for tst in self.toasts:
            tst[2] -= dt
        self.toasts = [t for t in self.toasts if t[2] > 0]
        st = self.state
        # los controles viajan en cada cuadro (también sirven de latido para el watchdog)
        active = (st is not None and self.pause_state is None and not st["paused"]
                  and st["phase"] == P.PHASE_PLAYING)
        self.app.link.send_input(self.controls(active))
        self.app.audio.crowd(st is not None and not st["paused"] and self.pause_state is None)
        if st and st["phase"] == P.PHASE_COUNTDOWN and not st["paused"]:
            n = math.ceil(st["phase_left"])
            if n != self.last_count:
                self.last_count = n
                self.app.audio.play("beep")
        else:
            self.last_count = None
        if st:
            for p in st["players"]:
                if p["frozen"]:
                    self.app.fx.frozen(self.t, p["x"], p["y"], p["scale"])
        if self.end_info is not None:
            self.end_timer -= dt
            if self.end_timer <= 0:
                self.on_match_over()

    # ------------------------------------------------------------------ dibujo
    def draw(self, surf):
        st = self.state
        if st is None:
            surf.blit(self.app.background, (0, 0))
            dim(surf, VEIL_OVERLAY)
            msg = "Preparando partido..." if self.waiting != "restart" else "Reiniciando partido..."
            title(surf, msg, (CENTER_X, self.MESSAGE_Y), FONT_LARGE, C.WHITE)
            draw_text(surf, "Esperando la confirmación de la simulación", FONT_SMALL, (CENTER_X, self.MESSAGE_NOTE_Y),
                      C.INK, outline=C.WHITE)
            return
        off = self.app.fx.shake_offset()
        self.renderer.draw_world(surf, st, off)
        self.app.fx.draw(surf, off)
        self.renderer.draw_hud(surf, st)
        self.renderer.draw_center_messages(surf, st)
        self._draw_toasts(surf)
        if self.end_info is not None:
            title(surf, "¡FINAL DEL PARTIDO!", (CENTER_X, self.MESSAGE_Y), FONT_TITLE_L, C.WHITE)
        if self.app.options.test_mode:
            self._draw_test_panel(surf)
        self.pause_button.visible = self.pause_state is None and self.end_info is None
        self.pause_button.draw(surf, self.t)
        if self.pause_state is not None:
            self._draw_pause(surf)

    def _draw_toasts(self, surf):
        for k, (txt, col, left, power) in enumerate(self.toasts):
            if left < self.TOAST_BLINK_TIME and int(left * self.TOAST_BLINK_HZ) % 2:
                continue                                  # parpadeo retro al desaparecer
            img = text(txt, FONT_SMALL, C.INK, outline=None)
            w = img.get_width() + self.TOAST_PADDING + (self.TOAST_ICON_ROOM if power else 0)
            r = pygame.Rect(0, 0, w, self.TOAST_H)
            r.midtop = (CENTER_X, self.TOAST_TOP + k * self.TOAST_STEP)
            inner = bevel_box(surf, r, C.CREAM)
            pygame.draw.rect(surf, col, (inner.left, inner.top, self.TOAST_BAR_W, inner.height))
            x = inner.left + self.TOAST_TEXT_X
            if power:
                surf.blit(power_icon(power, self.TOAST_ICON), (x, r.centery - self.TOAST_ICON // 2))
                x += self.TOAST_ICON_ADVANCE
            surf.blit(img, (x, r.centery - img.get_height() // 2))

    def _draw_test_panel(self, surf):
        power = POWER_IDS[self.test_sel]
        pdef = POWERS_BY_ID[power]
        r = pygame.Rect(self.TEST_PANEL)
        inner = bevel_box(surf, r, C.GOLD)
        surf.blit(power_icon(power, self.TEST_ICON), (inner.left + self.TEST_ICON_INSET,
                                                      inner.top + self.TEST_ICON_INSET))
        first, second = self.TEST_LINE_Y
        draw_text(surf, f"MODO PRUEBA - {pdef.name}", FONT_SMALL, (inner.left + self.TEST_TEXT_X, inner.top + first),
                  C.INK, anchor="topleft", outline=None)
        draw_text(surf, "F5/F6 elegir  F7 generar  F8 dar al de la izq.  F9 al de la der.  F12 fallo", FONT_SMALL,
                  (inner.left + self.TEST_TEXT_X, inner.top + second), C.INK, anchor="topleft", outline=None)

    def _draw_pause(self, surf):
        dim(surf, VEIL_OVERLAY)
        r = pygame.Rect((0, 0), self.PAUSE_BOX)
        r.center = self.PAUSE_CENTER
        inner = panel(surf, r)
        title(surf, "PAUSA", (CENTER_X, inner.top + self.PAUSE_TITLE_Y), FONT_TITLE)
        reason = {P.PAUSE_REASON_FOCUS: "La ventana perdió el foco: se liberaron los controles.",
                  P.PAUSE_REASON_WATCHDOG: "Pausa automática: la simulación dejó de recibir controles."}.get(
            self.pause_reason, "El reloj, los poderes y las bombas están detenidos.")
        for k, ln in enumerate(wrap(reason, FONT_SMALL, inner.width - self.PAUSE_TEXT_MARGIN)):
            draw_text(surf, ln, FONT_SMALL, (CENTER_X, inner.top + self.PAUSE_REASON_Y + k * TEXT_LINE_H), C.INK,
                      outline=None)
        if self.pause_state == "paused":
            self.pause_menu.draw(surf)
        else:
            msg = {"requested": "Pausando... esperando confirmación de la simulación",
                   "resuming": "Reanudando..."}.get(self.pause_state, "")
            draw_text(surf, msg, FONT_SMALL, (CENTER_X, r.centery + self.PAUSE_STATUS_Y), C.INK, outline=None)

    def debug_info(self):
        st = self.state or {}
        f = self.filter
        return {
            "match": self.match_id, "phase": st.get("phase", "—"), "paused": st.get("paused"),
            "seq": st.get("seq", "—"), "tick": st.get("tick", "—"), "clock": st.get("clock"),
            "filtered": f"{f.rejected_old_match} de otro partido, {f.rejected_stale} viejos",
            "sim_dropped": st.get("dropped_states", 0), "cosmetic_dropped": st.get("dropped_cosmetic", 0),
            "ignored_events": self.ignored_events, "ui_pause": self.pause_state or "—",
        }


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------
class ResultScreen(Screen):
    MENU_CENTER = (CENTER_X, 560)      # botones Revancha / Elegir personajes / Menú principal
    MENU_W = 380                       # ancho de esos botones
    MENU_BUTTON_H = 52                 # alto de esos botones (más bajos que los del menú: son tres)
    MENU_GAP = 10                      # px entre esos botones
    MENU_FONT = 26                     # tamaño de letra de esos botones
    PLAYER_X = (330, 950)              # x de cada jugador
    FEET_Y = 470                       # y de los pies de los jugadores
    NAME_Y = 500                       # nombre de cada jugador
    WINNER_SCALE = 2.4                 # el ganador se ve más grande...
    LOSER_SCALE = 1.8                  # ...que el que perdió (o los dos, si empataron)
    CONFETTI_EVERY = 1.4               # s entre tandas de papelitos sobre el ganador
    CONFETTI_Y = 380                   # altura de donde salen esos papelitos
    HEADLINE_Y = 80                    # "¡GANÓ ...!" / "¡EMPATE!"
    SCORE_CENTER = (CENTER_X, 290)     # tablero con el resultado
    SCORE_W = 300                      # ancho del tablero

    def __init__(self, app, chars, end_info, last_state):
        super().__init__(app)
        self.chars = chars
        self.score = end_info["score"]
        self.winner = end_info["winner"]
        self.menu = Menu([("Revancha", self.rematch), ("Elegir personajes", self.choose),
                          ("Menú principal", self.to_menu)], self.MENU_CENTER, width=self.MENU_W,
                         height=self.MENU_BUTTON_H, gap=self.MENU_GAP, size=self.MENU_FONT)
        self.confetti_t = 0.0

    def enter(self):
        self.app.audio.crowd(False)
        self.app.fx.clear()

    def name(self, i):
        """Nombre del personaje; si ambos eligieron el mismo, se aclara el lado."""
        n = short_name(CHARACTERS_BY_ID[self.chars[i]])
        if self.chars[0] == self.chars[1]:
            n += " (izq.)" if i == 0 else " (der.)"
        return n

    def rematch(self):
        self.app.switch(MatchScreen(self.app, self.chars))

    def choose(self):
        self.app.switch(SelectScreen(self.app, preselect=self.chars))

    def to_menu(self):
        self.app.switch(MenuScreen(self.app))

    def handle_event(self, ev):
        self.menu.handle_event(ev, self.app.audio)

    def update(self, dt):
        super().update(dt)
        self.menu.update(dt)
        self.app.fx.update(dt)
        self.confetti_t -= dt
        if self.winner is not None and self.confetti_t <= 0:
            self.confetti_t = self.CONFETTI_EVERY
            x = self.PLAYER_X[self.winner]
            self.app.fx.confetti(x, self.CONFETTI_Y, [PLAYER_COLORS[self.winner], C.WHITE, C.GOLD])

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_RESULT)
        sp = self.app.sprites
        for i in (0, 1):
            cid = self.chars[i]
            x = self.PLAYER_X[i]
            win = self.winner == i
            ang, bob = celebrate_pose(self.t) if win else idle_pose(self.t, i)
            img, (fx, fy) = sp.player(cid, FACING[i], ang, bob, PLAYER_COLORS[i], False,
                                      self.WINNER_SCALE if win else self.LOSER_SCALE)
            surf.blit(img, (x - fx, self.FEET_Y - fy))
            draw_text(surf, self.name(i), FONT_TEXT, (x, self.NAME_Y), PLAYER_COLORS[i], outline=C.INK)
        self.app.fx.draw(surf)
        if self.winner is None:
            head, col = "¡EMPATE!", C.WHITE
        else:
            head, col = f"¡GANÓ {self.name(self.winner).upper()}!", PLAYER_COLORS[self.winner]
        title(surf, head, (CENTER_X, self.HEADLINE_Y), FONT_TITLE_L, col)
        scoreboard(surf, self.SCORE_CENTER, self.SCORE_W, f"{self.score[0]}-{self.score[1]}")
        self.menu.draw(surf)
        footer(surf, "Revancha: mismos personajes  -  Elegir personajes: volver a la selección")
