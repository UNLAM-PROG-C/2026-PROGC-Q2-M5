"""Match screens: character selection, play and result.

MatchScreen is a Template Method: the tournament and the online match
extend it by overriding its hooks (extra_payload, controls, pause_items,
on_match_over). The simulation events are dispatched through a table of
handlers (one method per event type).
"""
import math

import pygame

from fdc import config
from fdc import protocol
from fdc.ui import assets
from fdc.ui import characters
from fdc.ui import icons
from fdc.ui import input as ui_input
from fdc.ui import layout
from fdc.ui import palette
from fdc.ui import render
from fdc.ui import retro
from fdc.ui import screens
from fdc.ui import sprites

CHARACTER_IDS = characters.CHARACTER_IDS
# x of each player in the selection (P1 on the left, P2 on the right), px.
PLAYER_X = (250, 1030)
FACING = (1, -1)                   # P1 looks right and P2 looks left
# --- row of character cards (local selection and tournament)
CARD_W = 150                       # px: width of each card
CARD_H = 168                       # px: height of each card
CARD_GAP = 14                      # px between cards
CARDS_TOP = 508                    # top edge of the row (px)
CARD_LIFT = 8                      # px the chosen card rises
CARD_NAME_BOTTOM = 14              # name, from the bottom edge of the card
SELECTION_MARGIN = 6               # px between the card and the chooser frame
# px: thickness of that frame (if both chose it, one inside the other).
SELECTION_LINE = 6
# --- mouse buttons below each character
CHOICE_BUTTONS_Y = 402             # top edge of the row (px)
OK_BUTTON_W = 172                  # width of the confirm/cancel button (px)
BUTTON_GAP = 12                    # px between the buttons
# Readable name of each effect target in the power notices.
TARGET_NAMES = {"goal0": "arco de {0}", "goal1": "arco de {1}",
                "ball": "pelota", "p0": "{0}", "p1": "{1}"}
# Sound of a power by category (the good ones use "power_good").
POWER_SOUNDS = {config.CATEGORY_BAD: "power_bad",
                config.CATEGORY_GLOBAL: "power_global"}
# Text of the pause box by reason (the others use the default one).
PAUSE_REASONS = {
    protocol.PAUSE_REASON_FOCUS:
        "La ventana perdió el foco: se liberaron los controles.",
    protocol.PAUSE_REASON_WATCHDOG:
        "Pausa automática: la simulación dejó de recibir controles."}
DEFAULT_PAUSE_REASON = "El reloj, los poderes y las bombas están detenidos."
# Status line of the pause box while waiting for the simulation.
PAUSE_STATUS = {"requested": "Pausando... esperando confirmación de la "
                             "simulación",
                "resuming": "Reanudando..."}
# Test mode keys: key name -> (command, power mode or None).
TEST_COMMANDS = {"f7": (protocol.CMD_DEBUG_POWER, "spawn"),
                 "f8": (protocol.CMD_DEBUG_POWER, "p0"),
                 "f9": (protocol.CMD_DEBUG_POWER, "p1"),
                 "f12": (protocol.CMD_DEBUG_CRASH, None)}
TEST_STEPS = {"f5": -1, "f6": 1}   # test mode keys that change the power
# Method of MatchScreen that handles each simulation event.
EVENT_HANDLERS = {
    protocol.EV_GOLDEN_GOAL: "_golden_goal",
    protocol.EV_KICKOFF: "_kickoff",
    protocol.EV_GOAL: "_goal",
    protocol.EV_MATCH_END: "_match_end",
    protocol.EV_PAUSED: "_paused",
    protocol.EV_POWER: "_power",
    protocol.EV_POWER_SPAWN: "_power_spawn",
    protocol.EV_PICKUP_EXPIRED: "_pickup_expired",
    protocol.EV_BOMB_ARMED: "_bomb_armed",
    protocol.EV_BOMB_EXPLODE: "_explosion",
    protocol.EV_KICK: "_kick",
    protocol.EV_KICK_BLOCKED: "_kick_blocked",
    protocol.EV_TOUCH: "_touch",
}


def card_rect(k):
    """Place of the card of character k in the row (centred, at the
    bottom)."""
    n = len(CHARACTER_IDS)
    total = n * CARD_W + (n - 1) * CARD_GAP
    x0 = layout.CENTER_X - total / 2
    return pygame.Rect(x0 + k * (CARD_W + CARD_GAP), CARDS_TOP, CARD_W, CARD_H)


def draw_card(surf, sprite_set, k, lifted):
    """Card of character k with its name (it rises a bit if chosen).
    Returns where it was drawn."""
    cid = CHARACTER_IDS[k]
    rr = card_rect(k).move(0, -CARD_LIFT if lifted else 0)
    pygame.draw.rect(surf, palette.INK,
                     rr.move(layout.SHADOW_OFFSET, layout.SHADOW_OFFSET))
    surf.blit(sprite_set.portrait(cid), rr)
    pygame.draw.rect(surf, palette.INK, rr, layout.FRAME_LINE)
    assets.draw_text(surf, characters.short_name(
        characters.CHARACTERS_BY_ID[cid]).upper(), layout.FONT_SMALL,
                     (rr.centerx, rr.bottom - CARD_NAME_BOTTOM), palette.WHITE,
                     outline=palette.INK)
    return rr


def choice_buttons(x):
    """Buttons previous, confirm/cancel and next centred at x, below the
    character."""
    half = OK_BUTTON_W // 2
    y = CHOICE_BUTTONS_Y
    arrow, h = layout.ARROW_BUTTON_W, layout.BUTTON_SMALL_H
    return {"prev": pygame.Rect(x - half - BUTTON_GAP - arrow, y, arrow, h),
            "ok": pygame.Rect(x - half, y, OK_BUTTON_W, h),
            "next": pygame.Rect(x + half + BUTTON_GAP, y, arrow, h)}


def by_strength(weakest, k):
    """Value between 'weakest' (soft hit, k = 0) and 1 (hard hit, k = 1)."""
    return weakest + (1 - weakest) * k


def selection_frames(surf, rr, chosen_by):
    """Frames of the players that chose a card (one inside the other)."""
    for n, i in enumerate(chosen_by):
        inset = SELECTION_LINE * n if len(chosen_by) == 2 else 0
        grow = 2 * SELECTION_MARGIN - inset * 2
        fr = rr.inflate(grow, grow)
        pygame.draw.rect(surf, config.PLAYER_COLORS[i], fr, SELECTION_LINE)
        yield i, fr


# ---------------------------------------------------------------------------
# Character selection (independent for each player)
# ---------------------------------------------------------------------------
class SelectScreen(screens.Screen):
    """Both players choose with their own keys or the mouse."""
    LABEL_INSET_X = 6                  # P1/P2 label, from the frame side (px)
    LABEL_RAISE = 12                   # label, above the frame edge (px)
    LABEL_PAD = (4, 2)                 # px of air around the label (x, y)
    READY_DELAY = 0.9                  # s with both ready before playing
    TITLE_Y = 40                       # title (px)
    SUBTITLE_Y = 84                    # note about equal abilities (px)
    TAG = (300, 70)                    # box with the character name (w, h)
    TAG_TOP = 108                      # top edge of that box (px)
    TAG_BAR_H = 6                      # band with the player colour (px)
    TAG_NAME_Y = 22                    # name, from the box top (px)
    TAG_TEAM_Y = 44                    # team and shirt, from the box top (px)
    PEDESTAL = (200, 18)               # pedestal below the character (w, h)
    PEDESTAL_TOP = 376                 # top edge of the pedestal (px)
    FEET_Y = 380                       # y of the character feet (px)
    PLAYER_SCALE = 1.9                 # size of the character
    READY_X = 170                      # ready sign, towards the centre (px)
    READY_Y = 300                      # ready sign, height (px)
    READY_BOB_HZ = 6                   # hops per second of the ready sign
    READY_BOB_PX = 4                   # px of those hops
    HINT_Y = 458                       # keys of each player (px)
    VS_Y = 280                         # VS sign (px)
    GO_Y = 360                         # sign when both are ready (px)

    def __init__(self, app, preselect=None):
        super().__init__(app)
        # Two different characters by default.
        pre = (preselect or app.last_characters
               or (CHARACTER_IDS[0], CHARACTER_IDS[2]))
        self.cursor = [CHARACTER_IDS.index(pre[0]),
                       CHARACTER_IDS.index(pre[1])]
        self.ready = [False, False]
        self.both_ready_t = None
        self.keys = [{a: ui_input.key_code(n)
                      for a, n in config.PLAYER_KEYS[i].items()}
                     for i in (0, 1)]
        self.hover = None
        self.back_button = screens.BackButton(self.back)

    def back(self):
        self.app.audio.play("back")
        self.app.switch(screens.MultiplayerMenuScreen(self.app))

    # ------------------------------------------------------------ geometry
    def buttons(self, i):
        """Mouse buttons of each player: previous, confirm and next."""
        return choice_buttons(PLAYER_X[i])

    # ------------------------------------------------------------ actions
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
            self._key(ev.key)
        elif ev.type == pygame.MOUSEMOTION:
            self._hover(ev.pos)
        elif (ev.type == pygame.MOUSEBUTTONDOWN
              and ev.button in (pygame.BUTTON_LEFT, pygame.BUTTON_RIGHT)):
            if not self._click_buttons(ev.pos):
                self._click_cards(ev)

    def _key(self, key):
        if key in screens.BACK_KEYS:
            self.back()
            return
        for i in (0, 1):
            k = self.keys[i]
            if key == k["left"]:
                self.move(i, -1)
            elif key == k["right"]:
                self.move(i, 1)
            elif key == k["kick"] and not self.ready[i]:
                self.toggle(i)
            elif key == k["jump"] and self.ready[i]:
                self.toggle(i)

    def _hover(self, pos):
        self.hover = None
        for i in (0, 1):
            for name, r in self.buttons(i).items():
                if r.collidepoint(pos):
                    self.hover = (i, name)

    def _click_buttons(self, pos):
        """True if the click was on a button of a player."""
        for i in (0, 1):
            b = self.buttons(i)
            if b["ok"].collidepoint(pos):
                self.toggle(i)
                return True
            for name, d in (("prev", -1), ("next", 1)):
                if b[name].collidepoint(pos):
                    self.move(i, d)
                    return True
        return False

    def _click_cards(self, ev):
        """Cards: a left click chooses for P1, a right click for P2."""
        i = 0 if ev.button == pygame.BUTTON_LEFT else 1
        for k in range(len(CHARACTER_IDS)):
            if card_rect(k).collidepoint(ev.pos) and not self.ready[i]:
                self.cursor[i] = k
                self.app.audio.play("select")

    def update(self, dt):
        super().update(dt)
        if not all(self.ready):
            return
        if self.both_ready_t is None:
            self.both_ready_t = self.READY_DELAY
        self.both_ready_t -= dt
        if self.both_ready_t <= 0:
            chars = [CHARACTER_IDS[c] for c in self.cursor]
            self.app.last_characters = chars
            self.app.switch(MatchScreen(self.app, chars))

    # ------------------------------------------------------------ drawing
    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        screens.dim(surf, layout.VEIL_OVERLAY)
        self._header(surf)
        for i in (0, 1):
            self._player_side(surf, i)
        assets.draw_text(surf, "VS", layout.FONT_BANNER,
                         (layout.CENTER_X, self.VS_Y), palette.WHITE,
                         kind="title", outline=palette.INK, shadow=True)
        self._cards(surf)
        self._footer(surf)

    def _header(self, surf):
        screens.title(surf, "ELEGÍ TU PERSONAJE",
                      (layout.CENTER_X, self.TITLE_Y), layout.FONT_TITLE)
        assets.draw_text(surf, "Todos tienen las mismas capacidades: sólo "
                         "cambia la apariencia. Pueden elegir el mismo.",
                         layout.FONT_SMALL, (layout.CENTER_X, self.SUBTITLE_Y),
                         palette.INK, outline=palette.WHITE)

    def _player_side(self, surf, i):
        """Everything of player i: tag, character, buttons and keys."""
        cid = CHARACTER_IDS[self.cursor[i]]
        x = PLAYER_X[i]
        self._tag(surf, i, characters.CHARACTERS_BY_ID[cid], x)
        self._character(surf, i, cid, x)
        self._buttons(surf, i)
        names = config.PLAYER_KEYS[i]
        label = ui_input.key_label
        hint = (f"{label(names['left'], True)}/{label(names['right'], True)}"
                f" elegir  {label(names['kick'], True)} confirmar  "
                f"{label(names['jump'], True)} cancelar")
        assets.draw_text(surf, hint, layout.FONT_SMALL, (x, self.HINT_Y),
                         palette.INK, outline=palette.WHITE)

    def _tag(self, surf, i, ch, x):
        tag = pygame.Rect((0, 0), self.TAG)
        tag.midtop = (x, self.TAG_TOP)
        inner = screens.panel(surf, tag)
        color = config.PLAYER_COLORS[i]
        pygame.draw.rect(surf, color, (inner.left, inner.top, inner.width,
                                       self.TAG_BAR_H))
        assets.draw_text(surf, f"{config.PLAYER_LABELS[i]}  "
                         f"{characters.short_name(ch).upper()}",
                         layout.FONT_TEXT, (x, inner.top + self.TAG_NAME_Y),
                         color, outline=palette.INK)
        assets.draw_text(surf, f"{ch['team']} - camiseta {ch['number']}",
                         layout.FONT_SMALL, (x, inner.top + self.TAG_TEAM_Y),
                         palette.INK, outline=None)

    def _character(self, surf, i, cid, x):
        """Pedestal and player (it celebrates when confirmed)."""
        ped = pygame.Rect((0, 0), self.PEDESTAL)
        ped.midtop = (x, self.PEDESTAL_TOP)
        retro.bevel_box(surf, ped, palette.STRUCT, shadow=True)
        ang, bob = (sprites.celebrate_pose(self.t) if self.ready[i]
                    else sprites.idle_pose(self.t, i))
        img, (fx, fy) = self.app.sprites.player(
            cid, FACING[i], ang, bob, config.PLAYER_COLORS[i], False,
            self.PLAYER_SCALE)
        surf.blit(img, (x - fx, self.FEET_Y - fy))
        if self.ready[i]:
            self._ready_sign(surf, i, x)

    def _ready_sign(self, surf, i, x):
        bob = self.READY_BOB_PX if int(self.t * self.READY_BOB_HZ) % 2 else 0
        assets.draw_text(surf, "¡LISTO!", layout.FONT_LARGE,
                         (x + self.READY_X * FACING[i], self.READY_Y + bob),
                         palette.GREEN, kind="title", outline=palette.INK,
                         shadow=True)

    def _buttons(self, surf, i):
        b = self.buttons(i)
        hv = self.hover
        free = not self.ready[i]
        screens.button(surf, b["prev"], "◄", hv == (i, "prev"), free,
                       layout.FONT_TEXT, self.t)
        screens.button(surf, b["ok"], "CANCELAR" if self.ready[i] else "OK",
                       hv == (i, "ok"), True, layout.FONT_TEXT, self.t)
        screens.button(surf, b["next"], "►", hv == (i, "next"), free,
                       layout.FONT_TEXT, self.t)

    def _cards(self, surf):
        for k in range(len(CHARACTER_IDS)):
            sel = [i for i in (0, 1) if self.cursor[i] == k]
            rr = draw_card(surf, self.app.sprites, k, bool(sel))
            for i, fr in selection_frames(surf, rr, sel):
                self._label(surf, i, fr)

    def _label(self, surf, i, fr):
        """P1 or P2 label on the frame of the chosen card."""
        pad_x, pad_y = self.LABEL_PAD
        lab = assets.text(config.PLAYER_LABELS[i], layout.FONT_SMALL,
                          palette.WHITE, outline=palette.INK)
        top = fr.top - self.LABEL_RAISE
        pos = ((fr.left + self.LABEL_INSET_X, top) if i == 0
               else (fr.right - lab.get_width() - self.LABEL_INSET_X, top))
        pygame.draw.rect(surf, config.PLAYER_COLORS[i],
                         (pos[0] - pad_x, pos[1] - pad_y,
                          lab.get_width() + 2 * pad_x,
                          lab.get_height() + 2 * pad_y))
        surf.blit(lab, pos)

    def _footer(self, surf):
        if all(self.ready):
            assets.draw_text(surf, "¡A LA CANCHA!", layout.FONT_TITLE_S,
                             (layout.CENTER_X, self.GO_Y), palette.GOLD,
                             kind="title", outline=palette.INK, shadow=True)
        screens.footer(surf, "Esc: volver  -  Mouse: botones de cada jugador; "
                       "clic izquierdo en una tarjeta elige J1, derecho J2")
        self.back_button.draw(surf, self.t)


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------
class MatchScreen(screens.Screen):
    """Match. The tournament extends it by overriding the hook methods
    (extra_payload, controls, pause_items, on_match_over); the local
    multiplayer mode uses the values of this class."""
    # Buttons of the pause menu (px).
    PAUSE_MENU_CENTER = (layout.CENTER_X, 420)
    PAUSE_MENU_W = 380                 # width of those buttons (px)
    PAUSE_BOX = (560, 380)             # pause box (width, height) in px
    PAUSE_CENTER = (layout.CENTER_X, 390)   # centre of that box (px)
    PAUSE_TITLE_Y = 34                 # title, from the box top (px)
    PAUSE_REASON_Y = 78                # pause reason, from the box top (px)
    PAUSE_TEXT_MARGIN = 20             # px of air beside the reason
    PAUSE_STATUS_Y = 30                # pausing/resuming line, below centre
    MESSAGE_Y = 330                    # preparing and final whistle signs
    MESSAGE_NOTE_Y = 380               # note below the preparing sign (px)
    GOLDEN_GOAL_BANNER = 2.5           # s the golden goal sign is shown
    KICKOFF_BANNER = 0.8               # s the go sign is shown
    GOAL_SHAKE = 0.25                  # s the camera shakes with a goal
    CONFETTI_INSET = 50                # px from the pitch side for confetti
    CONFETTI_HEIGHT = 120              # px above the floor for that confetti
    FINAL_WAIT = 1.8                   # s from final whistle to the result
    WHOOSH_VOLUME = 0.7                # volume of the kick whoosh
    # px/s: at this ball speed a hit sounds (and looks) at its maximum.
    HARD_HIT_SPEED = 1100
    HEADER_MIN_VOLUME = 0.5            # volume of the softest header
    HEADER_MIN_FLASH = 0.5             # flash size of the softest header
    BAR_MIN_VOLUME = 0.4               # volume of the softest crossbar hit
    BOUNCE_MIN_VOLUME = 0.3            # volume of the softest bounce
    DUST_SPEED = 350                   # px/s: a harder bounce raises dust
    TOAST_TIME = 2.6                   # s a power notice lasts
    MAX_TOASTS = 3                     # notices visible at once (newest)
    TOAST_BLINK_TIME = 0.3             # last s in which the notice blinks
    TOAST_BLINK_HZ = 20                # changes per second of that blink
    TOAST_H = 40                       # px: height of a notice
    TOAST_TOP = 170                    # top edge of the first notice (px)
    TOAST_STEP = 46                    # px between notices
    TOAST_PADDING = 28                 # px added to the text (margins, band)
    TOAST_ICON_ROOM = 30               # extra px if the notice has an icon
    TOAST_BAR_W = 6                    # band with the category colour (px)
    TOAST_TEXT_X = 12                  # icon or text, from the left edge
    TOAST_ICON = 28                    # px: icon of the power
    TOAST_ICON_ADVANCE = 34            # px taken by the icon and its gap
    # Test mode box, bottom left (x, y, width, height) in px.
    TEST_PANEL = (8, 646, 600, 68)
    TEST_ICON = 44                     # px: icon of the chosen power
    TEST_ICON_INSET = 6                # icon, from the box corner (px)
    TEST_TEXT_X = 60                   # texts, from the left edge (px)
    TEST_LINE_Y = (8, 32)              # the two lines, from the top edge
    VIEWER = None                      # player of the screen: shared screen

    def __init__(self, app, chars):
        super().__init__(app)
        self.chars = list(chars)
        self.viewer = self.VIEWER
        self.renderer = render.MatchRenderer(app, self.chars)
        self.filter = protocol.StateFilter()
        self.state = None
        self.match_id = None
        self.waiting = None    # "start" | "restart" while not confirmed
        self._init_pause()
        self._init_counters()

    def _init_pause(self):
        # None | "requested" | "paused" | "resuming".
        self.pause_state = None
        self.pause_reason = None
        self.pause_menu = screens.Menu(self.pause_items(),
                                       self.PAUSE_MENU_CENTER,
                                       width=self.PAUSE_MENU_W)
        self.pause_button = screens.BackButton(self.request_pause, "II PAUSA")

    def _init_counters(self):
        self.end_info = None
        self.end_timer = 0.0
        self.toasts = []
        self.last_count = None
        self.ignored_events = 0
        self.test_sel = 0
        self.expected_cid = {}

    # ------------------------------------------------------------ cycle
    def enter(self):
        for cid in set(self.chars):
            # Before starting: no hiccups during the game.
            self.app.sprites.warm(cid)
        self.app.input.capture = True
        self.app.fx.clear()
        self.app.postfx.clear()
        self.app.postfx.viewer = self.viewer
        self._start(protocol.CMD_START)

    def leave(self):
        self.app.input.capture = False
        self.app.input.release_all()
        self.app.audio.crowd(False)

    def _start(self, cmd):
        self.match_id = self.app.next_match_id()
        self.filter.expect(self.match_id)   # old states are ignored from now
        self.state = None
        self.end_info = None
        self.renderer.reset()
        self.app.fx.clear()
        self.toasts.clear()
        cid = self.app.link.send_command(cmd, **self._start_payload())
        self.expected_cid[cid] = cmd
        self.waiting = "start" if cmd == protocol.CMD_START else "restart"

    def _start_payload(self):
        payload = {"match": self.match_id, "characters": self.chars}
        payload.update(self.extra_payload())
        if self.app.options.seed is not None:
            payload["seed"] = self.app.options.seed
        return payload

    def _send(self, cmd, **payload):
        cid = self.app.link.send_command(cmd, **payload)
        if cid is not None:
            self.expected_cid[cid] = cmd
        return cid

    # ------------------------------------------------------------ hooks
    def pause_items(self):
        """Buttons of the pause menu."""
        return [("Continuar", self.resume), ("Reiniciar", self.restart),
                ("Menú principal", self.to_menu)]

    def extra_payload(self):
        """Extra fields of the start command."""
        return {}

    def controls(self, active):
        """Controls of both places (here: two people, one keyboard)."""
        return self.app.input.snapshot(active)

    def on_match_over(self):
        """The final whistle sounded and the wait is over."""
        self.app.switch(ResultScreen(self.app, self.chars, self.end_info,
                                     self.state))

    # ------------------------------------------------------------ commands
    def request_pause(self, reason=protocol.PAUSE_REASON_USER):
        if self.waiting or self.pause_state is not None or self.state is None:
            return
        if self.state["phase"] == protocol.PHASE_FINISHED:
            return
        self.app.input.release_all()
        self.pause_state = "requested"
        self.pause_reason = reason
        self.pause_menu.sel = 0
        self._send(protocol.CMD_PAUSE, reason=reason)

    def resume(self):
        if self.pause_state != "paused":
            return
        self.pause_state = "resuming"
        self._send(protocol.CMD_RESUME)

    def restart(self):
        if self.pause_state != "paused":
            return
        self.pause_state = None
        self._start(protocol.CMD_RESTART)

    def to_menu(self):
        self._send(protocol.CMD_END)
        self.app.switch(screens.MenuScreen(self.app))

    # ------------------------------------------------------------ input
    def handle_event(self, ev):
        self.pause_button.visible = (self.pause_state is None
                                     and self.state is not None)
        if self.pause_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self._escape()
            return
        if (ev.type == pygame.KEYDOWN and self.app.options.test_mode
                and self.pause_state is None):
            self._test_key(ev.key)
        if self.pause_state == "paused":
            self.pause_menu.handle_event(ev, self.app.audio)

    def _escape(self):
        if self.pause_state is None:
            self.request_pause()
        elif self.pause_state == "paused":
            self.app.audio.play("confirm")
            self.resume()

    def _test_key(self, key):
        """Test mode: F5/F6 choose a power; F7-F9 give it; F12 fails."""
        power = config.POWER_IDS[self.test_sel]
        for name, step in TEST_STEPS.items():
            if key == ui_input.key_code(name):
                self.test_sel = (self.test_sel + step) % len(config.POWER_IDS)
                return
        for name, (cmd, mode) in TEST_COMMANDS.items():
            if key == ui_input.key_code(name):
                if mode is None:
                    self._send(cmd)
                else:
                    self._send(cmd, power=power, mode=mode)
                return

    def on_focus_lost(self):
        self.request_pause(protocol.PAUSE_REASON_FOCUS)

    # ------------------------------------------------------------ messages
    def on_link(self, msgs, state):
        for m in msgs:
            if m["type"] == protocol.EV_ACK:
                self._on_ack(m)
            elif m.get("match") != self.match_id:
                self.ignored_events += 1     # event of an older match
            else:
                self._on_event(m)
        if state is not None and self.filter.accept(state):
            self.state = state
            if self.waiting and state["match"] == self.match_id:
                self.waiting = None

    def _on_ack(self, m):
        cmd = self.expected_cid.pop(m["cid"], None)
        if cmd in (protocol.CMD_START, protocol.CMD_RESTART):
            if not m["ok"]:
                self.app.link.fail("La simulación rechazó el inicio del "
                                   "partido: " + m.get("detail", ""))
        elif cmd == protocol.CMD_PAUSE:
            self._pause_acked(m["ok"])
        elif cmd == protocol.CMD_RESUME:
            self.pause_state = None if m["ok"] else "paused"
        elif cmd == protocol.CMD_DEBUG_POWER and not m["ok"]:
            self.toast(f"Prueba rechazada: {m.get('detail', '')}",
                       palette.SOFT_RED)

    def _pause_acked(self, ok):
        if ok:
            self.pause_state = "paused"
            self.app.audio.play("back")
        else:
            self.pause_state = None

    def _on_event(self, m):
        """Dispatches a simulation event to its handler (if any)."""
        self.app.postfx.event(m)
        name = EVENT_HANDLERS.get(m["type"])
        if name is not None:
            getattr(self, name)(m)

    def _golden_goal(self, m):
        del m  # Unused.
        self.renderer.golden_flash = self.GOLDEN_GOAL_BANNER
        self.app.audio.play("whistle")

    def _kickoff(self, m):
        del m  # Unused.
        self.renderer.kickoff_flash = self.KICKOFF_BANNER
        self.app.audio.play("go")
        self.app.audio.play("whistle")

    def _goal(self, m):
        self.renderer.goal_banner = (config.MatchRules.GOAL_CELEBRATION, m)
        gx = (self.CONFETTI_INSET if m["side"] == 0
              else config.Arena.WIDTH - self.CONFETTI_INSET)
        self.app.fx.confetti(gx, config.Arena.FLOOR_Y - self.CONFETTI_HEIGHT,
                             [config.PLAYER_COLORS[m["scorer"]], palette.WHITE,
                              palette.GOLD])
        self.app.fx.shake = self.GOAL_SHAKE
        self.app.audio.play("goal")

    def _match_end(self, m):
        self.end_info = m
        self.end_timer = self.FINAL_WAIT
        self.app.audio.play("whistle_end")

    def _paused(self, m):
        self.pause_state = "paused"
        self.pause_reason = m.get("reason")
        self.app.input.release_all()

    def _power(self, m):
        pdef = config.POWERS_BY_ID[m["power"]]
        col = config.CATEGORY_COLORS[pdef.category]
        self.app.fx.sparkle(m["x"], m["y"], col)
        self.app.audio.play(POWER_SOUNDS.get(pdef.category, "power_good"))
        self.toast(self._power_text(m, pdef), col, m["power"])

    def _power_text(self, m, pdef):
        """Who took the power and on whom it acts."""
        name = self.renderer.who
        who = name(m["receptor"]) if m["receptor"] is not None else "Partido"
        names = (name(0), name(1))
        targets = ", ".join(TARGET_NAMES[x].format(*names)
                            if x in TARGET_NAMES else x for x in m["targets"])
        return f"{who}: {pdef.name}" + (f"  (sobre {targets})"
                                        if targets else "")

    def _pickup_expired(self, m):
        self.app.fx.vanish(m["x"], m["y"])

    def _bomb_armed(self, m):
        del m  # Unused.
        self.app.audio.play("bomb_tick")

    def _kick(self, m):
        del m  # Unused.
        self.app.audio.play("whoosh", self.WHOOSH_VOLUME)

    def _power_spawn(self, m):
        pdef = config.POWERS_BY_ID[m["power"]]
        self.app.fx.power_spawn(m["x"], m["y"],
                                config.CATEGORY_COLORS[pdef.category])
        self.app.audio.play("spawn")

    def _explosion(self, m):
        self.app.fx.explosion(m["x"], m["y"], m["radius"])
        self.app.audio.play("explosion")

    def _kick_blocked(self, m):
        self.app.audio.play("blocked")
        if self.state:
            p = self.state["players"][m["player"]]
            self.app.fx.kick_blocked(p["x"], p["y"], p["facing"])

    def _touch(self, m):
        """Ball touch: sound and flash grow with the hit strength."""
        kind, sp = m["kind"], m.get("speed", 0)
        k = min(1.0, sp / self.HARD_HIT_SPEED)   # hit strength, from 0 to 1
        if kind == "kick":
            self.app.audio.play("kick")
            self.app.fx.kick_impact(m["x"], m["y"])
        elif kind in ("head", "bar"):
            self._hit(m, kind, k)
        else:
            self.app.audio.play("bounce",
                                by_strength(self.BOUNCE_MIN_VOLUME, k))
            if kind == "floor" and sp > self.DUST_SPEED:
                self.app.fx.dust(m["x"], config.Arena.FLOOR_Y, k)

    def _hit(self, m, kind, k):
        """Header or crossbar hit."""
        if kind == "head":
            self.app.audio.play("header",
                                by_strength(self.HEADER_MIN_VOLUME, k))
            self.app.fx.impact(m["x"], m["y"],
                               by_strength(self.HEADER_MIN_FLASH, k))
        else:
            self.app.audio.play("post", by_strength(self.BAR_MIN_VOLUME, k))
            self.app.fx.impact(m["x"], m["y"], k)

    def toast(self, txt, color, power=None):
        """Short notice below the scoreboard (the newest ones stay)."""
        self.toasts.append([txt, color, self.TOAST_TIME, power])
        self.toasts = self.toasts[-self.MAX_TOASTS:]

    # ------------------------------------------------------------ cycle
    def update(self, dt):
        super().update(dt)
        self.tick_effects(dt)
        self.pause_menu.enabled = self.pause_state == "paused"
        self.pause_menu.update(dt)
        self._send_controls()
        self.match_sounds_and_snow()
        if self.end_info is not None:
            self.end_timer -= dt
            if self.end_timer <= 0:
                self.on_match_over()

    def _send_controls(self):
        """Controls travel every frame (they are also the watchdog
        heartbeat); the crowd sounds while the match runs."""
        st = self.state
        active = (st is not None and self.pause_state is None
                  and not st["paused"]
                  and st["phase"] == protocol.PHASE_PLAYING)
        self.app.link.send_input(self.controls(active))
        self.app.audio.crowd(st is not None and not st["paused"]
                             and self.pause_state is None)

    def tick_effects(self, dt):
        """Renderer, effects and notices move forward dt seconds."""
        self.renderer.update(dt)
        self.app.fx.update(dt)
        for tst in self.toasts:
            tst[2] -= dt
        self.toasts = [t for t in self.toasts if t[2] > 0]

    def match_sounds_and_snow(self):
        """Countdown beeps and snow over frozen players."""
        st = self.state
        if st and st["phase"] == protocol.PHASE_COUNTDOWN and not st["paused"]:
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

    # ------------------------------------------------------------ drawing
    def draw(self, surf):
        st = self.state
        if st is None:
            self._draw_waiting(surf)
            return
        self.draw_match(surf, st, st)
        self._draw_end_and_test(surf)
        self.pause_button.visible = (self.pause_state is None
                                     and self.end_info is None)
        self.pause_button.draw(surf, self.t)
        if self.pause_state is not None:
            self._draw_pause(surf)

    def _draw_end_and_test(self, surf):
        if self.end_info is not None:
            screens.title(surf, "¡FINAL DEL PARTIDO!",
                          (layout.CENTER_X, self.MESSAGE_Y),
                          layout.FONT_TITLE_L, palette.WHITE)
        if self.app.options.test_mode:
            self._draw_test_panel(surf)

    def draw_match(self, surf, view, st):
        """World (from 'view'), effects, scoreboard, signs and notices."""
        off = self.app.fx.shake_offset()
        world = self.app.postfx.begin(surf, st)
        self.renderer.draw_world(world, view, off)
        self.app.fx.draw(world, off)
        self.app.postfx.finish(surf, self.app.last_dt)
        self.renderer.draw_hud(surf, st)
        self.renderer.draw_center_messages(surf, st)
        self._draw_toasts(surf)

    def _draw_waiting(self, surf):
        surf.blit(self.app.background, (0, 0))
        screens.dim(surf, layout.VEIL_OVERLAY)
        msg = ("Preparando partido..." if self.waiting != "restart"
               else "Reiniciando partido...")
        screens.title(surf, msg, (layout.CENTER_X, self.MESSAGE_Y),
                      layout.FONT_LARGE, palette.WHITE)
        assets.draw_text(surf, "Esperando la confirmación de la simulación",
                         layout.FONT_SMALL,
                         (layout.CENTER_X, self.MESSAGE_NOTE_Y), palette.INK,
                         outline=palette.WHITE)

    def _draw_toasts(self, surf):
        for k, (txt, col, left, power) in enumerate(self.toasts):
            blinking = (left < self.TOAST_BLINK_TIME
                        and int(left * self.TOAST_BLINK_HZ) % 2)
            if not blinking:           # retro blink when it goes away
                self._draw_toast(surf, k, txt, col, power)

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def _draw_toast(self, surf, k, txt, col, power):
        img = assets.text(txt, layout.FONT_SMALL, palette.INK, outline=None)
        w = (img.get_width() + self.TOAST_PADDING
             + (self.TOAST_ICON_ROOM if power else 0))
        r = pygame.Rect(0, 0, w, self.TOAST_H)
        r.midtop = (layout.CENTER_X, self.TOAST_TOP + k * self.TOAST_STEP)
        inner = retro.bevel_box(surf, r, palette.CREAM)
        pygame.draw.rect(surf, col, (inner.left, inner.top, self.TOAST_BAR_W,
                                     inner.height))
        x = inner.left + self.TOAST_TEXT_X
        if power:
            x = self._toast_icon(surf, power, x, r.centery)
        surf.blit(img, (x, r.centery - img.get_height() // 2))

    def _toast_icon(self, surf, power, x, centery):
        """Draws the power icon; returns where the text starts."""
        surf.blit(icons.power_icon(power, self.TOAST_ICON),
                  (x, centery - self.TOAST_ICON // 2))
        return x + self.TOAST_ICON_ADVANCE

    def _draw_test_panel(self, surf):
        power = config.POWER_IDS[self.test_sel]
        inner = retro.bevel_box(surf, pygame.Rect(self.TEST_PANEL),
                                palette.GOLD)
        surf.blit(icons.power_icon(power, self.TEST_ICON),
                  (inner.left + self.TEST_ICON_INSET,
                   inner.top + self.TEST_ICON_INSET))
        self._test_lines(surf, inner, config.POWERS_BY_ID[power].name)

    def _test_lines(self, surf, inner, power_name):
        first, second = self.TEST_LINE_Y
        x = inner.left + self.TEST_TEXT_X
        assets.draw_text(surf, f"MODO PRUEBA - {power_name}",
                         layout.FONT_SMALL, (x, inner.top + first),
                         palette.INK, anchor="topleft", outline=None)
        assets.draw_text(surf, "F5/F6 elegir  F7 generar  F8 dar al de la "
                         "izq.  F9 al de la der.  F12 fallo",
                         layout.FONT_SMALL, (x, inner.top + second),
                         palette.INK, anchor="topleft", outline=None)

    def _draw_pause(self, surf):
        screens.dim(surf, layout.VEIL_OVERLAY)
        r = pygame.Rect((0, 0), self.PAUSE_BOX)
        r.center = self.PAUSE_CENTER
        inner = screens.panel(surf, r)
        screens.title(surf, "PAUSA",
                      (layout.CENTER_X, inner.top + self.PAUSE_TITLE_Y),
                      layout.FONT_TITLE)
        self._draw_pause_reason(surf, inner)
        if self.pause_state == "paused":
            self.pause_menu.draw(surf)
        else:
            self._draw_pause_status(surf, r.centery)

    def _draw_pause_status(self, surf, centery):
        assets.draw_text(surf, PAUSE_STATUS.get(self.pause_state, ""),
                         layout.FONT_SMALL,
                         (layout.CENTER_X, centery + self.PAUSE_STATUS_Y),
                         palette.INK, outline=None)

    def _draw_pause_reason(self, surf, inner):
        reason = PAUSE_REASONS.get(self.pause_reason, DEFAULT_PAUSE_REASON)
        lines = assets.wrap(reason, layout.FONT_SMALL,
                            inner.width - self.PAUSE_TEXT_MARGIN)
        for k, ln in enumerate(lines):
            assets.draw_text(surf, ln, layout.FONT_SMALL,
                             (layout.CENTER_X, inner.top + self.PAUSE_REASON_Y
                              + k * layout.TEXT_LINE_H), palette.INK,
                             outline=None)

    def debug_info(self):
        st = self.state or {}
        f = self.filter
        return {
            "match": self.match_id, "phase": st.get("phase", "—"),
            "paused": st.get("paused"), "seq": st.get("seq", "—"),
            "tick": st.get("tick", "—"), "clock": st.get("clock"),
            "filtered": (f"{f.rejected_old_match} de otro partido, "
                         f"{f.rejected_stale} viejos"),
            "sim_dropped": st.get("dropped_states", 0),
            "cosmetic_dropped": st.get("dropped_cosmetic", 0),
            "ignored_events": self.ignored_events,
            "ui_pause": self.pause_state or "—",
        }


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
class ResultScreen(screens.Screen):
    """Winner (or draw), the score and what to do next."""
    # Rematch, choose characters and main menu buttons (px).
    MENU_CENTER = (layout.CENTER_X, 560)
    MENU_W = 380                       # width of those buttons (px)
    MENU_BUTTON_H = 52                 # height (lower than the menu: three)
    MENU_GAP = 10                      # px between those buttons
    MENU_FONT = 26                     # font size of those buttons
    PLAYER_X = (330, 950)              # x of each player (px)
    FEET_Y = 470                       # y of the players feet (px)
    NAME_Y = 500                       # name of each player (px)
    WINNER_SCALE = 2.4                 # the winner looks bigger...
    LOSER_SCALE = 1.8                  # ...than the loser (or both, if draw)
    CONFETTI_EVERY = 1.4               # s between confetti over the winner
    CONFETTI_Y = 380                   # height that confetti comes from (px)
    HEADLINE_Y = 80                    # winner or draw sign (px)
    SCORE_CENTER = (layout.CENTER_X, 290)   # board with the result (px)
    SCORE_W = 300                      # width of the board (px)

    def __init__(self, app, chars, end_info, last_state):
        super().__init__(app)
        del last_state  # Unused.
        self.chars = chars
        self.score = end_info["score"]
        self.winner = end_info["winner"]
        self.menu = screens.Menu(
            [("Revancha", self.rematch), ("Elegir personajes", self.choose),
             ("Menú principal", self.to_menu)], self.MENU_CENTER,
            width=self.MENU_W, height=self.MENU_BUTTON_H, gap=self.MENU_GAP,
            size=self.MENU_FONT)
        self.confetti_t = 0.0

    def enter(self):
        self.app.audio.crowd(False)
        self.app.fx.clear()

    def name(self, i):
        """Character name; if both chose the same one, the side is added."""
        n = characters.short_name(characters.CHARACTERS_BY_ID[self.chars[i]])
        if self.chars[0] == self.chars[1]:
            n += " (izq.)" if i == 0 else " (der.)"
        return n

    def rematch(self):
        self.app.switch(MatchScreen(self.app, self.chars))

    def choose(self):
        self.app.switch(SelectScreen(self.app, preselect=self.chars))

    def to_menu(self):
        self.app.switch(screens.MenuScreen(self.app))

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
            self.app.fx.confetti(x, self.CONFETTI_Y,
                                 [config.PLAYER_COLORS[self.winner],
                                  palette.WHITE, palette.GOLD])

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        screens.dim(surf, layout.VEIL_RESULT)
        for i in (0, 1):
            self._player(surf, i)
        self.app.fx.draw(surf)
        self._headline(surf)
        screens.scoreboard(surf, self.SCORE_CENTER, self.SCORE_W,
                           f"{self.score[0]}-{self.score[1]}")
        self.menu.draw(surf)
        screens.footer(surf, "Revancha: mismos personajes  -  Elegir "
                       "personajes: volver a la selección")

    def _headline(self, surf):
        if self.winner is None:
            head, col = "¡EMPATE!", palette.WHITE
        else:
            head = f"¡GANÓ {self.name(self.winner).upper()}!"
            col = config.PLAYER_COLORS[self.winner]
        screens.title(surf, head, (layout.CENTER_X, self.HEADLINE_Y),
                      layout.FONT_TITLE_L, col)

    def _player(self, surf, i):
        x = self.PLAYER_X[i]
        win = self.winner == i
        ang, bob = (sprites.celebrate_pose(self.t) if win
                    else sprites.idle_pose(self.t, i))
        img, (fx, fy) = self.app.sprites.player(
            self.chars[i], FACING[i], ang, bob, config.PLAYER_COLORS[i],
            False, self.WINNER_SCALE if win else self.LOSER_SCALE)
        surf.blit(img, (x - fx, self.FEET_Y - fy))
        assets.draw_text(surf, self.name(i), layout.FONT_TEXT,
                         (x, self.NAME_Y), config.PLAYER_COLORS[i],
                         outline=palette.INK)
