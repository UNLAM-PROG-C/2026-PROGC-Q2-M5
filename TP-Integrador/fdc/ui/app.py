"""Main process: window, events, screens, drawing and sound.

All the pygame event handling happens in THIS thread (the one that created
the window), as the pygame.event documentation says. The interface never
blocks waiting for the simulation or the network: every frame it reads
whatever arrived (get_nowait) and draws the last valid state. The rhythm is
set by FrameLimiter, which sleeps between frames (no busy waiting).

In the browser (pygbag) there is the whole game, but no processes: the
local modes simulate inside the page (InlineLink, fdc/sim/inline.py, with
the same simulation core), the online mode uses the room process on the
server, and the loop is asynchronous: every frame gives the control back to
the browser.

State pattern: App holds the current screen and every screen decides the
next one with app.switch().
"""
import asyncio
import collections
import logging
import os
import sys
import time

import pygame

from fdc import config
from fdc import profile as profiles
from fdc.online import client
from fdc.sim import inline
from fdc.ui import assets
from fdc.ui import audio
from fdc.ui import browser
from fdc.ui import fx
from fdc.ui import input as ui_input
from fdc.ui import layout
from fdc.ui import online_screens
from fdc.ui import palette
from fdc.ui import pixelfont
from fdc.ui import profile_screen
from fdc.ui import screens
from fdc.ui import sprites
from fdc.ui import stadium

log = logging.getLogger("fdc.ui")

FPS_SAMPLES = 60            # frames averaged to show the FPS
EPSILON = 1e-6              # avoids dividing by zero when averaging
# s: a very late frame counts at most this much (no huge jumps).
MAX_FRAME_DT = 0.1
ICON_SIZE = 64              # px: window icon (the game ball)
ICON_BALL_RADIUS = 28       # px: radius of the ball drawn in the icon
ICON_BALL_ANGLE = 20        # degrees: turn of the icon ball (patches show)
# Debug panel (F3).
DEBUG_TEXT_SCALE = 2        # scale of the pixel art font in the panel
DEBUG_LINE_H = 24           # px between lines
DEBUG_PADDING = 24          # px of total horizontal margin of the text
DEBUG_EXTRA_H = 14          # px of extra height of the box
DEBUG_MARGIN = 8            # px between the box and the screen edge
DEBUG_TEXT_X = 20           # px: x of the text
DEBUG_TEXT_TOP = 2          # px: gap of the first line
DEBUG_ALPHA = 225           # opacity of the panel background
DEBUG_BORDER = 2            # px: thickness of the golden frame
LOG_FORMAT = ("%(asctime)s [%(processName)s pid=%(process)d] %(levelname)s "
              "%(name)s: %(message)s")
LOG_FILE = "fdc.log"
GLOBAL_KEYS = (config.DEBUG_PANEL_KEY, config.FULLSCREEN_KEY, config.MUTE_KEY)


def _yes(v):
    return "sí" if v else "no"


class FrameLimiter:
    """Limits to N frames per second by SLEEPING until the frame deadline.

    It is used instead of pygame.time.Clock.tick() because on macOS that
    method oversleeps (about 47 FPS when asking for 60). time.sleep frees
    the CPU: it is not a busy wait.
    """

    def __init__(self, fps, sleep=True):
        # In the browser the rhythm is set by the browser itself.
        self.sleep = sleep
        self.period = 1.0 / fps
        self.deadline = time.perf_counter()
        self.last = self.deadline
        self.samples = collections.deque(maxlen=FPS_SAMPLES)

    def tick(self):
        """Sleeps until the next frame; returns the real dt (s)."""
        self.deadline += self.period
        now = time.perf_counter()
        remaining = self.deadline - now
        if remaining > 0 and self.sleep:
            time.sleep(remaining)
        else:
            self.deadline = now        # late frame: do not try to catch up
        now = time.perf_counter()
        dt = now - self.last
        self.last = now
        self.samples.append(dt)
        return dt

    def get_fps(self):
        if not self.samples:
            return 0.0
        return len(self.samples) / max(EPSILON, sum(self.samples))


class App:
    """The window, the current screen and the shared resources."""

    def __init__(self, options):
        self.options = options
        # Browser version (pygbag).
        self.web = bool(getattr(options, "web", False))
        self.screen = self._open_window()
        self.clock = FrameLimiter(config.UI_FPS, sleep=not self.web)
        if self.web:
            # Esc, F3, Tab and the arrows do not fire browser actions.
            browser.install_key_guard()
        self._load_resources()
        self._init_state()
        self._start_simulation()

    def _start_simulation(self):
        """The simulation process starts BEFORE the menu is shown; the boot
        screen waits for its READY without blocking the window. In the
        browser there are no processes: the local simulation runs in the
        page."""
        self.link = self._create_link()
        self.link.start()
        self.current = screens.BootScreen(self)
        self.current.enter()

    def _open_window(self):
        pygame.mixer.pre_init(audio.AUDIO_RATE, audio.AUDIO_BITS,
                              audio.AUDIO_CHANNELS, audio.AUDIO_BUFFER)
        pygame.init()
        pygame.display.set_caption(config.GAME_NAME)
        if self.web:
            flags = 0                  # the browser scales the canvas
        else:
            # Scales keeping the aspect ratio.
            flags = pygame.SCALED | pygame.RESIZABLE
            if self.options.fullscreen:
                flags |= pygame.FULLSCREEN
        return pygame.display.set_mode(
            (config.LOGICAL_WIDTH, config.LOGICAL_HEIGHT), flags)

    def _load_resources(self):
        self.audio = audio.Audio(enabled=not self.options.no_audio)
        self.sprites = sprites.CharacterSprites()
        self.ball_sprite = stadium.BallSprite()
        self.background = stadium.build_background()
        self._set_icon()
        self.fx = fx.Effects()
        self.input = ui_input.InputTracker()

    def _init_state(self):
        options = self.options
        self.last_characters = None
        self.tournament = None          # tournament in progress (memory only)
        self.match_counter = 0
        self.show_debug = options.debug_panel
        self.running = True
        self.keys = {k: ui_input.key_code(k) for k in GLOBAL_KEYS}
        self.first_frame_shown = False
        self._init_online()
        # Player name: chosen once at the start, valid for every mode.
        self.profile_path = getattr(options, "profile_path", None)
        self.profile = profiles.load(self.profile_path)

    def _init_online(self):
        self.net = None             # online server connection (when online)
        self.server_url = getattr(self.options, "server_url", None)
        self.last_online_char = None

    def _create_link(self):
        options = self.options
        duration = getattr(options, "duration", None)
        if self.web:
            return inline.InlineLink(test_mode=options.test_mode,
                                     seed=options.seed, duration=duration)
        # pylint: disable-next=import-outside-toplevel
        from fdc import ipc  # Here: the browser has no multiprocessing.
        return ipc.SimLink(test_mode=options.test_mode, seed=options.seed,
                           duration=duration)

    def _set_icon(self):
        icon = pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)
        center = ICON_SIZE // 2
        self.ball_sprite.draw(icon, center, center, ICON_BALL_RADIUS,
                              ICON_BALL_ANGLE)
        pygame.display.set_icon(icon)

    # ------------------------------------------------------------ navigation
    def switch(self, screen):
        """Changes the current screen (State pattern)."""
        self.current.leave()
        self.current = screen
        screen.enter()

    def home(self):
        """The main menu (the same on desktop and in the browser)."""
        return screens.MenuScreen(self)

    def first_screen(self):
        """After the boot: the name (if not chosen yet) and then the menu.
        If the browser reloaded in the middle of the online mode, back to
        the room."""
        if self.profile is None:
            return profile_screen.ProfileScreen(self, first_run=True)
        if self.web and client.saved_session():
            return online_screens.OnlineHomeScreen(self)
        return self.home()

    def set_profile(self, profile):
        self.profile = profile
        profiles.save(profile, self.profile_path)
        self.close_online()     # online comes back with the new name

    def online(self):
        """Network client (created the first time the online mode opens)."""
        if self.net is None:
            self.net = client.NetClient(self.server_url)
        return self.net

    def close_online(self):
        if self.net is not None:
            self.net.close()
            self.net = None

    def next_match_id(self):
        self.match_counter += 1
        return self.match_counter

    def quit(self):
        self.running = False

    def restart_simulation(self):
        """After an error: orderly shutdown of the old process and a new
        one."""
        self.link.restart()
        self.switch(screens.BootScreen(self))

    # ------------------------------------------------------------ loop
    def frame(self):
        """One frame: events -> SIM messages -> health -> screen logic ->
        drawing."""
        dt = min(self.clock.tick(), MAX_FRAME_DT)
        for ev in pygame.event.get():
            self.handle_event(ev)
            if not self.running:
                return
        self._poll_simulation()
        if self.net is not None:
            # One at a time: if a message changes the screen, the next ones
            # already go to the new screen (none is lost).
            for msg in self.net.poll():
                self.current.on_net(msg)
        self.current.update(dt)
        self._draw()

    def _poll_simulation(self):
        if self.link is None:
            return
        msgs, state = self.link.poll()
        self.current.on_link(msgs, state)
        err = self.link.check_health()
        if err and not isinstance(self.current, screens.ErrorScreen):
            self.switch(screens.ErrorScreen(self, err, self.link.error_detail))

    def _draw(self):
        self.current.draw(self.screen)
        if self.show_debug:
            self.draw_debug(self.screen)
        pygame.display.flip()
        if self.web and not self.first_frame_shown:
            self.first_frame_shown = True
            browser.hide_loading_screen()

    def run(self):
        try:
            while self.running:
                self.frame()
        except KeyboardInterrupt:
            log.info("interrupted from the terminal: orderly shutdown")
        finally:
            self.shutdown()

    async def run_async(self):
        """Browser loop: every frame gives the control back (no sleep)."""
        try:
            while self.running:
                self.frame()
                await asyncio.sleep(0)
        finally:
            self.shutdown()

    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.running = False          # close from any screen
            return
        if ev.type in (pygame.WINDOWFOCUSLOST, pygame.WINDOWMINIMIZED):
            # No player keeps walking with a stuck key.
            self.input.release_all()
            self.current.on_focus_lost()
            return
        if ev.type == pygame.KEYDOWN and self._global_key(ev.key):
            return
        self.input.handle_event(ev)
        self.current.handle_event(ev)

    def _global_key(self, key):
        """F3, F11 and M work on every screen. True if it was one."""
        if key == self.keys[config.DEBUG_PANEL_KEY]:
            self.show_debug = not self.show_debug
        elif key == self.keys[config.FULLSCREEN_KEY]:
            if not self.web:
                pygame.display.toggle_fullscreen()
        elif key == self.keys[config.MUTE_KEY]:
            self.audio.toggle_mute()
        else:
            return False
        return True

    def shutdown(self):
        try:
            self.audio.crowd(False)
        except pygame.error:
            pass
        self.close_online()
        if self.link is not None:
            report = self.link.stop()
            log.info("shutdown complete: %s", report)
        assets.clear_caches()
        pygame.quit()

    # ------------------------------------------------------------ F3 panel
    def draw_debug(self, surf):
        """F3 panel: processes, link, network and frame data."""
        si = self.current.debug_info()
        lines = [("PANEL DE DEPURACIÓN (F3)", palette.GOLD)]
        if self.link is not None:
            lines += self._process_lines()
        lines += _screen_lines(type(self.current).__name__, si)
        if self.link is not None:
            lines += _link_lines(self.link.debug_lines())
        if self.net is not None:
            lines += _net_lines(self.net)
        lines += self._frame_lines(si)
        _draw_panel(surf, lines)

    def _process_lines(self):
        if getattr(self.link, "inline", False):
            return [("Navegador: sin procesos; la simulación local corre en "
                     "la misma página (el online, en el servidor)", None)]
        li = self.link.debug_lines()
        info = self.link.ready_info or {}
        state = "viva" if li["alive"] else "detenida"
        return [(f"UI pid {os.getpid()}  |  SIM pid {li['sim_pid']} "
                 f"({state}), pygame en SIM: "
                 f"{_yes(info.get('pygame_loaded'))}", None)]

    def _frame_lines(self, si):
        return [
            (f"Estados ignorados: {si.get('filtered', '-')}", None),
            (f"SIM reemplazó {si.get('sim_dropped', 0)} estados  |  eventos "
             f"cosméticos perdidos {si.get('cosmetic_dropped', 0)}  |  "
             f"eventos viejos {si.get('ignored_events', 0)}", None),
            (f"FPS UI {screens.fps_value(self.clock):.0f}  |  física "
             f"{config.PHYSICS_HZ} Hz  |  prueba: "
             f"{_yes(self.options.test_mode)}  |  semilla "
             f"{self.options.seed}", None),
        ]


def _screen_lines(name, si):
    clock = f"{si['clock']:.2f} s" if si.get("clock") is not None else "-"
    return [
        (f"Pantalla {name}  |  partido #{si.get('match', '-')}  |  "
         f"fase {si.get('phase', '-')}", None),
        (f"Pausa SIM: {_yes(si.get('paused'))}  |  pausa UI: "
         f"{si.get('ui_pause', '-')}  |  reloj {clock}", None),
        (f"Actualización seq {si.get('seq', '-')}  |  tick "
         f"{si.get('tick', '-')}", None),
    ]


def _link_lines(li):
    return [
        (f"Último confirmado: {li['confirmed']}", None),
        (f"Órdenes sin confirmar: {li['pending']}  |  controles: "
         f"{li['inputs']}", None),
        (f"Recibidos: {li['received']}", None),
    ]


def _net_lines(net):
    ni = net.debug_lines()
    lines = [
        (f"Online: {ni['status']} como {ni['user']}  |  latencia "
         f"{ni['rtt']}  |  {ni['url']}", None),
        (f"Mensajes: {ni['traffic']}", None),
    ]
    if net.room_info:   # the room seen from the server (once per second)
        lines += _room_lines(net.room_info)
    return lines


def _room_lines(ri):
    ack = f"{ri['ack_ms']:.1f} ms" if ri.get("ack_ms") is not None else "-"
    alive = "vivo" if ri["sim_alive"] else "detenido"
    return [
        (f"Servidor pid {ri['server_pid']}  |  sala {ri['room']}: proceso "
         f"de simulación pid {ri['sim_pid']} ({alive})  |  partido "
         f"#{ri['match']}", palette.GOLD),
        (f"La sala manda {ri['states_per_s']:.0f} estados/s  |  recibe "
         f"{ri['inputs_per_s']:.0f} fotos de controles/s  |  último ACK "
         f"{ack}  |  sin confirmar {ri['pending_acks']}  |  pausa: "
         f"{', '.join(ri['hold']) or '-'}", None),
    ]


def _draw_panel(surf, lines):
    """Translucent box at the bottom left with the F3 lines."""
    w = (max(pixelfont.text_width(t, DEBUG_TEXT_SCALE) for t, _ in lines)
         + DEBUG_PADDING)
    h = len(lines) * DEBUG_LINE_H + DEBUG_EXTRA_H
    top = config.LOGICAL_HEIGHT - h - DEBUG_MARGIN
    box = pygame.Surface((w, h), pygame.SRCALPHA)
    box.fill((*palette.INK, DEBUG_ALPHA))
    surf.blit(box, (DEBUG_MARGIN, top))
    pygame.draw.rect(surf, palette.GOLD, (DEBUG_MARGIN, top, w, h),
                     DEBUG_BORDER)
    _panel_text(surf, lines, top)


def _panel_text(surf, lines, top):
    for k, (t, col) in enumerate(lines):
        assets.draw_text(surf, t, layout.FONT_SMALL,
                         (DEBUG_TEXT_X, top + DEBUG_MARGIN + DEBUG_TEXT_TOP
                          + k * DEBUG_LINE_H), col or palette.CREAM,
                         anchor="topleft", outline=None)


def run_app(options):
    """Creates the window and runs the game until it is closed."""
    app = App(options)
    app.run()
    return 0


def setup_logging():
    """Log to the terminal and to logs/fdc.log."""
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        handlers.append(logging.FileHandler(
            os.path.join(config.LOG_DIR, LOG_FILE), mode="w",
            encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT,
                        handlers=handlers, force=True)
