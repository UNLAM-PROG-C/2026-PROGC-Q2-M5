"""Online mode screens (desktop and browser version).

Flow: user name -> room list -> (create room) -> room: choose a character
and "ready" -> match -> result -> rematch / change character / leave.

All of them read app.net (NetClient), which is updated with every server
message: nothing is lost when the screen changes. The simulation runs on
the server; these screens only send controls and requests (pause, ready,
abandon) and draw what arrives.

Measures are px in the 1280 x 720 logical resolution (see layout.py).
"""
import math
import time

import pygame

from fdc import config
from fdc import protocol
from fdc.online import client
from fdc.online import interp
from fdc.online import lobby
from fdc.online import prediction
from fdc.online import wire
from fdc.ui import assets
from fdc.ui import characters
from fdc.ui import layout
from fdc.ui import match_screens
from fdc.ui import palette
from fdc.ui import retro
from fdc.ui import screens
from fdc.ui import sprites
from fdc.ui import widgets

CHARACTER_IDS = characters.CHARACTER_IDS
SELECT = match_screens.SelectScreen
PLAYER_X = match_screens.PLAYER_X
FACING = match_screens.FACING
ONLINE = config.Online
CONTROLS_HELP = ("Moverse: A/D o flechas  -  Saltar: W o flecha arriba  -  "
                 "Patear: Espacio o P  -  Pausa: Esc")
ROOM_STATES = {lobby.WAITING: "esperando rival",
               lobby.CHOOSING: "eligiendo personajes",
               lobby.PLAYING: "jugando"}
# In the room there are no sides yet: my colour and the rival colour.
ME_COLOR, RIVAL_COLOR = palette.GOLD, palette.BLUE
PASSWORD_MAX_LEN = 24              # characters of a room password
NOTICE_TIME = 4.0                  # s a notice is shown at the bottom
ENTER_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
UP_KEYS = (pygame.K_w, pygame.K_UP)
DOWN_KEYS = (pygame.K_s, pygame.K_DOWN)

# --- lock of the rooms with password: (x, y from the centre, w, h) in px
LOCK_BODY = (-9, -1, 18, 13)       # body
LOCK_SHACKLE = (-6, -11, 12, 12)   # arc on top
LOCK_SHACKLE_LINE = 3              # px: thickness of the arc
LOCK_KEYHOLE = (-2, 3, 4, 5)       # golden keyhole
# --- connection status (top right; at the bottom during the match)
CHIP_H = 32                        # px: height
CHIP_PADDING = 40                  # px added to the text (dot and margins)
# px from the bottom right corner during the match (x, y).
CHIP_BOTTOM_MARGIN = (12, 8)
CHIP_BLINK_HZ = 3                  # blink of the red dot while reconnecting
CHIP_DOT_X = 12                    # colour dot, from the left edge (px)
CHIP_DOT_R = 6                     # px: radius of the dot
CHIP_TEXT_X = 24                   # text, from the left edge (px)
# --- notice at the bottom centre
MESSAGE_BLINK_TIME = 0.3           # last s in which the notice blinks
MESSAGE_BLINK_HZ = 20              # changes per second of that blink
MESSAGE_MAX_W = 800                # px: maximum text width (then it wraps)
MESSAGE_PADDING = 40               # px added to the longest line
MESSAGE_PAD_Y = 18                 # px added to the lines
MESSAGE_BOTTOM = 676               # bottom edge (just above the footer)
MESSAGE_BAR_W = 6                  # colour band on the left (px)
MESSAGE_TEXT_Y = 13                # first line, from the notice top (px)


def _at(center, rect):
    """Rectangle (dx, dy, width, height) relative to the centre."""
    dx, dy, w, h = rect
    return center[0] + dx, center[1] + dy, w, h


def lock_icon(surf, center, color=palette.INK):
    """Pixel art lock (rooms with a password)."""
    pygame.draw.rect(surf, color, _at(center, LOCK_BODY))
    pygame.draw.rect(surf, color, _at(center, LOCK_SHACKLE), LOCK_SHACKLE_LINE)
    pygame.draw.rect(surf, palette.GOLD, _at(center, LOCK_KEYHOLE))


def _chip_text(net):
    """(text, dot colour) of the connection status, or None."""
    if net.status == client.RECONNECTING:
        return (f"RECONECTANDO... {net.reconnect_left() or 0:.0f} s",
                palette.RED)
    if net.connected:
        rtt = (f"  {net.rtt * config.MS_PER_SECOND:.0f} ms"
               if net.rtt is not None else "")
        return f"{net.display}{rtt}", palette.GREEN
    if net.status == client.CONNECTING:
        return "CONECTANDO...", palette.GOLD_DARK
    return None


def _chip_rect(txt, bottom):
    r = pygame.Rect(0, 0, assets.text_width(txt, layout.FONT_SMALL)
                    + CHIP_PADDING, CHIP_H)
    if bottom:
        margin_x, margin_y = CHIP_BOTTOM_MARGIN
        r.bottomright = (layout.SCREEN_W - margin_x, layout.SCREEN_H - margin_y)
    else:
        r.topright = (layout.SCREEN_W - layout.SCREEN_MARGIN,
                      layout.SCREEN_MARGIN)
    return r


def status_chip(surf, net, t, bottom=False):
    """Connection status (top right, or at the bottom during the match)."""
    chip = _chip_text(net)
    if chip is None:
        return
    txt, col = chip
    r = _chip_rect(txt, bottom)
    inner = retro.bevel_box(surf, r, palette.CREAM, shadow=False)
    if net.status != client.RECONNECTING or int(t * CHIP_BLINK_HZ) % 2 == 0:
        pygame.draw.circle(surf, col, (inner.left + CHIP_DOT_X, inner.centery),
                           CHIP_DOT_R)
    assets.draw_text(surf, txt, layout.FONT_SMALL,
                     (inner.left + CHIP_TEXT_X, inner.centery), palette.INK,
                     anchor="midleft", outline=None)


def message_box(surf, msg):
    """Short notice at the bottom centre (server errors, confirmations)."""
    txt, col, left = msg
    if left < MESSAGE_BLINK_TIME and int(left * MESSAGE_BLINK_HZ) % 2:
        return
    lines = assets.wrap(txt, layout.FONT_SMALL, MESSAGE_MAX_W)
    width = max(assets.text_width(ln, layout.FONT_SMALL) for ln in lines)
    r = pygame.Rect(0, 0, width + MESSAGE_PADDING,
                    layout.TEXT_LINE_H * len(lines) + MESSAGE_PAD_Y)
    r.midbottom = (layout.CENTER_X, MESSAGE_BOTTOM)
    inner = retro.bevel_box(surf, r, palette.CREAM)
    pygame.draw.rect(surf, col, (inner.left, inner.top, MESSAGE_BAR_W,
                                 inner.height))
    _message_lines(surf, lines, inner)


def _message_lines(surf, lines, inner):
    for k, ln in enumerate(lines):
        y = inner.top + MESSAGE_TEXT_Y + k * layout.TEXT_LINE_H
        assets.draw_text(surf, ln, layout.FONT_SMALL,
                         (inner.centerx + MESSAGE_BAR_W // 2, y), palette.INK,
                         outline=None)


def members(net):
    """(me, rival) in the current room (either may be None)."""
    room = net.room
    if not room:
        return None, None
    me = next((m for m in room["members"] if net.is_me(m)), None)
    rival = next((m for m in room["members"] if not net.is_me(m)), None)
    return me, rival


def _left_click_on(ev, rect):
    return (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1
            and rect.collidepoint(ev.pos))


def _to_multiplayer(app):
    """Leaves the online mode and goes back to the multiplayer menu."""
    app.close_online()
    app.switch(screens.MultiplayerMenuScreen(app))


def _centered_lines(surf, lines, size, top, line_h, color=palette.INK):
    for k, ln in enumerate(lines):
        assets.draw_text(surf, ln, size, (layout.CENTER_X, top + k * line_h),
                         color, outline=None)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class OnlineScreen(screens.Screen):
    """Base of the online screens: back button, notices and status."""
    IN_ROOM = False        # True: if I am no longer in a room, back to list
    NEEDS_CONNECTION = True   # True: if the connection is lost, error screen
    BACK_LABEL = "◄ VOLVER"

    def __init__(self, app):
        super().__init__(app)
        self.net = app.online()
        self.back_button = screens.BackButton(self.back, self.BACK_LABEL)
        self.message = None

    def back(self):
        """Where the back button goes (each screen decides)."""

    def notify(self, txt, color=palette.RED, secs=NOTICE_TIME):
        self.message = (txt, color, secs)

    def handle_back(self, ev):
        """Back button or Esc. True if it was used."""
        if self.back_button.handle_event(ev):
            self.app.audio.play("back")
            return True
        if (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE
                and self.back_button.visible):
            self.app.audio.play("back")
            self.back()
            return True
        return False

    def on_net(self, msg):
        t = msg["type"]
        if t == wire.ERROR:
            self.notify(msg["message"])
        elif t == wire.MATCH_START:
            self.app.switch(OnlineMatchScreen(self.app, msg))
        elif t == wire.ROOMS and self.IN_ROOM:
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
# Online entry: connects with the profile name (chosen at the start)
# ---------------------------------------------------------------------------
class OnlineHomeScreen(OnlineScreen):
    """Connecting... (or why it failed, with a retry button)."""
    NEEDS_CONNECTION = False
    TITLE_Y = 96                       # title (px)
    BOX = (330, 220, 620, 280)         # central box (x, y, width, height)
    CONNECTING_Y = 50                  # connecting line, from the box top
    BALL_GROUND = 150                  # bouncing ball: floor, from box top
    BALL_HOP = 40                      # px it rises
    BALL_HOP_HZ = 5                    # bounces per second (one way)
    BALL_SPIN = 400                    # degrees per second it turns
    TAG_NOTE_BOTTOM = 30               # note about tags, from the box bottom
    FAILED_Y = 44                      # failure line, from the box top (px)
    FAILED_DETAIL_Y = 90               # the reason, from the box top (px)
    FAILED_LINES = 3                   # lines of the reason that fit
    FAILED_MARGIN = 40                 # px of air beside the reason
    RETRY_SIZE = (280, layout.BUTTON_H)   # retry button (width, height)
    RETRY_CENTER = (layout.CENTER_X, 440)  # centre of that button (px)
    INFO = (1000, 104)                 # help box at the bottom (w, h) in px
    INFO_TOP = 546                     # top edge of that box (px)
    INFO_LINE_Y = (20, 46, 72)         # its three lines, from the box top

    def __init__(self, app):
        super().__init__(app)
        self.retry_rect = pygame.Rect((0, 0), self.RETRY_SIZE)
        self.retry_rect.center = self.RETRY_CENTER
        self.hover = False
        self.failed = None
        saved = client.saved_session()
        if saved and self.net.status == client.IDLE:
            # The page was reloaded: back to its room and match.
            self.net.token = saved[1]
        self.connect()

    def connect(self):
        profile = self.app.profile
        self.failed = None
        self.net.connect(profile.name, profile.player_id)

    def back(self):
        _to_multiplayer(self.app)

    def handle_event(self, ev):
        if self.handle_back(ev) or self.failed is None:
            return
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.retry_rect.collidepoint(ev.pos)
        elif (_left_click_on(ev, self.retry_rect)
              or (ev.type == pygame.KEYDOWN and ev.key in ENTER_KEYS)):
            self.app.audio.play("confirm")
            self.connect()

    def on_net(self, msg):
        if msg["type"] == wire.WELCOME:
            self.app.switch(RoomsScreen(self.app))
        elif msg["type"] == wire.ERROR:
            self.failed = msg["message"]

    def update(self, dt):
        super().update(dt)
        if self.failed is None and self.net.fatal:
            self.failed = self.net.fatal

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        screens.dim(surf, layout.VEIL_ONLINE)
        screens.title(surf, "JUGAR ONLINE", (layout.CENTER_X, self.TITLE_Y),
                      layout.FONT_TITLE_XL)
        box = screens.panel(surf, pygame.Rect(self.BOX))
        if self.failed is None:
            self._connecting(surf, box)
        else:
            self._failed(surf, box)
        self._info(surf)
        self.draw_common(surf)

    def _connecting(self, surf, box):
        assets.draw_text(surf, f"Conectando como {self.app.profile.name}...",
                         layout.FONT_TEXT,
                         (layout.CENTER_X, box.top + self.CONNECTING_Y),
                         palette.INK, outline=None)
        screens.bouncing_ball(self.app, surf, self.t, layout.CENTER_X,
                              box.top + self.BALL_GROUND, self.BALL_HOP,
                              self.BALL_HOP_HZ, self.BALL_SPIN)
        assets.draw_text(surf, "Si otra persona usa tu mismo nombre, los "
                         "distingue una etiqueta (#1234).", layout.FONT_SMALL,
                         (layout.CENTER_X, box.bottom - self.TAG_NOTE_BOTTOM),
                         palette.INK_SOFT, outline=None)

    def _failed(self, surf, box):
        assets.draw_text(surf, "No se pudo entrar al online", layout.FONT_TEXT,
                         (layout.CENTER_X, box.top + self.FAILED_Y),
                         palette.RED, outline=None)
        lines = assets.wrap(self.failed, layout.FONT_SMALL,
                            box.width - self.FAILED_MARGIN)[:self.FAILED_LINES]
        _centered_lines(surf, lines, layout.FONT_SMALL,
                        box.top + self.FAILED_DETAIL_Y, layout.TEXT_LINE_H)
        screens.button(surf, self.retry_rect, "REINTENTAR", self.hover, True,
                       layout.FONT_TEXT, self.t)

    def _info(self, surf):
        info = pygame.Rect((0, 0), self.INFO)
        info.midtop = (layout.CENTER_X, self.INFO_TOP)
        inner = screens.panel(surf, info)
        lines = [(CONTROLS_HELP, palette.INK),
                 ("Cada persona juega desde su casa; el servidor sortea los "
                  "lados al empezar.", palette.INK_SOFT)]
        if not self.app.web:
            lines.append((f"Servidor: {self.net.url}", palette.INK_SOFT))
        for (text, color), y in zip(lines, self.INFO_LINE_Y):
            assets.draw_text(surf, text, layout.FONT_SMALL,
                             (layout.CENTER_X, inner.top + y), color,
                             outline=None)


# ---------------------------------------------------------------------------
# Room list
# ---------------------------------------------------------------------------
class RoomsScreen(OnlineScreen):
    """List of rooms to join, plus create and refresh buttons."""
    ROW_H = 58                         # px per room in the list
    ROW_GAP = 6                        # free px between rooms
    VISIBLE = 6                        # rooms visible at once (wheel or W/S)
    LIST_PADDING = 8                   # px of air inside the list box
    # Box of the list (x, y, width, height) in px.
    LIST = pygame.Rect(150, 168, 980, VISIBLE * ROW_H + 2 * LIST_PADDING)
    HEADER_ROOM = 36                   # px the box grows up for the headers
    HEADER_Y = 10                      # column headers, from the box top
    # Columns: (header, x from the left edge of the list in px).
    COLUMNS = (("SALA", 30), ("CREADA POR", 400), ("JUGADORES", 650),
               ("ESTADO", 790))
    LOCK_X = 16                        # lock, from the left edge of the row
    NAME_X = 38                        # room name, from the row left edge
    OWNER_X = 400                      # who created it (owner column)
    PLAYERS_X = 690                    # "1/2", below the players column
    STATE_X = 790                      # state (state column)
    PAGER_GAP = 8                      # page line, below the list (px)
    TITLE_Y = 64                       # title (px)
    GREETING_Y = 116                   # greeting line (px)
    BUTTONS_Y = 572                    # create and refresh buttons (px)
    BUTTON_W = 260                     # width of those buttons (px)
    BUTTON_GAP = 20                    # px between those buttons
    PROMPT_BOX = (560, 250)            # password box (width, height) in px
    PROMPT_CENTER = (layout.CENTER_X, 400)   # centre of that box (px)
    # Password field (x, y, width, height) in px.
    PROMPT_FIELD = (420, 360, 440, layout.BUTTON_H)
    PROMPT_BUTTONS_Y = 448             # enter and cancel buttons (px)
    PROMPT_BUTTON = (190, 50)          # each of those buttons (w, h) in px

    def __init__(self, app, notice=None):
        super().__init__(app)
        self.sel = 0
        self.offset = 0
        self.hover_row = None
        self.hover_btn = None
        self.prompt = None       # (room, password field) for private rooms
        self.buttons = self._button_rects()
        if notice:
            self.notify(notice, palette.GOLD)

    def _button_rects(self):
        w, gap = self.BUTTON_W, self.BUTTON_GAP
        h = layout.BUTTON_H
        return {"create": pygame.Rect(layout.CENTER_X - w - gap // 2,
                                      self.BUTTONS_Y, w, h),
                "refresh": pygame.Rect(layout.CENTER_X + gap // 2,
                                       self.BUTTONS_Y, w, h)}

    @property
    def rooms(self):
        return self.net.rooms

    def back(self):
        """Leaves the online mode: closes the connection, back to the
        multiplayer menu (local or online)."""
        _to_multiplayer(self.app)

    def row_rect(self, k):
        pad = self.LIST_PADDING
        return pygame.Rect(self.LIST.left + pad,
                           self.LIST.top + pad + k * self.ROW_H,
                           self.LIST.width - 2 * pad, self.ROW_H - self.ROW_GAP)

    def visible_rooms(self):
        return list(enumerate(self.rooms))[self.offset:
                                           self.offset + self.VISIBLE]

    def join(self, room):
        if room["players"] >= room["max_players"]:
            self.notify("La sala está completa.")
            self.app.audio.play("blocked")
            return
        self.app.audio.play("confirm")
        if room["private"]:
            field = widgets.TextField(
                self.PROMPT_FIELD, f"CONTRASEÑA DE «{room['name']}»",
                PASSWORD_MAX_LEN, password=True, sticky=True)
            field.focus(True)
            self.prompt = (room, field)
            return
        self.net.send({"type": wire.JOIN_ROOM, "room": room["room"]})

    def scroll_to_sel(self):
        n = len(self.rooms)
        self.sel = max(0, min(self.sel, n - 1))
        if self.sel < self.offset:
            self.offset = self.sel
        elif self.sel >= self.offset + self.VISIBLE:
            self.offset = self.sel - self.VISIBLE + 1

    def _send_password(self, room, field):
        self.net.send({"type": wire.JOIN_ROOM, "room": room["room"],
                       "password": field.value})
        self.prompt = None

    def _prompt_event(self, ev):
        room, field = self.prompt
        r = field.handle_event(ev)
        if r == "submit" and field.value:
            self._send_password(room, field)
        elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.prompt = None
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and not r:
            ok, cancel = self._prompt_buttons()
            if ok.collidepoint(ev.pos) and field.value:
                self._send_password(room, field)
            elif cancel.collidepoint(ev.pos):
                self.prompt = None

    def _prompt_buttons(self):
        w, h = self.PROMPT_BUTTON
        gap = self.BUTTON_GAP
        y = self.PROMPT_BUTTONS_Y
        return (pygame.Rect(layout.CENTER_X - w - gap // 2, y, w, h),
                pygame.Rect(layout.CENTER_X + gap // 2, y, w, h))

    def handle_event(self, ev):
        if self.prompt:
            self._prompt_event(ev)
        elif self.handle_back(ev):
            return
        elif ev.type == pygame.KEYDOWN:
            self._key(ev.key)
        elif ev.type == pygame.MOUSEWHEEL:
            self.offset = max(0, min(self.offset - ev.y,
                                     max(0, len(self.rooms) - self.VISIBLE)))
        elif ev.type == pygame.MOUSEMOTION:
            self._hover(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._click(ev.pos)

    def _key(self, key):
        if key in UP_KEYS or key in DOWN_KEYS:
            self.sel += -1 if key in UP_KEYS else 1
            self.scroll_to_sel()
        elif key in ENTER_KEYS and self.rooms:
            self.join(self.rooms[self.sel])
        elif key == pygame.K_c:
            self.app.switch(CreateRoomScreen(self.app))

    def _hover(self, pos):
        rows = enumerate(self.visible_rooms())
        self.hover_row = next((i for k, (i, _) in rows
                               if self.row_rect(k).collidepoint(pos)), None)
        self.hover_btn = next((n for n, r in self.buttons.items()
                               if r.collidepoint(pos)), None)

    def _click(self, pos):
        if self.buttons["create"].collidepoint(pos):
            self.app.audio.play("confirm")
            self.app.switch(CreateRoomScreen(self.app))
        elif self.buttons["refresh"].collidepoint(pos):
            self.app.audio.play("select")
            self.net.send({"type": wire.LIST_ROOMS})
        else:
            for k, (i, room) in enumerate(self.visible_rooms()):
                if self.row_rect(k).collidepoint(pos):
                    self.sel = i
                    self.join(room)
                    return

    def on_net(self, msg):
        if msg["type"] == wire.ROOM:
            self.app.switch(RoomScreen(self.app))
            return
        super().on_net(msg)
        if msg["type"] == wire.ROOMS:
            self.scroll_to_sel()

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        screens.dim(surf, layout.VEIL_LIST)
        screens.title(surf, "SALAS", (layout.CENTER_X, self.TITLE_Y),
                      layout.FONT_TITLE_L)
        assets.draw_text(surf, f"Hola, {self.net.display or ''}. Elegí una "
                         "sala para unirte o creá la tuya.", layout.FONT_SMALL,
                         (layout.CENTER_X, self.GREETING_Y), palette.INK,
                         outline=palette.WHITE)
        self._list(surf)
        self._buttons(surf)
        if self.prompt:
            self._draw_prompt(surf)
        self.draw_common(surf)

    def _list(self, surf):
        inner = screens.panel(surf, self.LIST.inflate(0, self.HEADER_ROOM)
                              .move(0, -self.HEADER_ROOM // 2))
        self._headers(surf, inner)
        if not self.rooms:
            assets.draw_text(surf, "Todavía no hay salas: ¡creá la primera!",
                             layout.FONT_TEXT, self.LIST.center,
                             palette.INK_SOFT, outline=None)
        for k, (i, room) in enumerate(self.visible_rooms()):
            self._row(surf, self.row_rect(k), i, room)
        if len(self.rooms) > self.VISIBLE:
            self._pager(surf)

    def _headers(self, surf, inner):
        for txt, x in self.COLUMNS:
            assets.draw_text(surf, txt, layout.FONT_SMALL,
                             (self.LIST.left + x, inner.top + self.HEADER_Y),
                             palette.INK_SOFT, anchor="midleft", outline=None)

    def _row(self, surf, r, i, room):
        full = room["players"] >= room["max_players"]
        if i in (self.sel, self.hover_row):
            face = palette.GOLD
        else:
            face = palette.CREAM_DARK if full else palette.WHITE
        rin = retro.bevel_box(surf, r, face, shadow=False)
        if room["private"]:
            lock_icon(surf, (rin.left + self.LOCK_X, rin.centery))
        assets.draw_text(surf, room["name"], layout.FONT_TEXT,
                         (rin.left + self.NAME_X, rin.centery), palette.INK,
                         anchor="midleft", outline=None)
        self._row_columns(surf, rin.centery, room, full)

    def _row_columns(self, surf, y, room, full):
        left = self.LIST.left
        assets.draw_text(surf, room["owner"], layout.FONT_SMALL,
                         (left + self.OWNER_X, y), palette.INK,
                         anchor="midleft", outline=None)
        assets.draw_text(surf, f"{room['players']}/{room['max_players']}",
                         layout.FONT_TEXT, (left + self.PLAYERS_X, y),
                         palette.INK, outline=None)
        assets.draw_text(surf, ROOM_STATES.get(room["state"], room["state"]),
                         layout.FONT_SMALL, (left + self.STATE_X, y),
                         palette.RED if full else palette.INK_SOFT,
                         anchor="midleft", outline=None)

    def _pager(self, surf):
        last = min(len(self.rooms), self.offset + self.VISIBLE)
        assets.draw_text(surf, f"{self.offset + 1}-{last} de "
                         f"{len(self.rooms)} (rueda del mouse o W/S)",
                         layout.FONT_SMALL,
                         (layout.CENTER_X, self.LIST.bottom + self.PAGER_GAP),
                         palette.INK_SOFT, outline=None)

    def _buttons(self, surf):
        screens.button(surf, self.buttons["create"], "CREAR SALA",
                       self.hover_btn == "create", True, layout.FONT_TEXT,
                       self.t)
        screens.button(surf, self.buttons["refresh"], "ACTUALIZAR",
                       self.hover_btn == "refresh", True, layout.FONT_TEXT,
                       self.t)
        screens.footer(surf, "Clic o Enter: unirse  -  C: crear sala  -  "
                       "Esc: volver  -  La lista se actualiza sola")

    def _draw_prompt(self, surf):
        """Box that asks the password of a private room."""
        field = self.prompt[1]
        screens.dim(surf, layout.VEIL_OVERLAY)
        box = pygame.Rect((0, 0), self.PROMPT_BOX)
        box.center = self.PROMPT_CENTER
        screens.panel(surf, box)
        field.draw(surf, self.t)
        ok, cancel = self._prompt_buttons()
        screens.button(surf, ok, "ENTRAR", False, bool(field.value),
                       layout.FONT_TEXT, self.t)
        screens.button(surf, cancel, "CANCELAR", False, True, layout.FONT_TEXT,
                       self.t)


# ---------------------------------------------------------------------------
# Create a room
# ---------------------------------------------------------------------------
class CreateRoomScreen(OnlineScreen):
    """Form: room name and, optionally, a password."""
    TITLE_Y = 96                       # title (px)
    BOX = (350, 180, 580, 420)         # form box (x, y, width, height)
    # Room name field (x, y, width, height) in px.
    NAME_FIELD = (390, 236, 500, layout.BUTTON_H)
    PRIVATE_BOX = (390, 326, 360, 40)  # password check box (x, y, w, h)
    # Password field (x, y, width, height) in px.
    PASSWORD_FIELD = (390, 420, 500, layout.BUTTON_H)
    FREE_NOTE_Y = 448                  # free room note, instead of the field
    CREATE_SIZE = (300, layout.BUTTON_H)   # create button (w, h) in px
    CREATE_CENTER = (layout.CENTER_X, 540)  # centre of that button (px)

    def __init__(self, app):
        super().__init__(app)
        user = self.net.username or ""
        self.name = widgets.TextField(
            self.NAME_FIELD, "NOMBRE DE LA SALA", lobby.ROOM_NAME_MAX,
            value=f"Sala de {user}"[:lobby.ROOM_NAME_MAX])
        self.private = widgets.CheckBox(self.PRIVATE_BOX, "Con contraseña")
        self.password = widgets.TextField(self.PASSWORD_FIELD, "CONTRASEÑA",
                                          PASSWORD_MAX_LEN, password=True)
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
        msg = {"type": wire.CREATE_ROOM, "name": name}
        if self.private.value:
            if not self._password_given():
                return
            msg["password"] = self.password.value
        self.app.audio.play("confirm")
        self.net.send(msg)

    def _password_given(self):
        if not self.password.value:
            self.notify("Escribí la contraseña (o destildá «Con contraseña»).")
            self.password.focus(True)
            return False
        return True

    def handle_event(self, ev):
        if self.handle_back(ev):
            return
        self.password.enabled = self.private.value
        if self.private.handle_event(ev):
            self._private_toggled()
            return
        if self._fields_event(ev):
            return
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.create_rect.collidepoint(ev.pos)
        elif _left_click_on(ev, self.create_rect):
            self.create()

    def _private_toggled(self):
        self.app.audio.play("select")
        self.password.enabled = self.private.value
        self.name.focus(False)
        self.password.focus(self.private.value)

    def _fields_event(self, ev):
        """True if one of the two text fields used the event."""
        for field, other in ((self.name, self.password),
                             (self.password, self.name)):
            r = field.handle_event(ev)
            if r == "submit":
                self._submit(field)
            elif r == "tab":
                field.focus(False)
                other.focus(other.enabled)
            elif r and field.focused:
                other.focus(False)
            if r:
                return True
        return False

    def _submit(self, field):
        """Enter: go to the password if it is missing, or create."""
        if (field is self.name and self.private.value
                and not self.password.value):
            self.name.focus(False)
            self.password.focus(True)
        else:
            self.create()

    def on_net(self, msg):
        if msg["type"] == wire.ROOM:
            self.app.switch(RoomScreen(self.app))
            return
        super().on_net(msg)

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        screens.dim(surf, layout.VEIL_LIST)
        screens.title(surf, "CREAR SALA", (layout.CENTER_X, self.TITLE_Y),
                      layout.FONT_TITLE_L)
        screens.panel(surf, pygame.Rect(self.BOX))
        self._fields(surf)
        screens.button(surf, self.create_rect, "CREAR", self.hover, True,
                       layout.FONT_TEXT, self.t)
        screens.footer(surf, "Enter: crear  -  Tab: siguiente campo  -  "
                       "Esc: volver")
        self.draw_common(surf)


    def _fields(self, surf):
        self.name.draw(surf, self.t)
        self.private.draw(surf)
        if self.private.value:
            self.password.draw(surf, self.t)
        else:
            assets.draw_text(surf, "Sala libre: cualquiera de la lista puede "
                             "entrar.", layout.FONT_SMALL,
                             (layout.CENTER_X, self.FREE_NOTE_Y),
                             palette.INK_SOFT, outline=None)


# ---------------------------------------------------------------------------
# Room: choose a character and confirm
# ---------------------------------------------------------------------------
class RoomScreen(OnlineScreen):
    """Same layout as the local selection (match_screens.SelectScreen): me
    on the left, the rival on the right and the row of cards below."""
    IN_ROOM = True
    BACK_LABEL = "◄ SALIR"
    LEFT_KEYS = (pygame.K_a, pygame.K_LEFT)
    RIGHT_KEYS = (pygame.K_d, pygame.K_RIGHT)
    OK_KEYS = (pygame.K_SPACE, pygame.K_p, pygame.K_RETURN,
               pygame.K_KP_ENTER)
    # s: if the server still does not show my character, it is sent again.
    RESEND_AFTER = 1.0
    SUBTITLE_Y = 80                    # kind of room and owner (px)
    # Box with the name (wider than in the local selection: it has the tag).
    TAG = (320, 70)
    HINT_Y = 466                       # key hint, below my buttons (px)
    QUESTION_Y = 300                   # "?" where the rival is missing (px)
    DOTS_HZ = 2                        # waiting dots added per second...
    MAX_DOTS = 3                       # ...up to three
    # If both chose the same card, the rival frame goes inside (px).
    RIVAL_INNER_MARGIN = 2

    def __init__(self, app):
        super().__init__(app)
        me, _ = members(self.net)
        pre = ((me and me["character"])
               or getattr(app, "last_online_char", None) or CHARACTER_IDS[0])
        self.cursor = CHARACTER_IDS.index(pre)
        self.sent_char = None
        self.sent_at = -math.inf               # nothing was sent yet
        self.hover = None

    def back(self):
        self.net.leave_room()
        self.app.switch(RoomsScreen(self.app))

    def choosing(self):
        return bool(self.net.room) and self.net.room["state"] == lobby.CHOOSING

    def buttons(self):
        return match_screens.choice_buttons(PLAYER_X[0])

    def my_ready(self):
        me, _ = members(self.net)
        return bool(me and me["ready"])

    def move(self, d):
        if self.my_ready():
            return
        self.cursor = (self.cursor + d) % len(CHARACTER_IDS)
        self.app.audio.play("select")

    def sync_character(self):
        """Tells the server which character I have (the rival sees it)."""
        me, _ = members(self.net)
        if not self.choosing() or me is None:
            return
        cid = CHARACTER_IDS[self.cursor]
        stale = self.t - self.sent_at > self.RESEND_AFTER
        if me["character"] != cid and (cid != self.sent_char or stale):
            self.net.send({"type": wire.CHOOSE_CHARACTER, "character": cid})
            self.sent_char, self.sent_at = cid, self.t
            self.app.last_online_char = cid

    def toggle_ready(self):
        if not self.choosing():
            self.notify("Esperá a que entre un rival.", palette.GOLD)
            self.app.audio.play("blocked")
            return
        ready = not self.my_ready()
        if ready:
            self.sync_character()
        self.net.send({"type": wire.READY, "ready": ready})
        self.app.audio.play("confirm" if ready else "back")

    def handle_event(self, ev):
        if self.handle_back(ev):
            return
        if ev.type == pygame.KEYDOWN:
            self._key(ev.key)
        elif ev.type == pygame.MOUSEMOTION:
            self.hover = next((n for n, r in self.buttons().items()
                               if r.collidepoint(ev.pos)), None)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._click(ev.pos)

    def _key(self, key):
        if key in self.LEFT_KEYS:
            self.move(-1)
        elif key in self.RIGHT_KEYS:
            self.move(1)
        elif key in self.OK_KEYS:
            self.toggle_ready()

    def _click(self, pos):
        b = self.buttons()
        if b["ok"].collidepoint(pos):
            self.toggle_ready()
        elif b["prev"].collidepoint(pos):
            self.move(-1)
        elif b["next"].collidepoint(pos):
            self.move(1)
        elif not self.my_ready():
            for k in range(len(CHARACTER_IDS)):
                if match_screens.card_rect(k).collidepoint(pos):
                    self.cursor = k
                    self.app.audio.play("select")

    def update(self, dt):
        super().update(dt)
        if not self.my_ready():
            self.sync_character()

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def _player(self, surf, x, cid, facing, ready, color,
                scale=SELECT.PLAYER_SCALE):
        ang, bob = (sprites.celebrate_pose(self.t) if ready
                    else sprites.idle_pose(self.t))
        img, (fx, fy) = self.app.sprites.player(cid, facing, ang, bob, color,
                                                False, scale)
        surf.blit(img, (x - fx, SELECT.FEET_Y - fy))

    def _pedestal(self, surf, x):
        ped = pygame.Rect((0, 0), SELECT.PEDESTAL)
        ped.midtop = (x, SELECT.PEDESTAL_TOP)
        retro.bevel_box(surf, ped, palette.STRUCT, shadow=True)

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def _tag(self, surf, x, name, sub, color):
        tag = pygame.Rect((0, 0), self.TAG)
        tag.midtop = (x, SELECT.TAG_TOP)
        inner = screens.panel(surf, tag)
        pygame.draw.rect(surf, color, (inner.left, inner.top, inner.width,
                                       SELECT.TAG_BAR_H))
        assets.draw_text(surf, name, layout.FONT_TEXT,
                         (x, inner.top + SELECT.TAG_NAME_Y), palette.INK,
                         outline=None)
        assets.draw_text(surf, sub, layout.FONT_SMALL,
                         (x, inner.top + SELECT.TAG_TEAM_Y), palette.INK_SOFT,
                         outline=None)

    def _ready_sign(self, surf, i):
        """Ready sign next to player i (0 = me, on the left; 1 = rival)."""
        x = PLAYER_X[i] + SELECT.READY_X * FACING[i]
        assets.draw_text(surf, "¡LISTO!", layout.FONT_LARGE,
                         (x, SELECT.READY_Y), palette.GREEN, kind="title",
                         outline=palette.INK, shadow=True)

    def _question(self, surf):
        assets.draw_text(surf, "?", layout.FONT_GIANT,
                         (PLAYER_X[1], self.QUESTION_Y), palette.WHITE,
                         kind="title", outline=palette.INK, shadow=True)

    def draw(self, surf):
        room = self.net.room
        surf.blit(self.app.background, (0, 0))
        screens.dim(surf, layout.VEIL_OVERLAY)
        if not room:
            self.draw_common(surf)
            return
        me, rival = members(self.net)
        self._header(surf, room)
        self._me(surf, bool(me and me["ready"]))
        self._rival(surf, rival)
        self._middle(surf)
        self._cards(surf, rival)
        self._bottom(surf, room, me, rival)

    def _bottom(self, surf, room, me, rival):
        """Go sign when both are ready, footer and common parts."""
        if (room["state"] == lobby.CHOOSING and me and rival and me["ready"]
                and rival["ready"]):
            _go_sign(surf)
        screens.footer(surf, "Esc: salir de la sala  -  Mouse: botones y "
                       "tarjetas")
        self.draw_common(surf)

    def _header(self, surf, room):
        screens.title(surf, room["name"].upper(),
                      (layout.CENTER_X, SELECT.TITLE_Y), layout.FONT_TITLE_S)
        kind = "con contraseña" if room["private"] else "libre"
        assets.draw_text(surf, f"Sala {kind} de {room['owner']}  -  Los lados "
                         "se sortean al empezar el partido", layout.FONT_SMALL,
                         (layout.CENTER_X, self.SUBTITLE_Y), palette.INK,
                         outline=palette.WHITE)

    def _me(self, surf, ready):
        my_x = PLAYER_X[0]
        cid = CHARACTER_IDS[self.cursor]
        self._pedestal(surf, my_x)
        self._player(surf, my_x, cid, FACING[0], ready, ME_COLOR)
        self._tag(surf, my_x, self.net.display or "",
                  characters.short_name(characters.CHARACTERS_BY_ID[cid]),
                  ME_COLOR)
        self._my_buttons(surf, ready)
        if ready:
            self._ready_sign(surf, 0)

    def _my_buttons(self, surf, ready):
        b = self.buttons()
        t, font = self.t, layout.FONT_TEXT
        screens.button(surf, b["prev"], "◄", self.hover == "prev", not ready,
                       font, t)
        screens.button(surf, b["ok"], "CANCELAR" if ready else "¡LISTO!",
                       self.hover == "ok", self.choosing(), font, t)
        screens.button(surf, b["next"], "►", self.hover == "next", not ready,
                       font, t)

    def _rival(self, surf, rival):
        rival_x = PLAYER_X[1]
        if rival is None:
            self._no_rival(surf, rival_x)
            return
        self._pedestal(surf, rival_x)
        self._rival_character(surf, rival, rival_x)
        self._tag(surf, rival_x, rival["display"], _rival_note(rival),
                  RIVAL_COLOR)
        if rival["ready"]:
            self._ready_sign(surf, 1)

    def _rival_character(self, surf, rival, rival_x):
        rc = rival["character"]
        if rc:
            self._player(surf, rival_x, rc, FACING[1], rival["ready"],
                         RIVAL_COLOR)
        else:
            self._question(surf)

    def _no_rival(self, surf, rival_x):
        dots = "." * (1 + int(self.t * self.DOTS_HZ) % self.MAX_DOTS)
        self._tag(surf, rival_x, "ESPERANDO RIVAL" + dots,
                  "La sala aparece en la lista de salas", RIVAL_COLOR)
        self._question(surf)

    def _middle(self, surf):
        """VS sign and the key hint below my buttons."""
        assets.draw_text(surf, "VS", layout.FONT_BANNER,
                         (layout.CENTER_X, SELECT.VS_Y), palette.WHITE,
                         kind="title", outline=palette.INK, shadow=True)
        hint = ("A/D o flechas: elegir  -  Espacio, P o Enter: listo"
                if self.choosing()
                else "Cuando entre un rival van a poder confirmar")
        assets.draw_text(surf, hint, layout.FONT_SMALL,
                         (PLAYER_X[0], self.HINT_Y), palette.INK,
                         outline=palette.WHITE)

    def _cards(self, surf, rival):
        for k, c in enumerate(CHARACTER_IDS):
            mine = k == self.cursor
            theirs = rival is not None and rival["character"] == c
            rr = match_screens.draw_card(surf, self.app.sprites, k,
                                         mine or theirs)
            if mine:
                _frame(surf, rr, ME_COLOR, match_screens.SELECTION_MARGIN)
            if theirs:
                _frame(surf, rr, RIVAL_COLOR,
                       self.RIVAL_INNER_MARGIN if mine
                       else match_screens.SELECTION_MARGIN)


def _go_sign(surf):
    assets.draw_text(surf, "¡A LA CANCHA!", layout.FONT_TITLE_S,
                     (layout.CENTER_X, SELECT.GO_Y), palette.GOLD,
                     kind="title", outline=palette.INK, shadow=True)


def _frame(surf, rr, color, margin):
    pygame.draw.rect(surf, color, rr.inflate(2 * margin, 2 * margin),
                     match_screens.SELECTION_LINE)


def _rival_note(rival):
    """Second line of the rival tag."""
    if not rival.get("connected", True):
        return "desconectado: esperando que vuelva"
    rc = rival["character"]
    if rc:
        return characters.short_name(characters.CHARACTERS_BY_ID[rc])
    return "eligiendo personaje..."


# ---------------------------------------------------------------------------
# Online match
# ---------------------------------------------------------------------------
class OnlineMatchScreen(match_screens.MatchScreen):
    """The simulation runs on the server: here only controls and requests
    are sent, and what arrives is drawn (smoothed)."""
    INPUT_KEEPALIVE = 0.25     # s: the controls are repeated even if equal
    SIDE_BANNER_TIME = 5.0             # s the side sign is shown at start
    SIDE_BANNER_Y = 440                # height of that sign (px)
    # s from the end by forfeit to the result (by time: FINAL_WAIT).
    FORFEIT_WAIT = 1.0
    MATCH_BUTTON_W = 150               # width of the pause and quit buttons
    MATCH_BUTTON_GAP = 8               # px between those two buttons
    # Ready and quit buttons of the pause (px).
    PAUSE_MENU_CENTER = (layout.CENTER_X, 500)
    PAUSE_MENU_W = 340                 # width of those buttons (px)
    MENU_BUTTON_H = 50                 # height of pause and confirm buttons
    MENU_GAP = 12                      # px between those buttons
    # Buttons of the quit confirmation (px).
    CONFIRM_MENU_CENTER = (layout.CENTER_X, 440)
    CONFIRM_MENU_W = 380               # width of those buttons (px)
    # Centre of the signs (pause, disconnected, quit) in px.
    OVERLAY_CENTER = (layout.CENTER_X, 400)
    CONFIRM_BOX = (560, 260)           # quit confirmation (width, height)
    CONFIRM_TITLE_Y = 34               # title, from the box top (px)
    CONFIRM_TEXT_Y = 80                # explanation, from the box top (px)
    OVERLAY_W = 600                    # width of the pause/connection sign
    OVERLAY_H = 230                    # height of the connection sign...
    OVERLAY_PAUSE_H = 360              # ...and of the pause one (has buttons)
    OVERLAY_TITLE_Y = 40               # title, from the sign top (px)
    OVERLAY_TEXT_Y = 92                # first line, from the sign top (px)
    READY_LINES_Y = 156                # ready line of each player (px)
    REPLAY_CAN_SKIP = False            # the server decides: no S here

    def __init__(self, app, start):
        players = sorted(start["players"], key=lambda p: p["side"])
        self.start_msg = start
        self.names = [p["display"] for p in players]
        self.you = start["you"]
        super().__init__(app, [p["character"] for p in players])
        self.viewer = self.you
        self.net = app.online()
        self.match_id = start["match"]
        self.filter.expect(self.match_id)
        self._init_online()
        self._online_buttons()

    def _init_online(self):
        self.deduper = protocol.EventDeduper()
        self.interp = interp.Interpolator()
        # Own player predicted by the client (the rest is authoritative).
        self.predict = prediction.Prediction(self.you)
        self.predict.enabled = bool(getattr(self.app, "prediction",
                                            ONLINE.PREDICT_ENABLED))
        self.last_sent = None
        self.last_sent_t = -1.0
        self.confirm = None
        self.side_banner = self.SIDE_BANNER_TIME

    def _online_buttons(self):
        top, w = screens.BackButton.TOP, self.MATCH_BUTTON_W
        h = layout.BUTTON_SMALL_H
        self.pause_button = screens.BackButton(
            self.request_pause, "II PAUSA",
            rect=(layout.SCREEN_MARGIN, top, w, h))
        self.quit_button = screens.BackButton(
            self.ask_abandon, "ABANDONAR",
            rect=(layout.SCREEN_MARGIN, top + h + self.MATCH_BUTTON_GAP, w, h))
        self.pause_menu = self._menu(
            [("Estoy listo", self.ready_pause),
             ("Abandonar", self.ask_abandon)],
            self.PAUSE_MENU_CENTER, self.PAUSE_MENU_W)

    def _menu(self, items, center, width):
        return screens.Menu(items, center, width=width,
                            height=self.MENU_BUTTON_H, gap=self.MENU_GAP,
                            size=layout.FONT_TEXT)

    # ------------------------------------------------------------ hooks
    def pause_items(self):
        return []

    def enter(self):
        for cid in set(self.chars):
            self.app.sprites.warm(cid)
        self.app.input.capture = True
        self.app.fx.clear()
        # The effects are this player's: no leftovers of the last match.
        self.app.postfx.clear()
        self.app.postfx.viewer = self.viewer
        self.waiting = None

    def on_link(self, msgs, state):
        """The local process takes no part in the online match."""

    def on_focus_lost(self):
        """Online, the match is not paused when the focus is lost."""

    def _on_event(self, m):
        if m["type"] == protocol.EV_PAUSED:
            return              # the online pause arrives as pause_info
        super()._on_event(m)

    # ------------------------------------------------------------ network
    def on_net(self, msg):
        t = msg["type"]
        if t == wire.STATE:
            self._on_state(msg)
        elif t == wire.EVENT:
            self._on_remote_event(msg["e"])
        elif t in (wire.MATCH_OVER, wire.MATCH_START):
            self._on_match_change(msg)
        elif t == wire.PAUSE_INFO and msg["status"] == wire.PAUSE_ACTIVE:
            self.app.input.release_all()
        elif t == wire.ROOMS:
            self.app.switch(RoomsScreen(self.app, "Ya no estás en esa sala."))
        elif t == wire.ERROR:
            self.toast(msg["message"], palette.RED)

    def _on_match_change(self, msg):
        """End of this match, or a new one (a rematch) started."""
        if msg["type"] == wire.MATCH_OVER:
            if msg.get("match") == self.match_id:
                self._on_match_over(msg)
        elif msg["match"] != self.match_id:
            self.app.switch(OnlineMatchScreen(self.app, msg))

    def _on_state(self, msg):
        if msg.get("match") == self.match_id and self.filter.accept(msg):
            now = time.monotonic()
            self.state = msg
            self.interp.push(msg, now)
            self.predict.reconcile(msg, now)

    def _on_remote_event(self, e):
        if e.get("match") != self.match_id:
            self.ignored_events += 1
        elif self.deduper.fresh(e):
            self._on_event(e)

    def _on_match_over(self, msg):
        if self.end_info is None:
            self.end_info = msg
            self.end_timer = (self.FINAL_WAIT
                              if msg["reason"] == wire.END_TIME
                              else self.FORFEIT_WAIT)
            self.app.audio.play("whistle_end")

    # ------------------------------------------------------------ actions
    def overlay(self):
        """Which sign covers the match: None, "self", "opponent" or
        "pause"."""
        if self.net.status == client.RECONNECTING:
            return "self"
        opp = self.net.opponent
        if opp and not opp["connected"]:
            return "opponent"
        if self.net.pause.get("status") == wire.PAUSE_ACTIVE:
            return "pause"
        return None

    def request_pause(self, reason=None):
        del reason  # Unused: online there is only one kind of pause.
        if self.state is None or self.end_info is not None:
            return
        if self.net.pause.get("status") != wire.PAUSE_NONE:
            return
        self.net.send({"type": wire.PAUSE_REQUEST})
        self.app.audio.play("confirm")
        self.toast("Pediste la pausa: se activa después del próximo gol",
                   palette.GOLD)

    def ready_pause(self):
        self.net.send({"type": wire.PAUSE_READY})

    def ask_abandon(self):
        if self.end_info is not None:
            return
        self.confirm = self._menu(
            [("No, seguir jugando", self.close_confirm),
             ("Sí, abandonar", self.abandon)],
            self.CONFIRM_MENU_CENTER, self.CONFIRM_MENU_W)

    def close_confirm(self):
        self.confirm = None

    def abandon(self):
        self.net.abandon()
        self.app.switch(RoomsScreen(self.app, "Abandonaste el partido."))

    def _update_buttons(self, overlay):
        self.quit_button.visible = self.end_info is None
        self.pause_button.visible = (
            overlay is None and self.end_info is None
            and self.net.pause.get("status") == wire.PAUSE_NONE)

    def handle_event(self, ev):
        if self.confirm is not None:
            self._confirm_event(ev)
            return
        overlay = self.overlay()
        self._update_buttons(overlay)
        if (self.quit_button.handle_event(ev)
                or self.pause_button.handle_event(ev)):
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self._escape_online(overlay)
        elif overlay == "pause":
            self.pause_menu.handle_event(ev, self.app.audio)

    def _confirm_event(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.confirm = None
        else:
            self.confirm.handle_event(ev, self.app.audio)

    def _escape_online(self, overlay):
        if overlay == "pause":
            self.ready_pause()
        elif overlay is None:
            self.request_pause()

    # ------------------------------------------------------------ cycle
    def update(self, dt):
        screens.Screen.update(self, dt)
        self.tick_effects(dt)
        self.side_banner -= dt
        overlay = self.overlay()
        self._update_menus(dt, overlay)
        self._send_online_controls(overlay)
        self._step_prediction(dt, overlay)
        self.match_sounds_and_snow()
        self._pause_note()
        self._check_end(dt)

    def _check_end(self, dt):
        """Goes to the result after the wait, or to the error screen."""
        if self.end_info is not None:
            self.end_timer -= dt
            if self.end_timer <= 0:
                self.app.switch(OnlineResultScreen(self.app, self.start_msg,
                                                   self.end_info))
                return
        if self.net.fatal:
            self.app.switch(OnlineErrorScreen(self.app, self.net.fatal))

    def _update_menus(self, dt, overlay):
        self.pause_menu.enabled = overlay == "pause" and self.confirm is None
        self.pause_menu.update(dt)
        if self.confirm is not None:
            self.confirm.update(dt)

    def _send_online_controls(self, overlay):
        """Controls go only when they change (plus a heartbeat); both key
        sets are valid."""
        st = self.state
        snap = self.app.input.snapshot_single(self._playing(overlay))
        now = time.monotonic()
        heartbeat = now - self.last_sent_t > self.INPUT_KEEPALIVE
        if snap != self.last_sent or heartbeat:
            # The sequence number lets the client reconcile its prediction:
            # the server echoes it back in every state ("ack").
            self.net.send_input(snap, self.predict.push_input(snap))
            self.last_sent, self.last_sent_t = snap, now
        self.app.audio.crowd(st is not None and not st["paused"]
                             and overlay is None)

    def _playing(self, overlay):
        """True in effective play, with nothing covering the match."""
        st = self.state
        return (st is not None and overlay is None and self.confirm is None
                and not st["paused"]
                and st["phase"] == protocol.PHASE_PLAYING)

    def _step_prediction(self, dt, overlay):
        """Predicts the own player, but only in effective play: in a pause,
        in the goal hold and in the replay the server state is drawn."""
        st = self.state
        if st is None:
            return
        self.predict.set_latency(self.net.rtt)
        if not self._playing(overlay):
            self.predict.hold(st)
            return
        self.predict.play()
        self.predict.step(dt)

    def _pause_note(self):
        pause = self.net.pause
        pending = (pause.get("status") == wire.PAUSE_PENDING
                   and self.end_info is None)
        self.renderer.center_note = (f"{pause.get('by_name')} pidió la pausa"
                                     if pending else None)

    # ------------------------------------------------------------ drawing
    def draw(self, surf):
        st = self.state
        if st is None:
            self._draw_waiting_server(surf)
            return
        view = self.interp.sample(time.monotonic()) or st
        self.draw_match(surf, self.predict.apply(view), st)
        overlay = self.overlay()
        self._signs(surf, overlay)
        self._draw_buttons(surf, overlay)
        self._draw_dialogs(surf, overlay)

    def _draw_dialogs(self, surf, overlay):
        """Pause or connection sign, quit confirmation and status."""
        if overlay is not None:
            self._draw_overlay(surf, overlay)
        if self.confirm is not None:
            self._draw_confirm(surf)
        status_chip(surf, self.net, self.t, bottom=True)

    def _draw_buttons(self, surf, overlay):
        self._update_buttons(overlay)
        self.pause_button.draw(surf, self.t)
        self.quit_button.draw(surf, self.t)

    def _draw_waiting_server(self, surf):
        surf.blit(self.app.background, (0, 0))
        screens.dim(surf, layout.VEIL_OVERLAY)
        screens.title(surf, "Preparando partido...",
                      (layout.CENTER_X, self.MESSAGE_Y), layout.FONT_LARGE,
                      palette.WHITE)
        assets.draw_text(surf, "Esperando al servidor", layout.FONT_SMALL,
                         (layout.CENTER_X, self.MESSAGE_NOTE_Y), palette.INK,
                         outline=palette.WHITE)
        status_chip(surf, self.net, self.t, bottom=True)

    def _signs(self, surf, overlay):
        """Side sign at the start and the end of match sign."""
        if self.side_banner > 0 and overlay is None and self.end_info is None:
            side = "IZQUIERDA" if self.you == 0 else "DERECHA"
            assets.draw_text(surf, f"JUGÁS A LA {side}", layout.FONT_TITLE_S,
                             (layout.CENTER_X, self.SIDE_BANNER_Y),
                             config.PLAYER_COLORS[self.you], kind="title",
                             outline=palette.INK, shadow=True)
        if self.end_info is not None:
            head = ("¡FINAL DEL PARTIDO!"
                    if self.end_info["reason"] == wire.END_TIME
                    else "¡PARTIDO TERMINADO!")
            screens.title(surf, head, (layout.CENTER_X, self.MESSAGE_Y),
                          layout.FONT_TITLE_L, palette.WHITE)

    def _draw_confirm(self, surf):
        screens.dim(surf, layout.VEIL_OVERLAY)
        box = pygame.Rect((0, 0), self.CONFIRM_BOX)
        box.center = self.OVERLAY_CENTER
        inner = screens.panel(surf, box)
        screens.title(surf, "¿ABANDONAR?",
                      (layout.CENTER_X, inner.top + self.CONFIRM_TITLE_Y),
                      layout.FONT_TITLE_S, palette.RED)
        assets.draw_text(surf, "Si abandonás, perdés el partido y salís de la "
                         "sala.", layout.FONT_SMALL,
                         (layout.CENTER_X, inner.top + self.CONFIRM_TEXT_Y),
                         palette.INK, outline=None)
        self.confirm.draw(surf)

    def _draw_overlay(self, surf, overlay):
        screens.dim(surf, layout.VEIL_OVERLAY)
        height = self.OVERLAY_PAUSE_H if overlay == "pause" else self.OVERLAY_H
        r = pygame.Rect(0, 0, self.OVERLAY_W, height)
        r.center = self.OVERLAY_CENTER
        inner = screens.panel(surf, r)
        title_y = inner.top + self.OVERLAY_TITLE_Y
        if overlay == "self":
            lines = self._self_lost(surf, title_y)
        elif overlay == "opponent":
            lines = self._opponent_lost(surf, title_y)
        else:
            lines = self._pause_box(surf, title_y, inner)
        self._overlay_lines(surf, lines, inner, overlay != "pause")

    def _overlay_lines(self, surf, lines, inner, big_first):
        for k, ln in enumerate(lines):
            big = big_first and k == 0
            assets.draw_text(surf, ln, layout.FONT_TEXT if big
                             else layout.FONT_SMALL,
                             (layout.CENTER_X, inner.top + self.OVERLAY_TEXT_Y
                              + k * layout.TEXT_LINE_H_BIG), palette.INK,
                             outline=None)

    def _self_lost(self, surf, title_y):
        left = self.net.reconnect_left() or 0
        screens.title(surf, "SE CORTÓ TU CONEXIÓN", (layout.CENTER_X, title_y),
                      layout.FONT_LARGE, palette.RED)
        return [f"Reconectando... ({left:.0f} s)",
                "El partido está en pausa para los dos.",
                "Si no volvés a tiempo, perdés por abandono."]

    def _opponent_lost(self, surf, title_y):
        opp = self.net.opponent
        left = self.net.countdown(opp) or 0
        screens.title(surf, "SIN CONEXIÓN", (layout.CENTER_X, title_y),
                      layout.FONT_TITLE_S, palette.RED)
        return [f"{opp['name']} perdió la conexión.",
                f"Esperando que vuelva: {left:.0f} s",
                "Si no vuelve, ganás por abandono."]

    def _pause_box(self, surf, title_y, inner):
        p = self.net.pause
        left = self.net.countdown(p) or 0
        screens.title(surf, "PAUSA", (layout.CENTER_X, title_y),
                      layout.FONT_TITLE)
        for i in (0, 1):
            self._ready_line(surf, inner, i, p.get("ready", [False, False])[i])
        self.pause_menu.draw(surf)
        return [f"Pedida por {p.get('by_name')}.",
                f"Se sigue jugando en {left:.0f} s o cuando los dos estén "
                "listos."]

    def _ready_line(self, surf, inner, i, ok):
        assets.draw_text(surf, f"{self.names[i]}: "
                         f"{'LISTO' if ok else 'esperando...'}",
                         layout.FONT_TEXT,
                         (layout.CENTER_X, inner.top + self.READY_LINES_Y
                          + i * layout.TEXT_LINE_H_BIG),
                         palette.GREEN if ok else palette.INK_SOFT,
                         outline=None)

    def debug_info(self):
        info = super().debug_info()
        info["ui_pause"] = self.net.pause.get("status")
        info["prediccion"] = self.predict.debug_text()
        return info


# ---------------------------------------------------------------------------
# Result (rematch with the sides drawn again)
# ---------------------------------------------------------------------------
class OnlineResultScreen(OnlineScreen):
    """Result of an online match, with rematch and room options."""
    IN_ROOM = True
    BACK_LABEL = "◄ SALIR"
    # Rematch, change character and leave buttons (px).
    MENU_CENTER = (layout.CENTER_X, 590)
    MENU_W = 380                       # width of those buttons (px)
    MENU_BUTTON_H = 48                 # height (three, below the note)
    MENU_GAP = 10                      # px between those buttons
    PLAYER_X = (290, 990)              # x of each player (px)
    FEET_Y = 450                       # y of the players feet (px)
    WINNER_SCALE = 2.0                 # the winner looks bigger...
    LOSER_SCALE = 1.6                  # ...than the loser (or both, if draw)
    CHARACTER_Y = 478                  # character name of each player (px)
    NAME_Y = 504                       # name of the person (px)
    CONFETTI_EVERY = 1.4               # s between confetti over the winner
    CONFETTI_Y = 230                   # height of that confetti (px)
    HEADLINE_Y = 64                    # winner or draw sign (px)
    SUBTITLE_Y = 124                   # won/lost/forfeit line (px)
    SCORE_CENTER = (layout.CENTER_X, 270)   # board with the result (px)
    SCORE_W = 300                      # width of the board (px)
    NOTE_W = 440                       # rematch note: width...
    NOTE_TEXT_W = 400                  # ...and maximum width of its text
    NOTE_PAD_Y = 16                    # px added to the note lines
    NOTE_TOP = 342                     # top edge of the note (px)
    NOTE_TEXT_Y = 11                   # first line, from the note top (px)

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
        self.heat = None           # channel of the heat map (F6), None: off

    def enter(self):
        self.app.audio.crowd(False)
        self.app.fx.clear()

    def char_name(self, i):
        n = characters.short_name(characters.CHARACTERS_BY_ID[self.chars[i]])
        if self.chars[0] == self.chars[1]:
            n += " (izq.)" if i == 0 else " (der.)"
        return n

    def back(self):
        self.net.leave_room()
        self.app.switch(RoomsScreen(self.app))

    def rematch(self):
        me, rival = members(self.net)
        if (me is None or rival is None
                or self.net.room["state"] != lobby.CHOOSING):
            return
        self.net.send({"type": wire.READY, "ready": not me["ready"]})

    def to_room(self):
        self.app.switch(RoomScreen(self.app))

    def build_menu(self):
        """Rebuilds the menu only when the rival or my ready change."""
        me, rival = members(self.net)
        key = (rival is not None, bool(me and me["ready"]))
        if key == self.menu_key:
            return
        self.menu_key = key
        if rival is not None:
            items = [("Cancelar revancha" if key[1] else "Revancha",
                      self.rematch), ("Cambiar personaje", self.to_room),
                     ("Salir de la sala", self.back)]
        else:
            items = [("Esperar otro rival", self.to_room),
                     ("Salir de la sala", self.back)]
        self._set_menu(items)

    def _set_menu(self, items):
        sel = self.menu.sel if self.menu else 0
        self.menu = screens.Menu(items, self.MENU_CENTER, width=self.MENU_W,
                                 height=self.MENU_BUTTON_H, gap=self.MENU_GAP,
                                 size=layout.FONT_TEXT)
        self.menu.sel = min(sel, len(items) - 1)

    def handle_event(self, ev):
        if self.handle_back(ev):
            return
        step = match_screens.heat_step(ev)
        if step:
            self.heat = match_screens.heat_cycle(self.heat, step)
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
            self.app.fx.confetti(x, self.CONFETTI_Y,
                                 [config.PLAYER_COLORS[self.winner],
                                  palette.WHITE, palette.GOLD])

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        screens.dim(surf, layout.VEIL_RESULT)
        self.app.postfx.heat_overlay(surf, self.heat)
        for i in (0, 1):
            self._player(surf, i)
        self.app.fx.draw(surf)
        self._headline(surf)
        self._board(surf)
        match_screens.heat_hint(surf, self.heat)
        self.draw_common(surf)

    def _board(self, surf):
        """Scoreboard, note and buttons of the result."""
        screens.scoreboard(surf, self.SCORE_CENTER, self.SCORE_W,
                           f"{self.score[0]}-{self.score[1]}")
        self._note(surf)
        if self.menu:
            self.menu.draw(surf)

    def _player(self, surf, i):
        x = self.PLAYER_X[i]
        win = self.winner == i
        ang, bob = (sprites.celebrate_pose(self.t) if win
                    else sprites.idle_pose(self.t, i))
        img, (fx, fy) = self.app.sprites.player(
            self.chars[i], FACING[i], ang, bob, config.PLAYER_COLORS[i], False,
            self.WINNER_SCALE if win else self.LOSER_SCALE)
        surf.blit(img, (x - fx, self.FEET_Y - fy))
        assets.draw_text(surf, self.char_name(i), layout.FONT_TEXT,
                         (x, self.CHARACTER_Y), config.PLAYER_COLORS[i],
                         outline=palette.INK)
        assets.draw_text(surf, self.names[i], layout.FONT_SMALL,
                         (x, self.NAME_Y), palette.INK, outline=palette.WHITE)

    def _headline(self, surf):
        if self.winner is None:
            head, col = "¡EMPATE!", palette.WHITE
        else:
            head = f"¡GANÓ {self.char_name(self.winner).upper()}!"
            col = config.PLAYER_COLORS[self.winner]
        screens.title(surf, head, (layout.CENTER_X, self.HEADLINE_Y),
                      layout.FONT_TITLE_L, col)
        assets.draw_text(surf, self._subtitle(), layout.FONT_TEXT,
                         (layout.CENTER_X, self.SUBTITLE_Y), palette.INK,
                         outline=palette.WHITE)

    def _subtitle(self):
        if self.over["reason"] == wire.END_FORFEIT:
            return f"{self.over.get('by_name')} abandonó el partido"
        if self.over["reason"] == wire.END_ERROR:
            return "El partido se cortó por un problema del servidor"
        if self.winner is None:
            return "Nadie ganó esta vez"
        return "¡Ganaste!" if self.winner == self.you else "Perdiste"

    def _rematch_status(self):
        me, rival = members(self.net)
        if rival is None:
            return "Tu rival se fue de la sala: podés esperar a otro."
        if rival["ready"] and me and me["ready"]:
            return "¡Revancha! Sorteando los lados..."
        if rival["ready"]:
            return f"{rival['display']} quiere la revancha"
        if me and me["ready"]:
            return f"Esperando a {rival['display']}..."
        return "Revancha: mismos personajes y los lados se sortean de nuevo"

    def _note(self, surf):
        lines = assets.wrap(self._rematch_status(), layout.FONT_SMALL,
                            self.NOTE_TEXT_W)
        note = pygame.Rect(0, 0, self.NOTE_W,
                           layout.TEXT_LINE_H * len(lines) + self.NOTE_PAD_Y)
        note.midtop = (layout.CENTER_X, self.NOTE_TOP)
        inner = retro.bevel_box(surf, note, palette.CREAM, shadow=False)
        _centered_lines(surf, lines, layout.FONT_SMALL,
                        inner.top + self.NOTE_TEXT_Y, layout.TEXT_LINE_H)


# ---------------------------------------------------------------------------
# Connection lost
# ---------------------------------------------------------------------------
class OnlineErrorScreen(screens.Screen):
    """The connection was lost for good: retry or go back."""
    MENU_CENTER = (layout.CENTER_X, 520)   # retry and back buttons (px)
    MENU_W = 300                       # width of those buttons (px)
    BOX = (900, 240)                   # message box (width, height) in px
    BOX_TOP = 150                      # top edge of the box (px)
    TITLE_Y = 40                       # title, from the box top (px)
    MESSAGE_Y = 104                    # first line of the reason (px)
    MESSAGE_MARGIN = 40                # px of air beside the reason
    MESSAGE_LINE_H = 32                # px between lines of the reason
    HINT_BOTTOM = 22                   # hint, from the box bottom (px)

    def __init__(self, app, message):
        super().__init__(app)
        self.message = message
        self.menu = screens.Menu([("Reintentar", self.retry),
                                  ("Volver", self.back)], self.MENU_CENTER,
                                 width=self.MENU_W)
        self.back_button = screens.BackButton(self.back)

    def enter(self):
        self.app.audio.crowd(False)
        self.app.input.capture = False

    def retry(self):
        self.app.close_online()
        self.app.switch(OnlineHomeScreen(self.app))

    def back(self):
        _to_multiplayer(self.app)

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
        screens.dim(surf, layout.VEIL_ERROR)
        r = pygame.Rect((0, 0), self.BOX)
        r.midtop = (layout.CENTER_X, self.BOX_TOP)
        inner = screens.panel(surf, r, face=palette.ERROR_PANEL,
                              border=palette.RED)
        self._texts(surf, inner)
        assets.draw_text(surf, "Revisá tu internet o que el servidor esté "
                         "encendido.", layout.FONT_SMALL,
                         (layout.CENTER_X, inner.bottom - self.HINT_BOTTOM),
                         palette.INK_SOFT, outline=None)
        self.menu.draw(surf)
        self.back_button.draw(surf, self.t)

    def _texts(self, surf, inner):
        screens.title(surf, "SIN CONEXIÓN",
                      (layout.CENTER_X, inner.top + self.TITLE_Y),
                      layout.FONT_TITLE, palette.RED)
        lines = assets.wrap(self.message, layout.FONT_TEXT,
                            inner.width - self.MESSAGE_MARGIN)
        _centered_lines(surf, lines, layout.FONT_TEXT,
                        inner.top + self.MESSAGE_Y, self.MESSAGE_LINE_H)
