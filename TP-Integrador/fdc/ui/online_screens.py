"""Pantallas del modo online (versión de escritorio y navegador).

Flujo:  nombre de usuario -> lista de salas -> (crear sala) -> sala: elegir
personaje y "listo" -> partido -> resultado -> revancha / cambiar personaje /
salir.

Todas leen app.net (NetClient), que se actualiza con cada mensaje del
servidor: nada se pierde al cambiar de pantalla. La simulación corre en el
servidor; estas pantallas sólo mandan controles y pedidos (pausa, listo,
abandonar) y dibujan lo que llega.
"""
import math
import time

import pygame

from .. import protocol as P
from ..config import PLAYER_COLORS
from ..online import client as NC
from ..online import wire as W
from ..online.interp import Interpolator
from ..online.lobby import ROOM_NAME_MAX
from . import palette as C
from . import pixelfont
from .assets import draw_text, text_width, wrap
from .characters import CHARACTER_IDS, CHARACTERS_BY_ID, short_name
from .match_screens import MatchScreen
from .retro import bevel_box
from .screens import BackButton, Menu, Screen, button, dim, footer, panel, title
from .widgets import CheckBox, TextField

CONTROLS_HELP = "Moverse: A/D o flechas  -  Saltar: W o flecha arriba  -  Patear: Espacio o P  -  Pausa: Esc"
ROOM_STATES = {"esperando": "esperando rival", "eligiendo": "eligiendo personajes", "jugando": "jugando"}
ME_COLOR, RIVAL_COLOR = C.GOLD, C.BLUE        # en la sala todavía no hay lados


def lock_icon(surf, center, color=C.INK):
    """Candado pixel art (salas con contraseña)."""
    x, y = center
    pygame.draw.rect(surf, color, (x - 9, y - 1, 18, 13))
    pygame.draw.rect(surf, color, (x - 6, y - 11, 12, 12), 3)
    pygame.draw.rect(surf, C.GOLD, (x - 2, y + 3, 4, 5))


def status_chip(surf, net, t, bottom=False):
    """Estado de la conexión (arriba a la derecha, o abajo durante el partido)."""
    if net.status == NC.RECONNECTING:
        txt, col = f"RECONECTANDO... {net.reconnect_left() or 0:.0f} s", C.RED
    elif net.connected:
        rtt = f"  {net.rtt * 1000:.0f} ms" if net.rtt is not None else ""
        txt, col = f"{net.display}{rtt}", C.GREEN
    elif net.status == NC.CONNECTING:
        txt, col = "CONECTANDO...", C.GOLD_DARK
    else:
        return
    r = pygame.Rect(0, 0, text_width(txt, 16) + 40, 32)
    if bottom:
        r.bottomright = (1268, 712)
    else:
        r.topright = (1264, 16)
    inner = bevel_box(surf, r, C.CREAM, shadow=False)
    if net.status != NC.RECONNECTING or int(t * 3) % 2 == 0:
        pygame.draw.circle(surf, col, (inner.left + 12, inner.centery), 6)
    draw_text(surf, txt, 16, (inner.left + 24, inner.centery), C.INK, anchor="midleft", outline=None)


def message_box(surf, msg):
    """Aviso breve abajo al centro (errores del servidor, confirmaciones)."""
    txt, col, left = msg
    if left < 0.3 and int(left * 20) % 2:
        return
    lines = wrap(txt, 16, 800)
    r = pygame.Rect(0, 0, max(text_width(ln, 16) for ln in lines) + 40, 22 * len(lines) + 18)
    r.midbottom = (640, 676)
    inner = bevel_box(surf, r, C.CREAM)
    pygame.draw.rect(surf, col, (inner.left, inner.top, 6, inner.height))
    for k, ln in enumerate(lines):
        draw_text(surf, ln, 16, (inner.centerx + 3, inner.top + 13 + k * 22), C.INK, outline=None)


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

    def notify(self, txt, color=C.RED, secs=4.0):
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

    def __init__(self, app):
        super().__init__(app)
        self.retry_rect = pygame.Rect(0, 0, 280, 56)
        self.retry_rect.center = (640, 440)
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
        dim(surf, 130)
        title(surf, "JUGAR ONLINE", (640, 96), 64)
        box = panel(surf, pygame.Rect(330, 220, 620, 280))
        name = self.app.profile.name
        if self.failed is None:
            draw_text(surf, f"Conectando como {name}...", 24, (640, box.top + 50), C.INK, outline=None)
            self.app.ball_sprite.draw(surf, 640, box.top + 150 - abs(math.sin(self.t * 5)) * 40, 17, self.t * 400)
            draw_text(surf, "Si otra persona usa tu mismo nombre, los distingue una etiqueta (#1234).", 16,
                      (640, box.bottom - 30), C.INK_SOFT, outline=None)
        else:
            draw_text(surf, "No se pudo entrar al online", 24, (640, box.top + 44), C.RED, outline=None)
            for k, ln in enumerate(wrap(self.failed, 16, box.width - 40)[:3]):
                draw_text(surf, ln, 16, (640, box.top + 90 + k * 22), C.INK, outline=None)
            button(surf, self.retry_rect, "REINTENTAR", self.hover, True, 24, self.t)
        info = pygame.Rect(0, 0, 1000, 104)
        info.midtop = (640, 546)
        inner = panel(surf, info)
        draw_text(surf, CONTROLS_HELP, 16, (640, inner.top + 20), C.INK, outline=None)
        draw_text(surf, "Cada persona juega desde su casa; el servidor sortea los lados al empezar.", 16,
                  (640, inner.top + 46), C.INK_SOFT, outline=None)
        if not self.app.web:
            draw_text(surf, f"Servidor: {self.net.url}", 16, (640, inner.top + 72), C.INK_SOFT, outline=None)
        self.draw_common(surf)


# ---------------------------------------------------------------------------
# Lista de salas
# ---------------------------------------------------------------------------
class RoomsScreen(OnlineScreen):
    ROW_H = 58
    VISIBLE = 6
    LIST = pygame.Rect(150, 168, 980, 6 * 58 + 16)

    def __init__(self, app, notice=None):
        super().__init__(app)
        self.sel = 0
        self.offset = 0
        self.hover_row = None
        self.hover_btn = None
        self.prompt = None              # (sala, campo de contraseña) para salas privadas
        self.buttons = {"create": pygame.Rect(370, 572, 260, 56), "refresh": pygame.Rect(650, 572, 260, 56)}
        if notice:
            self.notify(notice, C.GOLD)

    @property
    def rooms(self):
        return self.net.rooms

    def back(self):
        self.app.close_online()
        self.app.switch(OnlineHomeScreen(self.app))

    def row_rect(self, k):
        return pygame.Rect(self.LIST.left + 8, self.LIST.top + 8 + k * self.ROW_H, self.LIST.width - 16,
                           self.ROW_H - 6)

    def visible_rooms(self):
        return list(enumerate(self.rooms))[self.offset:self.offset + self.VISIBLE]

    def join(self, room):
        if room["players"] >= room["max_players"]:
            self.notify("La sala está completa.")
            self.app.audio.play("blocked")
            return
        self.app.audio.play("confirm")
        if room["private"]:
            field = TextField((420, 360, 440, 56), f"CONTRASEÑA DE «{room['name']}»", 24, password=True,
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
        return pygame.Rect(440, 448, 190, 50), pygame.Rect(650, 448, 190, 50)

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
        dim(surf, 140)
        title(surf, "SALAS", (640, 64), 56)
        draw_text(surf, f"Hola, {self.net.display or ''}. Elegí una sala para unirte o creá la tuya.", 16,
                  (640, 116), C.INK, outline=C.WHITE)
        inner = panel(surf, self.LIST.inflate(0, 36).move(0, -18))
        for txt, x in (("SALA", 30), ("CREADA POR", 400), ("JUGADORES", 650), ("ESTADO", 790)):
            draw_text(surf, txt, 16, (self.LIST.left + x, inner.top + 10), C.INK_SOFT, anchor="midleft",
                      outline=None)
        if not self.rooms:
            draw_text(surf, "Todavía no hay salas: ¡creá la primera!", 24, self.LIST.center, C.INK_SOFT,
                      outline=None)
        for k, (i, room) in enumerate(self.visible_rooms()):
            r = self.row_rect(k)
            full = room["players"] >= room["max_players"]
            face = C.GOLD if i == self.sel or i == self.hover_row else (C.CREAM_DARK if full else C.WHITE)
            rin = bevel_box(surf, r, face, shadow=False)
            if room["private"]:
                lock_icon(surf, (rin.left + 16, rin.centery))
            draw_text(surf, room["name"], 24, (rin.left + 38, rin.centery), C.INK, anchor="midleft", outline=None)
            draw_text(surf, room["owner"], 16, (self.LIST.left + 400, rin.centery), C.INK, anchor="midleft",
                      outline=None)
            draw_text(surf, f"{room['players']}/{room['max_players']}", 24, (self.LIST.left + 690, rin.centery),
                      C.INK, outline=None)
            draw_text(surf, ROOM_STATES.get(room["state"], room["state"]), 16, (self.LIST.left + 790, rin.centery),
                      C.RED if full else C.INK_SOFT, anchor="midleft", outline=None)
        if len(self.rooms) > self.VISIBLE:
            draw_text(surf, f"{self.offset + 1}-{min(len(self.rooms), self.offset + self.VISIBLE)} de "
                            f"{len(self.rooms)} (rueda del mouse o W/S)", 16, (640, self.LIST.bottom + 8),
                      C.INK_SOFT, outline=None)
        button(surf, self.buttons["create"], "CREAR SALA", self.hover_btn == "create", True, 24, self.t)
        button(surf, self.buttons["refresh"], "ACTUALIZAR", self.hover_btn == "refresh", True, 24, self.t)
        footer(surf, "Clic o Enter: unirse  -  C: crear sala  -  Esc: volver  -  La lista se actualiza sola")
        if self.prompt:
            room, field = self.prompt
            dim(surf, 120)
            box = pygame.Rect(0, 0, 560, 250)
            box.center = (640, 400)
            panel(surf, box)
            field.draw(surf, self.t)
            ok, cancel = self._prompt_buttons()
            button(surf, ok, "ENTRAR", False, bool(field.value), 24, self.t)
            button(surf, cancel, "CANCELAR", False, True, 24, self.t)
        self.draw_common(surf)


# ---------------------------------------------------------------------------
# Crear sala
# ---------------------------------------------------------------------------
class CreateRoomScreen(OnlineScreen):
    def __init__(self, app):
        super().__init__(app)
        user = self.net.username or ""
        self.name = TextField((390, 236, 500, 56), "NOMBRE DE LA SALA", ROOM_NAME_MAX,
                              value=f"Sala de {user}"[:ROOM_NAME_MAX])
        self.private = CheckBox((390, 326, 360, 40), "Con contraseña")
        self.password = TextField((390, 420, 500, 56), "CONTRASEÑA", 24, password=True)
        self.create_rect = pygame.Rect(0, 0, 300, 56)
        self.create_rect.center = (640, 540)
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
        dim(surf, 140)
        title(surf, "CREAR SALA", (640, 96), 56)
        panel(surf, pygame.Rect(350, 180, 580, 420))
        self.name.draw(surf, self.t)
        self.private.draw(surf)
        if self.private.value:
            self.password.draw(surf, self.t)
        else:
            draw_text(surf, "Sala libre: cualquiera de la lista puede entrar.", 16, (640, 448), C.INK_SOFT,
                      outline=None)
        button(surf, self.create_rect, "CREAR", self.hover, True, 24, self.t)
        footer(surf, "Enter: crear  -  Tab: siguiente campo  -  Esc: volver")
        self.draw_common(surf)


# ---------------------------------------------------------------------------
# Sala: elegir personaje y confirmar
# ---------------------------------------------------------------------------
class RoomScreen(OnlineScreen):
    IN_ROOM = True
    BACK_LABEL = "◄ SALIR"
    CARD_W, CARD_H, GAP = 150, 168, 14
    LEFT_KEYS = (pygame.K_a, pygame.K_LEFT)
    RIGHT_KEYS = (pygame.K_d, pygame.K_RIGHT)
    OK_KEYS = (pygame.K_SPACE, pygame.K_p, pygame.K_RETURN, pygame.K_KP_ENTER)

    def __init__(self, app):
        super().__init__(app)
        me, _ = members(self.net)
        pre = (me and me["character"]) or getattr(app, "last_online_char", None) or CHARACTER_IDS[0]
        self.cursor = CHARACTER_IDS.index(pre)
        self.sent_char = None
        self.sent_at = -10.0
        self.hover = None

    def back(self):
        self.net.leave_room()
        self.app.switch(RoomsScreen(self.app))

    def choosing(self):
        return bool(self.net.room) and self.net.room["state"] == "eligiendo"

    def card_rect(self, k):
        total = len(CHARACTER_IDS) * self.CARD_W + (len(CHARACTER_IDS) - 1) * self.GAP
        x0 = 640 - total / 2
        return pygame.Rect(x0 + k * (self.CARD_W + self.GAP), 508, self.CARD_W, self.CARD_H)

    def buttons(self):
        x, y = 250, 402
        return {"prev": pygame.Rect(x - 150, y, 52, 44), "ok": pygame.Rect(x - 86, y, 172, 44),
                "next": pygame.Rect(x + 98, y, 52, 44)}

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
        if me["character"] != cid and (cid != self.sent_char or self.t - self.sent_at > 1.0):
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
                    if self.card_rect(k).collidepoint(ev.pos):
                        self.cursor = k
                        self.app.audio.play("select")

    def update(self, dt):
        super().update(dt)
        if not self.my_ready():
            self.sync_character()

    def _player(self, surf, x, cid, facing, ready, color, scale=1.9):
        if ready:
            ang, bob = -50 + 50 * math.sin(self.t * 14), -int(abs(math.sin(self.t * 7)) * 6)
        else:
            ang, bob = 0, (-1 if (self.t * 1.6) % 2 < 1 else 0)
        img, (fx, fy) = self.app.sprites.player(cid, facing, ang, bob, color, False, scale)
        surf.blit(img, (x - fx, 380 - fy))

    def _tag(self, surf, x, name, sub, color):
        tag = pygame.Rect(0, 0, 320, 70)
        tag.midtop = (x, 108)
        inner = panel(surf, tag)
        pygame.draw.rect(surf, color, (inner.left, inner.top, inner.width, 6))
        draw_text(surf, name, 24, (x, inner.top + 22), C.INK, outline=None)
        draw_text(surf, sub, 16, (x, inner.top + 44), C.INK_SOFT, outline=None)

    def draw(self, surf):
        room = self.net.room
        surf.blit(self.app.background, (0, 0))
        dim(surf, 120)
        if not room:
            self.draw_common(surf)
            return
        me, rival = members(self.net)
        title(surf, room["name"].upper(), (640, 40), 40)
        kind = "con contraseña" if room["private"] else "libre"
        draw_text(surf, f"Sala {kind} de {room['owner']}  -  Los lados se sortean al empezar el partido", 16,
                  (640, 80), C.INK, outline=C.WHITE)
        # yo
        cid = CHARACTER_IDS[self.cursor]
        ready = bool(me and me["ready"])
        ped = pygame.Rect(0, 0, 200, 18)
        ped.midtop = (250, 376)
        bevel_box(surf, ped, C.STRUCT, shadow=True)
        self._player(surf, 250, cid, 1, ready, ME_COLOR)
        self._tag(surf, 250, self.net.display or "", short_name(CHARACTERS_BY_ID[cid]), ME_COLOR)
        b = self.buttons()
        can = self.choosing()
        button(surf, b["prev"], "◄", self.hover == "prev", not ready, 24, self.t)
        button(surf, b["ok"], "CANCELAR" if ready else "¡LISTO!", self.hover == "ok", can, 24, self.t)
        button(surf, b["next"], "►", self.hover == "next", not ready, 24, self.t)
        if ready:
            draw_text(surf, "¡LISTO!", 32, (420, 300), C.GREEN, kind="title", outline=C.INK, shadow=True)
        # rival
        if rival is None:
            dots = "." * (1 + int(self.t * 2) % 3)
            self._tag(surf, 1030, "ESPERANDO RIVAL" + dots, "La sala aparece en la lista de salas", RIVAL_COLOR)
            draw_text(surf, "?", 120, (1030, 300), C.WHITE, kind="title", outline=C.INK, shadow=True)
        else:
            rc = rival["character"]
            sub = short_name(CHARACTERS_BY_ID[rc]) if rc else "eligiendo personaje..."
            if not rival.get("connected", True):
                sub = "desconectado: esperando que vuelva"
            ped = pygame.Rect(0, 0, 200, 18)
            ped.midtop = (1030, 376)
            bevel_box(surf, ped, C.STRUCT, shadow=True)
            if rc:
                self._player(surf, 1030, rc, -1, rival["ready"], RIVAL_COLOR)
            else:
                draw_text(surf, "?", 120, (1030, 300), C.WHITE, kind="title", outline=C.INK, shadow=True)
            self._tag(surf, 1030, rival["display"], sub, RIVAL_COLOR)
            if rival["ready"]:
                draw_text(surf, "¡LISTO!", 32, (860, 300), C.GREEN, kind="title", outline=C.INK, shadow=True)
        draw_text(surf, "VS", 72, (640, 280), C.WHITE, kind="title", outline=C.INK, shadow=True)
        hint = ("A/D o flechas: elegir  -  Espacio, P o Enter: listo" if can
                else "Cuando entre un rival van a poder confirmar")
        draw_text(surf, hint, 16, (250, 466), C.INK, outline=C.WHITE)
        # tarjetas
        sp = self.app.sprites
        for k, c in enumerate(CHARACTER_IDS):
            r = self.card_rect(k)
            mine = k == self.cursor
            theirs = rival is not None and rival["character"] == c
            rr = r.move(0, -8 if (mine or theirs) else 0)
            pygame.draw.rect(surf, C.INK, rr.move(6, 6))
            surf.blit(sp.portrait(c), rr)
            pygame.draw.rect(surf, C.INK, rr, 4)
            draw_text(surf, short_name(CHARACTERS_BY_ID[c]).upper(), 16, (rr.centerx, rr.bottom - 14), C.WHITE,
                      outline=C.INK)
            if mine:
                pygame.draw.rect(surf, ME_COLOR, rr.inflate(12, 12), 6)
            if theirs:
                pygame.draw.rect(surf, RIVAL_COLOR, rr.inflate(4 if mine else 12, 4 if mine else 12), 6)
        if room["state"] == "eligiendo" and me and rival and me["ready"] and rival["ready"]:
            draw_text(surf, "¡A LA CANCHA!", 40, (640, 360), C.GOLD, kind="title", outline=C.INK, shadow=True)
        footer(surf, "Esc: salir de la sala  -  Mouse: botones y tarjetas")
        self.draw_common(surf)


# ---------------------------------------------------------------------------
# Partido online
# ---------------------------------------------------------------------------
class OnlineMatchScreen(MatchScreen):
    """La simulación corre en el servidor: acá sólo se mandan controles y
    pedidos, y se dibuja (suavizado) lo que llega."""

    INPUT_KEEPALIVE = 0.25     # s: aunque no cambie nada, se repite la foto de controles

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
        self.side_banner = 5.0
        self.pause_button = BackButton(self.request_pause, "II PAUSA", rect=(16, 12, 150, 44))
        self.quit_button = BackButton(self.ask_abandon, "ABANDONAR", rect=(16, 64, 150, 44))
        self.pause_menu = Menu([("Estoy listo", self.ready_pause), ("Abandonar", self.ask_abandon)],
                               (640, 500), width=340, height=50, gap=12, size=24)

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
                self.end_timer = 1.8 if msg["reason"] == W.END_TIME else 1.0
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
                            (640, 440), width=380, height=50, gap=12, size=24)

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
                if p["frozen"] and int(self.t * 20) % 3 == 0:
                    self.app.fx.snow(p["x"] + (self.t * 97 % 60) - 30, p["y"] - 120 * p["scale"])
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
            dim(surf, 120)
            title(surf, "Preparando partido...", (640, 330), 32, C.WHITE)
            draw_text(surf, "Esperando al servidor", 16, (640, 380), C.INK, outline=C.WHITE)
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
            draw_text(surf, f"JUGÁS A LA {side}", 40, (640, 440), PLAYER_COLORS[self.you], kind="title",
                      outline=C.INK, shadow=True)
        if self.end_info is not None:
            head = "¡FINAL DEL PARTIDO!" if self.end_info["reason"] == W.END_TIME else "¡PARTIDO TERMINADO!"
            title(surf, head, (640, 330), 56, C.WHITE)
        self.quit_button.visible = self.end_info is None
        self.pause_button.visible = (overlay is None and self.end_info is None
                                     and self.net.pause.get("status") == W.PAUSE_NONE)
        self.pause_button.draw(surf, self.t)
        self.quit_button.draw(surf, self.t)
        if overlay is not None:
            self._draw_overlay(surf, overlay)
        if self.confirm is not None:
            dim(surf, 120)
            box = pygame.Rect(0, 0, 560, 260)
            box.center = (640, 400)
            inner = panel(surf, box)
            title(surf, "¿ABANDONAR?", (640, inner.top + 34), 40, C.RED)
            draw_text(surf, "Si abandonás, perdés el partido y salís de la sala.", 16, (640, inner.top + 80),
                      C.INK, outline=None)
            self.confirm.draw(surf)
        status_chip(surf, self.net, self.t, bottom=True)

    def _draw_overlay(self, surf, overlay):
        dim(surf, 120)
        r = pygame.Rect(0, 0, 600, 360 if overlay == "pause" else 230)
        r.center = (640, 400)
        inner = panel(surf, r)
        if overlay == "self":
            left = self.net.reconnect_left() or 0
            title(surf, "SE CORTÓ TU CONEXIÓN", (640, inner.top + 40), 32, C.RED)
            lines = [f"Reconectando... ({left:.0f} s)", "El partido está en pausa para los dos.",
                     "Si no volvés a tiempo, perdés por abandono."]
        elif overlay == "opponent":
            opp = self.net.opponent
            left = self.net.countdown(opp) or 0
            title(surf, "SIN CONEXIÓN", (640, inner.top + 40), 40, C.RED)
            lines = [f"{opp['name']} perdió la conexión.", f"Esperando que vuelva: {left:.0f} s",
                     "Si no vuelve, ganás por abandono."]
        else:
            p = self.net.pause
            left = self.net.countdown(p) or 0
            title(surf, "PAUSA", (640, inner.top + 40), 48)
            lines = [f"Pedida por {p.get('by_name')}.",
                     f"Se sigue jugando en {left:.0f} s o cuando los dos estén listos."]
            for i in (0, 1):
                ok = p.get("ready", [False, False])[i]
                draw_text(surf, f"{self.names[i]}: {'LISTO' if ok else 'esperando...'}", 24,
                          (640, inner.top + 156 + i * 30), C.GREEN if ok else C.INK_SOFT, outline=None)
            self.pause_menu.draw(surf)
        for k, ln in enumerate(lines):
            big = overlay != "pause" and k == 0
            draw_text(surf, ln, 24 if big else 16, (640, inner.top + 92 + k * 30), C.INK, outline=None)

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
        self.menu = Menu(items, (640, 590), width=380, height=48, gap=10, size=24)
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
            self.confetti_t = 1.4
            x = 290 if self.winner == 0 else 990
            self.app.fx.confetti(x, 230, [PLAYER_COLORS[self.winner], C.WHITE, C.GOLD])

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, 100)
        sp = self.app.sprites
        for i in (0, 1):
            x, f = (290, 1) if i == 0 else (990, -1)
            win = self.winner == i
            if win:
                ang, bob = -50 + 50 * math.sin(self.t * 14), -int(abs(math.sin(self.t * 7)) * 6)
            else:
                ang, bob = 0, (-1 if (self.t * 1.6 + i * 0.5) % 2 < 1 else 0)
            img, (fx, fy) = sp.player(self.chars[i], f, ang, bob, PLAYER_COLORS[i], False, 2.0 if win else 1.6)
            surf.blit(img, (x - fx, 450 - fy))
            draw_text(surf, self.char_name(i), 24, (x, 478), PLAYER_COLORS[i], outline=C.INK)
            draw_text(surf, self.names[i], 16, (x, 504), C.INK, outline=C.WHITE)
        self.app.fx.draw(surf)
        if self.winner is None:
            head, col = "¡EMPATE!", C.WHITE
        else:
            head, col = f"¡GANÓ {self.char_name(self.winner).upper()}!", PLAYER_COLORS[self.winner]
        title(surf, head, (640, 64), 56, col)
        if self.over["reason"] == W.END_FORFEIT:
            sub = f"{self.over.get('by_name')} abandonó el partido"
        elif self.over["reason"] == W.END_ERROR:
            sub = "El partido se cortó por un problema del servidor"
        elif self.winner is None:
            sub = "Nadie ganó esta vez"
        else:
            sub = "¡Ganaste!" if self.winner == self.you else "Perdiste"
        draw_text(surf, sub, 24, (640, 124), C.INK, outline=C.WHITE)
        box = pygame.Rect(0, 0, 300, 110)
        box.center = (640, 270)
        pygame.draw.rect(surf, C.INK, box.move(6, 6))
        pygame.draw.rect(surf, C.STRUCT_DARK, box)
        pygame.draw.rect(surf, C.INK, box, 4)
        led = box.inflate(-16, -16)
        pygame.draw.rect(surf, C.LED_BG, led)
        score = pixelfont.render_led(f"{self.score[0]}-{self.score[1]}", 9, C.LED_ON, C.LED_OFF)
        surf.blit(score, score.get_rect(center=led.center))
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
        lines = wrap(status, 16, 400)
        note = pygame.Rect(0, 0, 440, 22 * len(lines) + 16)
        note.midtop = (640, 342)
        inner = bevel_box(surf, note, C.CREAM, shadow=False)
        for k, ln in enumerate(lines):
            draw_text(surf, ln, 16, (640, inner.top + 11 + k * 22), C.INK, outline=None)
        if self.menu:
            self.menu.draw(surf)
        self.draw_common(surf)


# ---------------------------------------------------------------------------
# Conexión perdida
# ---------------------------------------------------------------------------
class OnlineErrorScreen(Screen):
    def __init__(self, app, message):
        super().__init__(app)
        self.message = message
        self.menu = Menu([("Reintentar", self.retry), ("Volver", self.back)], (640, 520), width=300)
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
        dim(surf, 170)
        r = pygame.Rect(0, 0, 900, 240)
        r.midtop = (640, 150)
        inner = panel(surf, r, face=(255, 236, 232), border=C.RED)
        title(surf, "SIN CONEXIÓN", (640, inner.top + 40), 48, C.RED)
        y = inner.top + 104
        for ln in wrap(self.message, 24, inner.width - 40):
            draw_text(surf, ln, 24, (640, y), C.INK, outline=None)
            y += 32
        draw_text(surf, "Revisá tu internet o que el servidor esté encendido.", 16, (640, inner.bottom - 22),
                  C.INK_SOFT, outline=None)
        self.menu.draw(surf)
        self.back_button.draw(surf, self.t)
