"""Pantallas del modo online (versión de escritorio y navegador).

Flujo:  nombre de usuario -> lista de salas -> (crear sala) -> sala: elegir
personaje y "listo" -> partido -> resultado -> revancha / cambiar personaje /
salir.

Todas leen app.net (NetClient), que se actualiza con cada mensaje del
servidor: nada se pierde al cambiar de pantalla. La simulación corre en el
servidor; estas pantallas sólo mandan controles y pedidos (pausa, listo,
abandonar) y dibujan lo que llega.

Las medidas son px en la resolución lógica de 1280 x 720 (ver layout.py).
"""
import math
import time

import pygame

from .. import protocol as P
from ..config import MS_PER_SECOND, PLAYER_COLORS
from ..online import client as NC
from ..online import wire as W
from ..online.interp import Interpolator
from ..online.lobby import ROOM_NAME_MAX
from . import palette as C
from .assets import draw_text, text_width, wrap
from .characters import CHARACTER_IDS, CHARACTERS_BY_ID, short_name
from .layout import (BUTTON_H, BUTTON_SMALL_H, CENTER_X, FONT_BANNER, FONT_GIANT, FONT_LARGE, FONT_SMALL, FONT_TEXT,
                     FONT_TITLE, FONT_TITLE_L, FONT_TITLE_S, FONT_TITLE_XL, SCREEN_H, SCREEN_MARGIN, SCREEN_W,
                     TEXT_LINE_H, TEXT_LINE_H_BIG, VEIL_ERROR, VEIL_LIST, VEIL_ONLINE, VEIL_OVERLAY, VEIL_RESULT)
from .match_screens import (FACING, PLAYER_X, SELECTION_LINE, SELECTION_MARGIN, MatchScreen, SelectScreen, card_rect,
                            choice_buttons, draw_card)
from .retro import bevel_box
from .screens import BackButton, Menu, Screen, bouncing_ball, button, dim, footer, panel, scoreboard, title
from .sprites import celebrate_pose, idle_pose
from .widgets import CheckBox, TextField

CONTROLS_HELP = "Moverse: A/D o flechas  -  Saltar: W o flecha arriba  -  Patear: Espacio o P  -  Pausa: Esc"
ROOM_STATES = {"esperando": "esperando rival", "eligiendo": "eligiendo personajes", "jugando": "jugando"}
ME_COLOR, RIVAL_COLOR = C.GOLD, C.BLUE        # en la sala todavía no hay lados
PASSWORD_MAX_LEN = 24              # caracteres que se pueden escribir en una contraseña de sala
NOTICE_TIME = 4.0                  # s que se muestra un aviso abajo al centro

# --- candado de las salas con contraseña: (x, y relativos al centro, ancho, alto)
LOCK_BODY = (-9, -1, 18, 13)       # cuerpo
LOCK_SHACKLE = (-6, -11, 12, 12)   # arco de arriba
LOCK_SHACKLE_LINE = 3              # px: grosor del arco
LOCK_KEYHOLE = (-2, 3, 4, 5)       # cerradura dorada
# --- estado de la conexión (arriba a la derecha; abajo durante el partido)
CHIP_H = 32                        # px: alto
CHIP_PADDING = 40                  # px que se suman al texto (punto de color y márgenes)
CHIP_BOTTOM_MARGIN = (12, 8)       # px desde la esquina inferior derecha durante el partido (x, y)
CHIP_BLINK_HZ = 3                  # parpadeo del punto rojo mientras reconecta
CHIP_DOT_X = 12                    # punto de color, desde el borde izquierdo
CHIP_DOT_R = 6                     # px: radio del punto
CHIP_TEXT_X = 24                   # texto, desde el borde izquierdo
# --- aviso abajo al centro
MESSAGE_BLINK_TIME = 0.3           # s finales en los que el aviso parpadea antes de irse
MESSAGE_BLINK_HZ = 20              # cambios por segundo de ese parpadeo
MESSAGE_MAX_W = 800                # px: ancho máximo del texto (después pasa al renglón siguiente)
MESSAGE_PADDING = 40               # px que se suman al texto más largo
MESSAGE_PAD_Y = 18                 # px que se suman a los renglones
MESSAGE_BOTTOM = 676               # borde inferior (justo arriba del pie de página)
MESSAGE_BAR_W = 6                  # franja de color a la izquierda
MESSAGE_TEXT_Y = 13                # primer renglón, desde arriba del aviso


def lock_icon(surf, center, color=C.INK):
    """Candado pixel art (salas con contraseña)."""
    x, y = center

    def at(rect):
        dx, dy, w, h = rect
        return x + dx, y + dy, w, h

    pygame.draw.rect(surf, color, at(LOCK_BODY))
    pygame.draw.rect(surf, color, at(LOCK_SHACKLE), LOCK_SHACKLE_LINE)
    pygame.draw.rect(surf, C.GOLD, at(LOCK_KEYHOLE))


def status_chip(surf, net, t, bottom=False):
    """Estado de la conexión (arriba a la derecha, o abajo durante el partido)."""
    if net.status == NC.RECONNECTING:
        txt, col = f"RECONECTANDO... {net.reconnect_left() or 0:.0f} s", C.RED
    elif net.connected:
        rtt = f"  {net.rtt * MS_PER_SECOND:.0f} ms" if net.rtt is not None else ""
        txt, col = f"{net.display}{rtt}", C.GREEN
    elif net.status == NC.CONNECTING:
        txt, col = "CONECTANDO...", C.GOLD_DARK
    else:
        return
    r = pygame.Rect(0, 0, text_width(txt, FONT_SMALL) + CHIP_PADDING, CHIP_H)
    if bottom:
        margin_x, margin_y = CHIP_BOTTOM_MARGIN
        r.bottomright = (SCREEN_W - margin_x, SCREEN_H - margin_y)
    else:
        r.topright = (SCREEN_W - SCREEN_MARGIN, SCREEN_MARGIN)
    inner = bevel_box(surf, r, C.CREAM, shadow=False)
    if net.status != NC.RECONNECTING or int(t * CHIP_BLINK_HZ) % 2 == 0:
        pygame.draw.circle(surf, col, (inner.left + CHIP_DOT_X, inner.centery), CHIP_DOT_R)
    draw_text(surf, txt, FONT_SMALL, (inner.left + CHIP_TEXT_X, inner.centery), C.INK, anchor="midleft", outline=None)


def message_box(surf, msg):
    """Aviso breve abajo al centro (errores del servidor, confirmaciones)."""
    txt, col, left = msg
    if left < MESSAGE_BLINK_TIME and int(left * MESSAGE_BLINK_HZ) % 2:
        return
    lines = wrap(txt, FONT_SMALL, MESSAGE_MAX_W)
    r = pygame.Rect(0, 0, max(text_width(ln, FONT_SMALL) for ln in lines) + MESSAGE_PADDING,
                    TEXT_LINE_H * len(lines) + MESSAGE_PAD_Y)
    r.midbottom = (CENTER_X, MESSAGE_BOTTOM)
    inner = bevel_box(surf, r, C.CREAM)
    pygame.draw.rect(surf, col, (inner.left, inner.top, MESSAGE_BAR_W, inner.height))
    for k, ln in enumerate(lines):
        y = inner.top + MESSAGE_TEXT_Y + k * TEXT_LINE_H
        draw_text(surf, ln, FONT_SMALL, (inner.centerx + MESSAGE_BAR_W // 2, y), C.INK, outline=None)


def members(net):
    """(yo, rival) en la sala actual (cualquiera puede ser None)."""
    room = net.room
    if not room:
        return None, None
    me = next((m for m in room["members"] if net.is_me(m)), None)
    rival = next((m for m in room["members"] if not net.is_me(m)), None)
    return me, rival


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class OnlineScreen(Screen):
    IN_ROOM = False              # True: si dejo de estar en una sala, vuelvo a la lista
    NEEDS_CONNECTION = True      # True: si se pierde la conexión, pantalla de error
    BACK_LABEL = "◄ VOLVER"

    def __init__(self, app):
        super().__init__(app)
        self.net = app.online()
        self.back_button = BackButton(self.back, self.BACK_LABEL)
        self.message = None

    def back(self):
        pass

    def notify(self, txt, color=C.RED, secs=NOTICE_TIME):
        self.message = (txt, color, secs)

    def handle_back(self, ev):
        """Botón "Volver" o Esc. True si se usó."""
        if self.back_button.handle_event(ev):
            self.app.audio.play("back")
            return True
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE and self.back_button.visible:
            self.app.audio.play("back")
            self.back()
            return True
        return False

    def on_net(self, msg):
        t = msg["type"]
        if t == W.ERROR:
            self.notify(msg["message"])
        elif t == W.MATCH_START:
            self.app.switch(OnlineMatchScreen(self.app, msg))
        elif t == W.ROOMS and self.IN_ROOM:
            self.app.switch(RoomsScreen(self.app, "Ya no estás en esa sala."))

    def update(self, dt):
        super().update(dt)
        if self.message:
            txt, col, left = self.message
            self.message = (txt, col, left - dt) if left - dt > 0 else None
        if self.NEEDS_CONNECTION and self.net.fatal:
            self.app.switch(OnlineErrorScreen(self.app, self.net.fatal))

    def draw_common(self, surf):
        status_chip(surf, self.net, self.t)
        if self.message:
            message_box(surf, self.message)
        self.back_button.draw(surf, self.t)


# ---------------------------------------------------------------------------
# Entrada al online: se conecta con el nombre del perfil (elegido al empezar)
# ---------------------------------------------------------------------------
class OnlineHomeScreen(OnlineScreen):
    NEEDS_CONNECTION = False
    TITLE_Y = 96                       # "JUGAR ONLINE"
    BOX = (330, 220, 620, 280)         # recuadro central (x, y, ancho, alto)
    CONNECTING_Y = 50                  # "Conectando como ...", desde arriba del recuadro
    BALL_GROUND = 150                  # pelota que pica: piso, desde arriba del recuadro
    BALL_HOP = 40                      # px que sube
    BALL_HOP_HZ = 5                    # rebotes por segundo (de ida)
    BALL_SPIN = 400                    # grados por segundo que gira
    TAG_NOTE_BOTTOM = 30               # aclaración de la etiqueta, desde abajo del recuadro
    FAILED_Y = 44                      # "No se pudo entrar al online", desde arriba del recuadro
    FAILED_DETAIL_Y = 90               # el motivo, desde arriba del recuadro
    FAILED_LINES = 3                   # renglones del motivo que entran
    FAILED_MARGIN = 40                 # px de aire a los costados del motivo
    RETRY_SIZE = (280, BUTTON_H)       # botón "REINTENTAR" (ancho, alto)
    RETRY_CENTER = (CENTER_X, 440)     # centro de ese botón
    INFO = (1000, 104)                 # recuadro de ayuda de abajo (ancho, alto)
    INFO_TOP = 546                     # borde superior de ese recuadro
    INFO_LINE_Y = (20, 46, 72)         # sus tres renglones, desde arriba del recuadro

    def __init__(self, app):
        super().__init__(app)
        self.retry_rect = pygame.Rect((0, 0), self.RETRY_SIZE)
        self.retry_rect.center = self.RETRY_CENTER
        self.hover = False
        self.failed = None
        saved = NC.saved_session()
        if saved and self.net.status == NC.IDLE:
            self.net.token = saved[1]   # se recargó la página: vuelve a su sala y partido
        self.connect()

    def connect(self):
        profile = self.app.profile
        self.failed = None
        self.net.connect(profile.name, profile.player_id)

    def back(self):
        self.app.close_online()
        from .screens import MultiplayerMenuScreen
        self.app.switch(MultiplayerMenuScreen(self.app))

    def handle_event(self, ev):
        if self.handle_back(ev):
            return
        if self.failed is None:
            return
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.retry_rect.collidepoint(ev.pos)
        elif ((ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.retry_rect.collidepoint(ev.pos))
              or (ev.type == pygame.KEYDOWN and ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE))):
            self.app.audio.play("confirm")
            self.connect()

    def on_net(self, msg):
        if msg["type"] == W.WELCOME:
            self.app.switch(RoomsScreen(self.app))
        elif msg["type"] == W.ERROR:
            self.failed = msg["message"]

    def update(self, dt):
        super().update(dt)
        if self.failed is None and self.net.fatal:
            self.failed = self.net.fatal

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_ONLINE)
        title(surf, "JUGAR ONLINE", (CENTER_X, self.TITLE_Y), FONT_TITLE_XL)
        box = panel(surf, pygame.Rect(self.BOX))
        name = self.app.profile.name
        if self.failed is None:
            draw_text(surf, f"Conectando como {name}...", FONT_TEXT, (CENTER_X, box.top + self.CONNECTING_Y), C.INK,
                      outline=None)
            bouncing_ball(self.app, surf, self.t, CENTER_X, box.top + self.BALL_GROUND, self.BALL_HOP, self.BALL_HOP_HZ,
                          self.BALL_SPIN)
            draw_text(surf, "Si otra persona usa tu mismo nombre, los distingue una etiqueta (#1234).", FONT_SMALL,
                      (CENTER_X, box.bottom - self.TAG_NOTE_BOTTOM), C.INK_SOFT, outline=None)
        else:
            draw_text(surf, "No se pudo entrar al online", FONT_TEXT, (CENTER_X, box.top + self.FAILED_Y), C.RED,
                      outline=None)
            lines = wrap(self.failed, FONT_SMALL, box.width - self.FAILED_MARGIN)[:self.FAILED_LINES]
            for k, ln in enumerate(lines):
                draw_text(surf, ln, FONT_SMALL, (CENTER_X, box.top + self.FAILED_DETAIL_Y + k * TEXT_LINE_H), C.INK,
                          outline=None)
            button(surf, self.retry_rect, "REINTENTAR", self.hover, True, FONT_TEXT, self.t)
        info = pygame.Rect((0, 0), self.INFO)
        info.midtop = (CENTER_X, self.INFO_TOP)
        inner = panel(surf, info)
        first, second, third = self.INFO_LINE_Y
        draw_text(surf, CONTROLS_HELP, FONT_SMALL, (CENTER_X, inner.top + first), C.INK, outline=None)
        draw_text(surf, "Cada persona juega desde su casa; el servidor sortea los lados al empezar.", FONT_SMALL,
                  (CENTER_X, inner.top + second), C.INK_SOFT, outline=None)
        if not self.app.web:
            draw_text(surf, f"Servidor: {self.net.url}", FONT_SMALL, (CENTER_X, inner.top + third), C.INK_SOFT,
                      outline=None)
        self.draw_common(surf)


# ---------------------------------------------------------------------------
# Lista de salas
# ---------------------------------------------------------------------------
class RoomsScreen(OnlineScreen):
    ROW_H = 58                         # px por sala en la lista
    ROW_GAP = 6                        # px libres entre salas
    VISIBLE = 6                        # salas visibles a la vez (las demás, con la rueda o W/S)
    LIST_PADDING = 8                   # px de aire dentro del recuadro de la lista
    LIST = pygame.Rect(150, 168, 980, VISIBLE * ROW_H + 2 * LIST_PADDING)   # recuadro de la lista
    HEADER_ROOM = 36                   # px que se agranda el recuadro hacia arriba para los títulos de columna
    HEADER_Y = 10                      # títulos de columna, desde arriba del recuadro
    # columnas: (título, x desde el borde izquierdo de la lista)
    COLUMNS = (("SALA", 30), ("CREADA POR", 400), ("JUGADORES", 650), ("ESTADO", 790))
    LOCK_X = 16                        # candado, desde el borde izquierdo de la fila
    NAME_X = 38                        # nombre de la sala, desde el borde izquierdo de la fila
    OWNER_X = 400                      # quien la creó (columna "CREADA POR")
    PLAYERS_X = 690                    # "1/2", centrado bajo "JUGADORES"
    STATE_X = 790                      # estado (columna "ESTADO")
    PAGER_GAP = 8                      # "1-6 de 9", debajo de la lista
    TITLE_Y = 64                       # "SALAS"
    GREETING_Y = 116                   # "Hola, ... Elegí una sala..."
    BUTTONS_Y = 572                    # botones CREAR SALA / ACTUALIZAR
    BUTTON_W = 260                     # ancho de esos botones
    BUTTON_GAP = 20                    # px entre esos botones (y entre los del pedido de contraseña)
    PROMPT_BOX = (560, 250)            # recuadro para escribir la contraseña (ancho, alto)
    PROMPT_CENTER = (CENTER_X, 400)    # centro de ese recuadro
    PROMPT_FIELD = (420, 360, 440, BUTTON_H)   # campo de la contraseña (x, y, ancho, alto)
    PROMPT_BUTTONS_Y = 448             # botones ENTRAR / CANCELAR
    PROMPT_BUTTON = (190, 50)          # cada uno de esos botones (ancho, alto)

    def __init__(self, app, notice=None):
        super().__init__(app)
        self.sel = 0
        self.offset = 0
        self.hover_row = None
        self.hover_btn = None
        self.prompt = None              # (sala, campo de contraseña) para salas privadas
        w, gap = self.BUTTON_W, self.BUTTON_GAP
        self.buttons = {"create": pygame.Rect(CENTER_X - w - gap // 2, self.BUTTONS_Y, w, BUTTON_H),
                        "refresh": pygame.Rect(CENTER_X + gap // 2, self.BUTTONS_Y, w, BUTTON_H)}
        if notice:
            self.notify(notice, C.GOLD)

    @property
    def rooms(self):
        return self.net.rooms

    def back(self):
        """Sale del online: corta la conexión y vuelve a Multijugador (Local / Online)."""
        self.app.close_online()
        from .screens import MultiplayerMenuScreen
        self.app.switch(MultiplayerMenuScreen(self.app))

    def row_rect(self, k):
        pad = self.LIST_PADDING
        return pygame.Rect(self.LIST.left + pad, self.LIST.top + pad + k * self.ROW_H, self.LIST.width - 2 * pad,
                           self.ROW_H - self.ROW_GAP)

    def visible_rooms(self):
        return list(enumerate(self.rooms))[self.offset:self.offset + self.VISIBLE]

    def join(self, room):
        if room["players"] >= room["max_players"]:
            self.notify("La sala está completa.")
            self.app.audio.play("blocked")
            return
        self.app.audio.play("confirm")
        if room["private"]:
            field = TextField(self.PROMPT_FIELD, f"CONTRASEÑA DE «{room['name']}»", PASSWORD_MAX_LEN, password=True,
                              sticky=True)
            field.focus(True)
            self.prompt = (room, field)
            return
        self.net.send({"type": "join_room", "room": room["room"]})

    def scroll_to_sel(self):
        n = len(self.rooms)
        self.sel = max(0, min(self.sel, n - 1))
        if self.sel < self.offset:
            self.offset = self.sel
        elif self.sel >= self.offset + self.VISIBLE:
            self.offset = self.sel - self.VISIBLE + 1

    def _prompt_event(self, ev):
        room, field = self.prompt
        r = field.handle_event(ev)
        if r == "submit" and field.value:
            self.net.send({"type": "join_room", "room": room["room"], "password": field.value})
            self.prompt = None
        elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.prompt = None
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and not r:
            ok, cancel = self._prompt_buttons()
            if ok.collidepoint(ev.pos) and field.value:
                self.net.send({"type": "join_room", "room": room["room"], "password": field.value})
                self.prompt = None
            elif cancel.collidepoint(ev.pos):
                self.prompt = None

    def _prompt_buttons(self):
        w, h = self.PROMPT_BUTTON
        gap = self.BUTTON_GAP
        return (pygame.Rect(CENTER_X - w - gap // 2, self.PROMPT_BUTTONS_Y, w, h),
                pygame.Rect(CENTER_X + gap // 2, self.PROMPT_BUTTONS_Y, w, h))

    def handle_event(self, ev):
        if self.prompt:
            self._prompt_event(ev)
            return
        if self.handle_back(ev):
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_w, pygame.K_UP):
                self.sel -= 1
                self.scroll_to_sel()
            elif ev.key in (pygame.K_s, pygame.K_DOWN):
                self.sel += 1
                self.scroll_to_sel()
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE) and self.rooms:
                self.join(self.rooms[self.sel])
            elif ev.key == pygame.K_c:
                self.app.switch(CreateRoomScreen(self.app))
        elif ev.type == pygame.MOUSEWHEEL:
            self.offset = max(0, min(self.offset - ev.y, max(0, len(self.rooms) - self.VISIBLE)))
        elif ev.type == pygame.MOUSEMOTION:
            self.hover_row = next((i for k, (i, _) in enumerate(self.visible_rooms())
                                   if self.row_rect(k).collidepoint(ev.pos)), None)
            self.hover_btn = next((n for n, r in self.buttons.items() if r.collidepoint(ev.pos)), None)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.buttons["create"].collidepoint(ev.pos):
                self.app.audio.play("confirm")
                self.app.switch(CreateRoomScreen(self.app))
                return
            if self.buttons["refresh"].collidepoint(ev.pos):
                self.app.audio.play("select")
                self.net.send({"type": "list_rooms"})
                return
            for k, (i, room) in enumerate(self.visible_rooms()):
                if self.row_rect(k).collidepoint(ev.pos):
                    self.sel = i
                    self.join(room)
                    return

    def on_net(self, msg):
        if msg["type"] == W.ROOM:
            self.app.switch(RoomScreen(self.app))
            return
        super().on_net(msg)
        if msg["type"] == W.ROOMS:
            self.scroll_to_sel()

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_LIST)
        title(surf, "SALAS", (CENTER_X, self.TITLE_Y), FONT_TITLE_L)
        draw_text(surf, f"Hola, {self.net.display or ''}. Elegí una sala para unirte o creá la tuya.", FONT_SMALL,
                  (CENTER_X, self.GREETING_Y), C.INK, outline=C.WHITE)
        inner = panel(surf, self.LIST.inflate(0, self.HEADER_ROOM).move(0, -self.HEADER_ROOM // 2))
        left = self.LIST.left
        for txt, x in self.COLUMNS:
            draw_text(surf, txt, FONT_SMALL, (left + x, inner.top + self.HEADER_Y), C.INK_SOFT, anchor="midleft",
                      outline=None)
        if not self.rooms:
            draw_text(surf, "Todavía no hay salas: ¡creá la primera!", FONT_TEXT, self.LIST.center, C.INK_SOFT,
                      outline=None)
        for k, (i, room) in enumerate(self.visible_rooms()):
            r = self.row_rect(k)
            full = room["players"] >= room["max_players"]
            face = C.GOLD if i == self.sel or i == self.hover_row else (C.CREAM_DARK if full else C.WHITE)
            rin = bevel_box(surf, r, face, shadow=False)
            if room["private"]:
                lock_icon(surf, (rin.left + self.LOCK_X, rin.centery))
            draw_text(surf, room["name"], FONT_TEXT, (rin.left + self.NAME_X, rin.centery), C.INK, anchor="midleft",
                      outline=None)
            draw_text(surf, room["owner"], FONT_SMALL, (left + self.OWNER_X, rin.centery), C.INK, anchor="midleft",
                      outline=None)
            draw_text(surf, f"{room['players']}/{room['max_players']}", FONT_TEXT, (left + self.PLAYERS_X, rin.centery),
                      C.INK, outline=None)
            draw_text(surf, ROOM_STATES.get(room["state"], room["state"]), FONT_SMALL,
                      (left + self.STATE_X, rin.centery), C.RED if full else C.INK_SOFT, anchor="midleft", outline=None)
        if len(self.rooms) > self.VISIBLE:
            draw_text(surf, f"{self.offset + 1}-{min(len(self.rooms), self.offset + self.VISIBLE)} de "
                            f"{len(self.rooms)} (rueda del mouse o W/S)", FONT_SMALL,
                      (CENTER_X, self.LIST.bottom + self.PAGER_GAP), C.INK_SOFT, outline=None)
        button(surf, self.buttons["create"], "CREAR SALA", self.hover_btn == "create", True, FONT_TEXT, self.t)
        button(surf, self.buttons["refresh"], "ACTUALIZAR", self.hover_btn == "refresh", True, FONT_TEXT, self.t)
        footer(surf, "Clic o Enter: unirse  -  C: crear sala  -  Esc: volver  -  La lista se actualiza sola")
        if self.prompt:
            room, field = self.prompt
            dim(surf, VEIL_OVERLAY)
            box = pygame.Rect((0, 0), self.PROMPT_BOX)
            box.center = self.PROMPT_CENTER
            panel(surf, box)
            field.draw(surf, self.t)
            ok, cancel = self._prompt_buttons()
            button(surf, ok, "ENTRAR", False, bool(field.value), FONT_TEXT, self.t)
            button(surf, cancel, "CANCELAR", False, True, FONT_TEXT, self.t)
        self.draw_common(surf)


# ---------------------------------------------------------------------------
# Crear sala
# ---------------------------------------------------------------------------
class CreateRoomScreen(OnlineScreen):
    TITLE_Y = 96                       # "CREAR SALA"
    BOX = (350, 180, 580, 420)         # recuadro del formulario (x, y, ancho, alto)
    NAME_FIELD = (390, 236, 500, BUTTON_H)     # campo del nombre de la sala (x, y, ancho, alto)
    PRIVATE_BOX = (390, 326, 360, 40)  # casilla "Con contraseña" (x, y, ancho, alto)
    PASSWORD_FIELD = (390, 420, 500, BUTTON_H)  # campo de la contraseña (x, y, ancho, alto)
    FREE_NOTE_Y = 448                  # "Sala libre: ...", en lugar del campo de contraseña
    CREATE_SIZE = (300, BUTTON_H)      # botón "CREAR" (ancho, alto)
    CREATE_CENTER = (CENTER_X, 540)    # centro de ese botón

    def __init__(self, app):
        super().__init__(app)
        user = self.net.username or ""
        self.name = TextField(self.NAME_FIELD, "NOMBRE DE LA SALA", ROOM_NAME_MAX,
                              value=f"Sala de {user}"[:ROOM_NAME_MAX])
        self.private = CheckBox(self.PRIVATE_BOX, "Con contraseña")
        self.password = TextField(self.PASSWORD_FIELD, "CONTRASEÑA", PASSWORD_MAX_LEN, password=True)
        self.create_rect = pygame.Rect((0, 0), self.CREATE_SIZE)
        self.create_rect.center = self.CREATE_CENTER
        self.hover = False
        self.name.focus(True)

    def back(self):
        self.app.switch(RoomsScreen(self.app))

    def create(self):
        name = self.name.value.strip()
        if not name:
            self.notify("Escribí un nombre para la sala.")
            return
        msg = {"type": "create_room", "name": name}
        if self.private.value:
            if not self.password.value:
                self.notify("Escribí la contraseña (o destildá «Con contraseña»).")
                self.password.focus(True)
                return
            msg["password"] = self.password.value
        self.app.audio.play("confirm")
        self.net.send(msg)

    def handle_event(self, ev):
        if self.handle_back(ev):
            return
        self.password.enabled = self.private.value
        if self.private.handle_event(ev):
            self.app.audio.play("select")
            self.password.enabled = self.private.value
            self.name.focus(False)
            self.password.focus(self.private.value)
            return
        for field, other in ((self.name, self.password), (self.password, self.name)):
            r = field.handle_event(ev)
            if r == "submit":
                if field is self.name and self.private.value and not self.password.value:
                    self.name.focus(False)
                    self.password.focus(True)
                else:
                    self.create()
                return
            if r == "tab":
                field.focus(False)
                other.focus(other.enabled)
                return
            if r:
                if field.focused:
                    other.focus(False)
                return
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.create_rect.collidepoint(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.create_rect.collidepoint(ev.pos):
            self.create()

    def on_net(self, msg):
        if msg["type"] == W.ROOM:
            self.app.switch(RoomScreen(self.app))
            return
        super().on_net(msg)

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_LIST)
        title(surf, "CREAR SALA", (CENTER_X, self.TITLE_Y), FONT_TITLE_L)
        panel(surf, pygame.Rect(self.BOX))
        self.name.draw(surf, self.t)
        self.private.draw(surf)
        if self.private.value:
            self.password.draw(surf, self.t)
        else:
            draw_text(surf, "Sala libre: cualquiera de la lista puede entrar.", FONT_SMALL,
                      (CENTER_X, self.FREE_NOTE_Y), C.INK_SOFT, outline=None)
        button(surf, self.create_rect, "CREAR", self.hover, True, FONT_TEXT, self.t)
        footer(surf, "Enter: crear  -  Tab: siguiente campo  -  Esc: volver")
        self.draw_common(surf)


# ---------------------------------------------------------------------------
# Sala: elegir personaje y confirmar
# ---------------------------------------------------------------------------
class RoomScreen(OnlineScreen):
    """Misma disposición que la selección local (match_screens.SelectScreen): yo a la
    izquierda, el rival a la derecha y la fila de tarjetas abajo."""
    IN_ROOM = True
    BACK_LABEL = "◄ SALIR"
    LEFT_KEYS = (pygame.K_a, pygame.K_LEFT)
    RIGHT_KEYS = (pygame.K_d, pygame.K_RIGHT)
    OK_KEYS = (pygame.K_SPACE, pygame.K_p, pygame.K_RETURN, pygame.K_KP_ENTER)
    RESEND_AFTER = 1.0                 # s: si el servidor todavía no muestra mi personaje, se vuelve a mandar
    SUBTITLE_Y = 80                    # "Sala libre de ... - Los lados se sortean..."
    TAG = (320, 70)                    # recuadro con el nombre (más ancho que en la selección local: va la etiqueta)
    HINT_Y = 466                       # ayuda de teclas, debajo de mis botones
    QUESTION_Y = 300                   # "?" en el lugar del rival que todavía no está o no eligió
    DOTS_HZ = 2                        # "ESPERANDO RIVAL...": puntos que se agregan por segundo...
    MAX_DOTS = 3                       # ...hasta tres
    RIVAL_INNER_MARGIN = 2             # si los dos eligieron la misma tarjeta, el marco del rival va por dentro

    def __init__(self, app):
        super().__init__(app)
        me, _ = members(self.net)
        pre = (me and me["character"]) or getattr(app, "last_online_char", None) or CHARACTER_IDS[0]
        self.cursor = CHARACTER_IDS.index(pre)
        self.sent_char = None
        self.sent_at = -math.inf               # todavía no se mandó nada
        self.hover = None

    def back(self):
        self.net.leave_room()
        self.app.switch(RoomsScreen(self.app))

    def choosing(self):
        return bool(self.net.room) and self.net.room["state"] == "eligiendo"

    def buttons(self):
        return choice_buttons(PLAYER_X[0])

    def my_ready(self):
        me, _ = members(self.net)
        return bool(me and me["ready"])

    def move(self, d):
        if self.my_ready():
            return
        self.cursor = (self.cursor + d) % len(CHARACTER_IDS)
        self.app.audio.play("select")

    def sync_character(self):
        """Avisa al servidor qué personaje tengo elegido (el rival lo ve al instante)."""
        me, _ = members(self.net)
        if not self.choosing() or me is None:
            return
        cid = CHARACTER_IDS[self.cursor]
        if me["character"] != cid and (cid != self.sent_char or self.t - self.sent_at > self.RESEND_AFTER):
            self.net.send({"type": "choose_character", "character": cid})
            self.sent_char, self.sent_at = cid, self.t
            self.app.last_online_char = cid

    def toggle_ready(self):
        if not self.choosing():
            self.notify("Esperá a que entre un rival.", C.GOLD)
            self.app.audio.play("blocked")
            return
        ready = not self.my_ready()
        if ready:
            self.sync_character()
        self.net.send({"type": "ready", "ready": ready})
        self.app.audio.play("confirm" if ready else "back")

    def handle_event(self, ev):
        if self.handle_back(ev):
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key in self.LEFT_KEYS:
                self.move(-1)
            elif ev.key in self.RIGHT_KEYS:
                self.move(1)
            elif ev.key in self.OK_KEYS:
                self.toggle_ready()
        elif ev.type == pygame.MOUSEMOTION:
            self.hover = next((n for n, r in self.buttons().items() if r.collidepoint(ev.pos)), None)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            b = self.buttons()
            if b["ok"].collidepoint(ev.pos):
                self.toggle_ready()
            elif b["prev"].collidepoint(ev.pos):
                self.move(-1)
            elif b["next"].collidepoint(ev.pos):
                self.move(1)
            elif not self.my_ready():
                for k in range(len(CHARACTER_IDS)):
                    if card_rect(k).collidepoint(ev.pos):
                        self.cursor = k
                        self.app.audio.play("select")

    def update(self, dt):
        super().update(dt)
        if not self.my_ready():
            self.sync_character()

    def _player(self, surf, x, cid, facing, ready, color, scale=SelectScreen.PLAYER_SCALE):
        ang, bob = celebrate_pose(self.t) if ready else idle_pose(self.t)
        img, (fx, fy) = self.app.sprites.player(cid, facing, ang, bob, color, False, scale)
        surf.blit(img, (x - fx, SelectScreen.FEET_Y - fy))

    def _pedestal(self, surf, x):
        ped = pygame.Rect((0, 0), SelectScreen.PEDESTAL)
        ped.midtop = (x, SelectScreen.PEDESTAL_TOP)
        bevel_box(surf, ped, C.STRUCT, shadow=True)

    def _tag(self, surf, x, name, sub, color):
        tag = pygame.Rect((0, 0), self.TAG)
        tag.midtop = (x, SelectScreen.TAG_TOP)
        inner = panel(surf, tag)
        pygame.draw.rect(surf, color, (inner.left, inner.top, inner.width, SelectScreen.TAG_BAR_H))
        draw_text(surf, name, FONT_TEXT, (x, inner.top + SelectScreen.TAG_NAME_Y), C.INK, outline=None)
        draw_text(surf, sub, FONT_SMALL, (x, inner.top + SelectScreen.TAG_TEAM_Y), C.INK_SOFT, outline=None)

    def _ready_sign(self, surf, i):
        """"¡LISTO!" al lado del jugador i (0 = yo, a la izquierda; 1 = el rival)."""
        x = PLAYER_X[i] + SelectScreen.READY_X * FACING[i]
        draw_text(surf, "¡LISTO!", FONT_LARGE, (x, SelectScreen.READY_Y), C.GREEN, kind="title", outline=C.INK,
                  shadow=True)

    def _question(self, surf):
        draw_text(surf, "?", FONT_GIANT, (PLAYER_X[1], self.QUESTION_Y), C.WHITE, kind="title", outline=C.INK,
                  shadow=True)

    def draw(self, surf):
        room = self.net.room
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_OVERLAY)
        if not room:
            self.draw_common(surf)
            return
        me, rival = members(self.net)
        title(surf, room["name"].upper(), (CENTER_X, SelectScreen.TITLE_Y), FONT_TITLE_S)
        kind = "con contraseña" if room["private"] else "libre"
        draw_text(surf, f"Sala {kind} de {room['owner']}  -  Los lados se sortean al empezar el partido", FONT_SMALL,
                  (CENTER_X, self.SUBTITLE_Y), C.INK, outline=C.WHITE)
        # yo
        my_x, rival_x = PLAYER_X
        cid = CHARACTER_IDS[self.cursor]
        ready = bool(me and me["ready"])
        self._pedestal(surf, my_x)
        self._player(surf, my_x, cid, FACING[0], ready, ME_COLOR)
        self._tag(surf, my_x, self.net.display or "", short_name(CHARACTERS_BY_ID[cid]), ME_COLOR)
        b = self.buttons()
        can = self.choosing()
        button(surf, b["prev"], "◄", self.hover == "prev", not ready, FONT_TEXT, self.t)
        button(surf, b["ok"], "CANCELAR" if ready else "¡LISTO!", self.hover == "ok", can, FONT_TEXT, self.t)
        button(surf, b["next"], "►", self.hover == "next", not ready, FONT_TEXT, self.t)
        if ready:
            self._ready_sign(surf, 0)
        # rival
        if rival is None:
            dots = "." * (1 + int(self.t * self.DOTS_HZ) % self.MAX_DOTS)
            self._tag(surf, rival_x, "ESPERANDO RIVAL" + dots, "La sala aparece en la lista de salas", RIVAL_COLOR)
            self._question(surf)
        else:
            rc = rival["character"]
            sub = short_name(CHARACTERS_BY_ID[rc]) if rc else "eligiendo personaje..."
            if not rival.get("connected", True):
                sub = "desconectado: esperando que vuelva"
            self._pedestal(surf, rival_x)
            if rc:
                self._player(surf, rival_x, rc, FACING[1], rival["ready"], RIVAL_COLOR)
            else:
                self._question(surf)
            self._tag(surf, rival_x, rival["display"], sub, RIVAL_COLOR)
            if rival["ready"]:
                self._ready_sign(surf, 1)
        draw_text(surf, "VS", FONT_BANNER, (CENTER_X, SelectScreen.VS_Y), C.WHITE, kind="title", outline=C.INK,
                  shadow=True)
        hint = ("A/D o flechas: elegir  -  Espacio, P o Enter: listo" if can
                else "Cuando entre un rival van a poder confirmar")
        draw_text(surf, hint, FONT_SMALL, (my_x, self.HINT_Y), C.INK, outline=C.WHITE)
        # tarjetas
        sp = self.app.sprites
        for k, c in enumerate(CHARACTER_IDS):
            mine = k == self.cursor
            theirs = rival is not None and rival["character"] == c
            rr = draw_card(surf, sp, k, mine or theirs)
            if mine:
                pygame.draw.rect(surf, ME_COLOR, rr.inflate(2 * SELECTION_MARGIN, 2 * SELECTION_MARGIN), SELECTION_LINE)
            if theirs:
                margin = self.RIVAL_INNER_MARGIN if mine else SELECTION_MARGIN
                pygame.draw.rect(surf, RIVAL_COLOR, rr.inflate(2 * margin, 2 * margin), SELECTION_LINE)
        if room["state"] == "eligiendo" and me and rival and me["ready"] and rival["ready"]:
            draw_text(surf, "¡A LA CANCHA!", FONT_TITLE_S, (CENTER_X, SelectScreen.GO_Y), C.GOLD, kind="title",
                      outline=C.INK, shadow=True)
        footer(surf, "Esc: salir de la sala  -  Mouse: botones y tarjetas")
        self.draw_common(surf)


# ---------------------------------------------------------------------------
# Partido online
# ---------------------------------------------------------------------------
class OnlineMatchScreen(MatchScreen):
    """La simulación corre en el servidor: acá sólo se mandan controles y
    pedidos, y se dibuja (suavizado) lo que llega."""

    INPUT_KEEPALIVE = 0.25     # s: aunque no cambie nada, se repite la foto de controles
    SIDE_BANNER_TIME = 5.0             # s que se muestra "JUGÁS A LA IZQUIERDA/DERECHA" al empezar
    SIDE_BANNER_Y = 440                # altura de ese cartel
    FORFEIT_WAIT = 1.0                 # s entre el fin por abandono y el resultado (por tiempo: FINAL_WAIT)
    MATCH_BUTTON_W = 150               # ancho de los botones "II PAUSA" y "ABANDONAR"
    MATCH_BUTTON_GAP = 8               # px entre esos dos botones (uno debajo del otro)
    PAUSE_MENU_CENTER = (CENTER_X, 500)  # botones "Estoy listo" / "Abandonar" de la pausa
    PAUSE_MENU_W = 340                 # ancho de esos botones
    MENU_BUTTON_H = 50                 # alto de los botones de la pausa y de la confirmación
    MENU_GAP = 12                      # px entre esos botones
    CONFIRM_MENU_CENTER = (CENTER_X, 440)  # botones de "¿ABANDONAR?"
    CONFIRM_MENU_W = 380               # ancho de esos botones
    OVERLAY_CENTER = (CENTER_X, 400)   # centro de los carteles (pausa, sin conexión, abandonar)
    CONFIRM_BOX = (560, 260)           # cartel "¿ABANDONAR?" (ancho, alto)
    CONFIRM_TITLE_Y = 34               # título, desde arriba del cartel
    CONFIRM_TEXT_Y = 80                # explicación, desde arriba del cartel
    OVERLAY_W = 600                    # ancho del cartel de pausa o de conexión cortada
    OVERLAY_H = 230                    # alto del cartel de conexión cortada...
    OVERLAY_PAUSE_H = 360              # ...y del de pausa (lleva botones)
    OVERLAY_TITLE_Y = 40               # título, desde arriba del cartel
    OVERLAY_TEXT_Y = 92                # primer renglón, desde arriba del cartel
    READY_LINES_Y = 156                # "Ale: LISTO" de cada jugador, desde arriba del cartel de pausa

    def __init__(self, app, start):
        players = sorted(start["players"], key=lambda p: p["side"])
        self.start_msg = start
        self.names = [p["display"] for p in players]
        self.you = start["you"]
        super().__init__(app, [p["character"] for p in players])
        self.net = app.online()
        self.match_id = start["match"]
        self.filter.expect(self.match_id)
        self.deduper = P.EventDeduper()
        self.interp = Interpolator()
        self.last_sent = None
        self.last_sent_t = -1.0
        self.confirm = None
        self.side_banner = self.SIDE_BANNER_TIME
        top, w = BackButton.TOP, self.MATCH_BUTTON_W
        self.pause_button = BackButton(self.request_pause, "II PAUSA", rect=(SCREEN_MARGIN, top, w, BUTTON_SMALL_H))
        self.quit_button = BackButton(self.ask_abandon, "ABANDONAR",
                                      rect=(SCREEN_MARGIN, top + BUTTON_SMALL_H + self.MATCH_BUTTON_GAP, w,
                                            BUTTON_SMALL_H))
        self.pause_menu = Menu([("Estoy listo", self.ready_pause), ("Abandonar", self.ask_abandon)],
                               self.PAUSE_MENU_CENTER, width=self.PAUSE_MENU_W, height=self.MENU_BUTTON_H,
                               gap=self.MENU_GAP, size=FONT_TEXT)

    # ------------------------------------------------------------------ ganchos de MatchScreen
    def pause_items(self):
        return []

    def enter(self):
        for cid in set(self.chars):
            self.app.sprites.warm(cid)
        self.app.input.capture = True
        self.app.fx.clear()
        self.waiting = None

    def on_link(self, msgs, state):
        pass                                     # el proceso local no participa del online

    def on_focus_lost(self):
        pass                                     # online no se pausa al perder el foco

    def _on_event(self, m):
        if m["type"] == P.EV_PAUSED:
            return                               # la pausa online llega como pause_info
        super()._on_event(m)

    # ------------------------------------------------------------------ red
    def on_net(self, msg):
        t = msg["type"]
        if t == W.STATE:
            if msg.get("match") == self.match_id and self.filter.accept(msg):
                self.state = msg
                self.interp.push(msg, time.monotonic())
        elif t == W.EVENT:
            e = msg["e"]
            if e.get("match") != self.match_id:
                self.ignored_events += 1
            elif self.deduper.fresh(e):
                self._on_event(e)
        elif t == W.MATCH_OVER and msg.get("match") == self.match_id:
            if self.end_info is None:
                self.end_info = msg
                self.end_timer = self.FINAL_WAIT if msg["reason"] == W.END_TIME else self.FORFEIT_WAIT
                self.app.audio.play("whistle_end")
        elif t == W.MATCH_START and msg["match"] != self.match_id:
            self.app.switch(OnlineMatchScreen(self.app, msg))
        elif t == W.PAUSE_INFO and msg["status"] == W.PAUSE_ACTIVE:
            self.app.input.release_all()
        elif t == W.ROOMS:
            self.app.switch(RoomsScreen(self.app, "Ya no estás en esa sala."))
        elif t == W.ERROR:
            self.toast(msg["message"], C.RED)

    # ------------------------------------------------------------------ acciones
    def overlay(self):
        """Qué cartel tapa el partido: None, "self", "opponent" o "pause"."""
        if self.net.status == NC.RECONNECTING:
            return "self"
        opp = self.net.opponent
        if opp and not opp["connected"]:
            return "opponent"
        if self.net.pause.get("status") == W.PAUSE_ACTIVE:
            return "pause"
        return None

    def request_pause(self, reason=None):
        if self.state is None or self.end_info is not None:
            return
        if self.net.pause.get("status") != W.PAUSE_NONE:
            return
        self.net.send({"type": W.PAUSE_REQUEST})
        self.app.audio.play("confirm")
        self.toast("Pediste la pausa: se activa después del próximo gol", C.GOLD)

    def ready_pause(self):
        self.net.send({"type": W.PAUSE_READY})

    def ask_abandon(self):
        if self.end_info is not None:
            return
        self.confirm = Menu([("No, seguir jugando", self.close_confirm), ("Sí, abandonar", self.abandon)],
                            self.CONFIRM_MENU_CENTER, width=self.CONFIRM_MENU_W, height=self.MENU_BUTTON_H,
                            gap=self.MENU_GAP, size=FONT_TEXT)

    def close_confirm(self):
        self.confirm = None

    def abandon(self):
        self.net.abandon()
        self.app.switch(RoomsScreen(self.app, "Abandonaste el partido."))

    def handle_event(self, ev):
        if self.confirm is not None:
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.confirm = None
            else:
                self.confirm.handle_event(ev, self.app.audio)
            return
        overlay = self.overlay()
        self.quit_button.visible = self.end_info is None
        self.pause_button.visible = (overlay is None and self.end_info is None
                                     and self.net.pause.get("status") == W.PAUSE_NONE)
        if self.quit_button.handle_event(ev) or self.pause_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if overlay == "pause":
                self.ready_pause()
            elif overlay is None:
                self.request_pause()
            return
        if overlay == "pause":
            self.pause_menu.handle_event(ev, self.app.audio)

    # ------------------------------------------------------------------ ciclo
    def update(self, dt):
        Screen.update(self, dt)
        self.renderer.update(dt)
        self.app.fx.update(dt)
        self.side_banner -= dt
        for tst in self.toasts:
            tst[2] -= dt
        self.toasts = [t for t in self.toasts if t[2] > 0]
        overlay = self.overlay()
        self.pause_menu.enabled = overlay == "pause" and self.confirm is None
        self.pause_menu.update(dt)
        if self.confirm is not None:
            self.confirm.update(dt)
        st = self.state
        active = (st is not None and overlay is None and self.confirm is None and not st["paused"]
                  and st["phase"] == P.PHASE_PLAYING)
        snap = self.app.input.snapshot_single(active)       # valen las dos combinaciones de teclas
        now = time.monotonic()
        if snap != self.last_sent or now - self.last_sent_t > self.INPUT_KEEPALIVE:
            self.net.send_input(snap)                       # sólo cuando cambia (y un latido)
            self.last_sent, self.last_sent_t = snap, now
        self.app.audio.crowd(st is not None and not st["paused"] and overlay is None)
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
        pause = self.net.pause
        self.renderer.center_note = (f"{pause.get('by_name')} pidió la pausa"
                                     if pause.get("status") == W.PAUSE_PENDING and self.end_info is None else None)
        if self.end_info is not None:
            self.end_timer -= dt
            if self.end_timer <= 0:
                self.app.switch(OnlineResultScreen(self.app, self.start_msg, self.end_info))
                return
        if self.net.fatal:
            self.app.switch(OnlineErrorScreen(self.app, self.net.fatal))

    # ------------------------------------------------------------------ dibujo
    def draw(self, surf):
        st = self.state
        if st is None:
            surf.blit(self.app.background, (0, 0))
            dim(surf, VEIL_OVERLAY)
            title(surf, "Preparando partido...", (CENTER_X, self.MESSAGE_Y), FONT_LARGE, C.WHITE)
            draw_text(surf, "Esperando al servidor", FONT_SMALL, (CENTER_X, self.MESSAGE_NOTE_Y), C.INK,
                      outline=C.WHITE)
            status_chip(surf, self.net, self.t, bottom=True)
            return
        view = self.interp.sample(time.monotonic()) or st
        off = self.app.fx.shake_offset()
        self.renderer.draw_world(surf, view, off)
        self.app.fx.draw(surf, off)
        self.renderer.draw_hud(surf, st)
        self.renderer.draw_center_messages(surf, st)
        self._draw_toasts(surf)
        overlay = self.overlay()
        if self.side_banner > 0 and overlay is None and self.end_info is None:
            side = "IZQUIERDA" if self.you == 0 else "DERECHA"
            draw_text(surf, f"JUGÁS A LA {side}", FONT_TITLE_S, (CENTER_X, self.SIDE_BANNER_Y),
                      PLAYER_COLORS[self.you], kind="title", outline=C.INK, shadow=True)
        if self.end_info is not None:
            head = "¡FINAL DEL PARTIDO!" if self.end_info["reason"] == W.END_TIME else "¡PARTIDO TERMINADO!"
            title(surf, head, (CENTER_X, self.MESSAGE_Y), FONT_TITLE_L, C.WHITE)
        self.quit_button.visible = self.end_info is None
        self.pause_button.visible = (overlay is None and self.end_info is None
                                     and self.net.pause.get("status") == W.PAUSE_NONE)
        self.pause_button.draw(surf, self.t)
        self.quit_button.draw(surf, self.t)
        if overlay is not None:
            self._draw_overlay(surf, overlay)
        if self.confirm is not None:
            dim(surf, VEIL_OVERLAY)
            box = pygame.Rect((0, 0), self.CONFIRM_BOX)
            box.center = self.OVERLAY_CENTER
            inner = panel(surf, box)
            title(surf, "¿ABANDONAR?", (CENTER_X, inner.top + self.CONFIRM_TITLE_Y), FONT_TITLE_S, C.RED)
            draw_text(surf, "Si abandonás, perdés el partido y salís de la sala.", FONT_SMALL,
                      (CENTER_X, inner.top + self.CONFIRM_TEXT_Y), C.INK, outline=None)
            self.confirm.draw(surf)
        status_chip(surf, self.net, self.t, bottom=True)

    def _draw_overlay(self, surf, overlay):
        dim(surf, VEIL_OVERLAY)
        r = pygame.Rect(0, 0, self.OVERLAY_W, self.OVERLAY_PAUSE_H if overlay == "pause" else self.OVERLAY_H)
        r.center = self.OVERLAY_CENTER
        inner = panel(surf, r)
        title_y = inner.top + self.OVERLAY_TITLE_Y
        if overlay == "self":
            left = self.net.reconnect_left() or 0
            title(surf, "SE CORTÓ TU CONEXIÓN", (CENTER_X, title_y), FONT_LARGE, C.RED)
            lines = [f"Reconectando... ({left:.0f} s)", "El partido está en pausa para los dos.",
                     "Si no volvés a tiempo, perdés por abandono."]
        elif overlay == "opponent":
            opp = self.net.opponent
            left = self.net.countdown(opp) or 0
            title(surf, "SIN CONEXIÓN", (CENTER_X, title_y), FONT_TITLE_S, C.RED)
            lines = [f"{opp['name']} perdió la conexión.", f"Esperando que vuelva: {left:.0f} s",
                     "Si no vuelve, ganás por abandono."]
        else:
            p = self.net.pause
            left = self.net.countdown(p) or 0
            title(surf, "PAUSA", (CENTER_X, title_y), FONT_TITLE)
            lines = [f"Pedida por {p.get('by_name')}.",
                     f"Se sigue jugando en {left:.0f} s o cuando los dos estén listos."]
            for i in (0, 1):
                ok = p.get("ready", [False, False])[i]
                draw_text(surf, f"{self.names[i]}: {'LISTO' if ok else 'esperando...'}", FONT_TEXT,
                          (CENTER_X, inner.top + self.READY_LINES_Y + i * TEXT_LINE_H_BIG),
                          C.GREEN if ok else C.INK_SOFT, outline=None)
            self.pause_menu.draw(surf)
        for k, ln in enumerate(lines):
            big = overlay != "pause" and k == 0
            draw_text(surf, ln, FONT_TEXT if big else FONT_SMALL,
                      (CENTER_X, inner.top + self.OVERLAY_TEXT_Y + k * TEXT_LINE_H_BIG), C.INK, outline=None)

    def debug_info(self):
        info = super().debug_info()
        info["ui_pause"] = self.net.pause.get("status")
        return info


# ---------------------------------------------------------------------------
# Resultado (revancha con lados sorteados de nuevo)
# ---------------------------------------------------------------------------
class OnlineResultScreen(OnlineScreen):
    IN_ROOM = True
    BACK_LABEL = "◄ SALIR"
    MENU_CENTER = (CENTER_X, 590)      # botones Revancha / Cambiar personaje / Salir
    MENU_W = 380                       # ancho de esos botones
    MENU_BUTTON_H = 48                 # alto de esos botones (son tres, debajo del aviso)
    MENU_GAP = 10                      # px entre esos botones
    PLAYER_X = (290, 990)              # x de cada jugador
    FEET_Y = 450                       # y de los pies de los jugadores
    WINNER_SCALE = 2.0                 # el ganador se ve más grande...
    LOSER_SCALE = 1.6                  # ...que el que perdió (o los dos, si empataron)
    CHARACTER_Y = 478                  # nombre del personaje de cada jugador
    NAME_Y = 504                       # nombre de la persona
    CONFETTI_EVERY = 1.4               # s entre tandas de papelitos sobre el ganador
    CONFETTI_Y = 230                   # altura de donde salen esos papelitos
    HEADLINE_Y = 64                    # "¡GANÓ ...!" / "¡EMPATE!"
    SUBTITLE_Y = 124                   # "¡Ganaste!" / "Perdiste" / "... abandonó el partido"
    SCORE_CENTER = (CENTER_X, 270)     # tablero con el resultado
    SCORE_W = 300                      # ancho del tablero
    NOTE_W = 440                       # aviso de la revancha: ancho...
    NOTE_TEXT_W = 400                  # ...y ancho máximo de su texto
    NOTE_PAD_Y = 16                    # px que se suman a los renglones del aviso
    NOTE_TOP = 342                     # borde superior del aviso
    NOTE_TEXT_Y = 11                   # primer renglón, desde arriba del aviso

    def __init__(self, app, start, over):
        super().__init__(app)
        players = sorted(start["players"], key=lambda p: p["side"])
        self.chars = [p["character"] for p in players]
        self.names = [p["display"] for p in players]
        self.you = start["you"]
        self.over = over
        self.winner = over["winner"]
        self.score = over["score"]
        self.menu = None
        self.menu_key = None
        self.confetti_t = 0.0

    def enter(self):
        self.app.audio.crowd(False)
        self.app.fx.clear()

    def char_name(self, i):
        n = short_name(CHARACTERS_BY_ID[self.chars[i]])
        if self.chars[0] == self.chars[1]:
            n += " (izq.)" if i == 0 else " (der.)"
        return n

    def back(self):
        self.net.leave_room()
        self.app.switch(RoomsScreen(self.app))

    def rematch(self):
        me, rival = members(self.net)
        if me is None or rival is None or self.net.room["state"] != "eligiendo":
            return
        self.net.send({"type": "ready", "ready": not me["ready"]})

    def to_room(self):
        self.app.switch(RoomScreen(self.app))

    def build_menu(self):
        me, rival = members(self.net)
        key = (rival is not None, bool(me and me["ready"]))
        if key == self.menu_key:
            return
        self.menu_key = key
        if rival is not None:
            items = [("Cancelar revancha" if key[1] else "Revancha", self.rematch),
                     ("Cambiar personaje", self.to_room), ("Salir de la sala", self.back)]
        else:
            items = [("Esperar otro rival", self.to_room), ("Salir de la sala", self.back)]
        sel = self.menu.sel if self.menu else 0
        self.menu = Menu(items, self.MENU_CENTER, width=self.MENU_W, height=self.MENU_BUTTON_H, gap=self.MENU_GAP,
                         size=FONT_TEXT)
        self.menu.sel = min(sel, len(items) - 1)

    def handle_event(self, ev):
        if self.handle_back(ev):
            return
        if self.menu:
            self.menu.handle_event(ev, self.app.audio)

    def update(self, dt):
        super().update(dt)
        self.build_menu()
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
            x = self.PLAYER_X[i]
            win = self.winner == i
            ang, bob = celebrate_pose(self.t) if win else idle_pose(self.t, i)
            img, (fx, fy) = sp.player(self.chars[i], FACING[i], ang, bob, PLAYER_COLORS[i], False,
                                      self.WINNER_SCALE if win else self.LOSER_SCALE)
            surf.blit(img, (x - fx, self.FEET_Y - fy))
            draw_text(surf, self.char_name(i), FONT_TEXT, (x, self.CHARACTER_Y), PLAYER_COLORS[i], outline=C.INK)
            draw_text(surf, self.names[i], FONT_SMALL, (x, self.NAME_Y), C.INK, outline=C.WHITE)
        self.app.fx.draw(surf)
        if self.winner is None:
            head, col = "¡EMPATE!", C.WHITE
        else:
            head, col = f"¡GANÓ {self.char_name(self.winner).upper()}!", PLAYER_COLORS[self.winner]
        title(surf, head, (CENTER_X, self.HEADLINE_Y), FONT_TITLE_L, col)
        if self.over["reason"] == W.END_FORFEIT:
            sub = f"{self.over.get('by_name')} abandonó el partido"
        elif self.over["reason"] == W.END_ERROR:
            sub = "El partido se cortó por un problema del servidor"
        elif self.winner is None:
            sub = "Nadie ganó esta vez"
        else:
            sub = "¡Ganaste!" if self.winner == self.you else "Perdiste"
        draw_text(surf, sub, FONT_TEXT, (CENTER_X, self.SUBTITLE_Y), C.INK, outline=C.WHITE)
        scoreboard(surf, self.SCORE_CENTER, self.SCORE_W, f"{self.score[0]}-{self.score[1]}")
        me, rival = members(self.net)
        if rival is None:
            status = "Tu rival se fue de la sala: podés esperar a otro."
        elif rival["ready"] and me and me["ready"]:
            status = "¡Revancha! Sorteando los lados..."
        elif rival["ready"]:
            status = f"{rival['display']} quiere la revancha"
        elif me and me["ready"]:
            status = f"Esperando a {rival['display']}..."
        else:
            status = "Revancha: mismos personajes y los lados se sortean de nuevo"
        lines = wrap(status, FONT_SMALL, self.NOTE_TEXT_W)
        note = pygame.Rect(0, 0, self.NOTE_W, TEXT_LINE_H * len(lines) + self.NOTE_PAD_Y)
        note.midtop = (CENTER_X, self.NOTE_TOP)
        inner = bevel_box(surf, note, C.CREAM, shadow=False)
        for k, ln in enumerate(lines):
            draw_text(surf, ln, FONT_SMALL, (CENTER_X, inner.top + self.NOTE_TEXT_Y + k * TEXT_LINE_H), C.INK,
                      outline=None)
        if self.menu:
            self.menu.draw(surf)
        self.draw_common(surf)


# ---------------------------------------------------------------------------
# Conexión perdida
# ---------------------------------------------------------------------------
class OnlineErrorScreen(Screen):
    MENU_CENTER = (CENTER_X, 520)      # botones Reintentar / Volver
    MENU_W = 300                       # ancho de esos botones
    BOX = (900, 240)                   # recuadro del mensaje (ancho, alto)
    BOX_TOP = 150                      # borde superior del recuadro
    TITLE_Y = 40                       # "SIN CONEXIÓN", desde arriba del recuadro
    MESSAGE_Y = 104                    # primer renglón del motivo, desde arriba del recuadro
    MESSAGE_MARGIN = 40                # px de aire a los costados del motivo
    MESSAGE_LINE_H = 32                # px entre renglones del motivo
    HINT_BOTTOM = 22                   # "Revisá tu internet...", desde abajo del recuadro

    def __init__(self, app, message):
        super().__init__(app)
        self.message = message
        self.menu = Menu([("Reintentar", self.retry), ("Volver", self.back)], self.MENU_CENTER, width=self.MENU_W)
        self.back_button = BackButton(self.back)

    def enter(self):
        self.app.audio.crowd(False)
        self.app.input.capture = False

    def retry(self):
        self.app.close_online()
        self.app.switch(OnlineHomeScreen(self.app))

    def back(self):
        self.app.close_online()
        from .screens import MultiplayerMenuScreen
        self.app.switch(MultiplayerMenuScreen(self.app))

    def handle_event(self, ev):
        if self.back_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.back()
            return
        self.menu.handle_event(ev, self.app.audio)

    def update(self, dt):
        super().update(dt)
        self.menu.update(dt)

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_ERROR)
        r = pygame.Rect((0, 0), self.BOX)
        r.midtop = (CENTER_X, self.BOX_TOP)
        inner = panel(surf, r, face=C.ERROR_PANEL, border=C.RED)
        title(surf, "SIN CONEXIÓN", (CENTER_X, inner.top + self.TITLE_Y), FONT_TITLE, C.RED)
        y = inner.top + self.MESSAGE_Y
        for ln in wrap(self.message, FONT_TEXT, inner.width - self.MESSAGE_MARGIN):
            draw_text(surf, ln, FONT_TEXT, (CENTER_X, y), C.INK, outline=None)
            y += self.MESSAGE_LINE_H
        draw_text(surf, "Revisá tu internet o que el servidor esté encendido.", FONT_SMALL,
                  (CENTER_X, inner.bottom - self.HINT_BOTTOM), C.INK_SOFT, outline=None)
        self.menu.draw(surf)
        self.back_button.draw(surf, self.t)
