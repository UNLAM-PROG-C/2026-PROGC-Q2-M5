"""Automatic demo: plays a match without a window and measures the effects.

`tools/demo_gpu.py` calls `run` to compare the loop with the effects on and
off. `DemoDirector` and `DemoScreen` (F7) are the demo for the university:
ten segments of ten seconds each, one effect at a time, with a forced seed and
a CSV of the real frame times. `tools/run_demo.py` runs it headless.
"""
import os
import time

import pygame

import main as main_module
from fdc import bot
from fdc import config
from fdc import protocol
from fdc.sim import match as sim_match   # noqa: F401  (imported by the link)
from fdc.gpu import backend
from fdc.gpu import metrics as gpu_metrics
from fdc.ui import app as ui_app
from fdc.ui import assets
from fdc.ui import layout
from fdc.ui import match_screens
from fdc.ui import palette

DEFAULT_FRAMES = 600      # 10 s at 60 fps
SPEED = 60.0              # frames per second: the simulated time
MS_PER_S = 1000.0         # milliseconds in a second
WAIT_SECONDS = 15.0       # s until the simulation sends the first state
WAIT_STEP = 0.01          # s between frames while waiting
G = config.Gpu
# --- F7: demo for the university ------------------------------------------
SEGMENTS = (
    ("sin efectos", None),
    ("hielo", "ice"),
    ("apagón", "blackout"),
    ("confusión", "confusion"),
    ("fuego", "fire"),
    ("noche + autoexposición", "night"),
    ("onda expansiva + estela", "shock"),
    ("repetición con look de TV vieja", "replay"),
    ("VAR con zoom y cartel", "var"),
    ("mapa de calor del partido", "heat"),
)
SEGMENT_COUNT = len(SEGMENTS)
AVATARS = 2               # characters of the demo (the first two)
LABEL_Y = 96              # px: top of the segment label
LABEL_NOTE_Y = 34         # px: gap between the label and its note
HINT_Y = 26               # px: bottom hint line
BAR_H = 34                # px: height of the bottom bar
BAR_ALPHA = 170           # opacity of that bar (0-255)
ICE_FORCED = 1.0          # ice strength of its segment (0-1)
CONFUSION_FORCED = 1.0    # confusion strength of its segment (0-1)
TRAIL_FORCED = 1.0        # trail strength of its segment (0-1)
FIRE_RADIUS = 170.0       # px of the hot air of the fire segment
HEAT_CHANNEL = 0          # the demo shows the heat of the ball
BOT_LEVEL = G.DEMO_BOT_LEVEL
ONE_SECOND = 1.0          # seconds in a second (demo clocks)
FIRST_SEGMENT = 0         # index of the first segment



def run(frames=DEFAULT_FRAMES, argv=()):
    """Plays `frames` frames headless; returns the metrics of the chain."""
    options = main_module.parse_args(list(argv) + ["--no-audio"])
    main_module.apply_gpu_options(options)
    game = ui_app.App(options)
    try:
        _play(game, frames)          # warm up: boot, first state
        start = pygame.time.get_ticks()
        done = _play(game, frames)
        elapsed = pygame.time.get_ticks() - start
        return _summary(game, done, elapsed)
    finally:
        game.shutdown()


def headless():
    """Puts SDL in dummy mode (no window, no sound card needed)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def _play(game, frames):
    """Starts a match between the first two characters and runs the loop.

    The first call also waits (a few frames) until the simulation sends its
    first state; the second one only counts frames.
    """
    game.clock.sleep = False        # measure the real cost of the frame
    screen = game.current
    if not isinstance(screen, match_screens.MatchScreen):
        screen = match_screens.MatchScreen(game, config.CHARACTER_IDS[:2])
        game.switch(screen)
    _wait_state(game, screen)
    done = 0
    for _ in range(frames):
        game.frame()
        done += 1
        if not game.running:
            break
    return done


def _wait_state(game, screen):
    """Frames until the match state arrives (at most WAIT_SECONDS)."""
    limit = time.perf_counter() + WAIT_SECONDS
    while screen.state is None and time.perf_counter() < limit:
        game.frame()
        time.sleep(WAIT_STEP)


def _summary(game, frames, elapsed):
    """Numbers of the run: mode, quality, per stage and total."""
    data = game.postfx.summary()
    data["frames"] = frames
    data["ms_frame"] = elapsed / frames if frames else 0.0
    data["fps_loop"] = frames * MS_PER_S / elapsed if elapsed else 0.0
    data["surface"] = f"{game.screen.get_width()}x{game.screen.get_height()}"
    return data


def compare(frames=DEFAULT_FRAMES):
    """Runs the same demo with the effects on and off."""
    headless()
    pygame.init()
    with_effects = run(frames)
    without = run(frames, ["--no-gpu"])
    return {"gpu": with_effects, "sin_efectos": without}


class DemoDirector:
    """Clock of the demo: which of the ten segments is on, and when it ends.

    The time comes from outside (`step(dt, frame_dt)`), so the demo can run
    in real time or with a fixed 1/60 s clock for repeated captures.
    """

    def __init__(self, seconds=None, frame_clock=False):
        self.seconds = seconds or G.DEMO_SECONDS
        self.frame_clock = frame_clock
        self.index = FIRST_SEGMENT
        self.elapsed = 0.0
        self.done = False

    def step(self, dt, frame_dt):
        """Adds one frame; returns the segment that has to be drawn."""
        if self.done:
            return self.index
        self.elapsed += frame_dt if self.frame_clock else dt
        while self.elapsed >= self.seconds and not self.done:
            self._next()
        return self.index

    def _next(self):
        """Passes to the next segment (or finishes after the last one)."""
        self.elapsed -= self.seconds
        if self.index + 1 >= SEGMENT_COUNT:
            self.done = True
            self.elapsed = 0.0
            return
        self.index += 1

    def name(self):
        """Name of the segment ("hielo", "VAR con zoom y cartel"...)."""
        return SEGMENTS[self.index][0]

    def kind(self):
        """Effect of the segment ('ice', 'var'...) or None for the first."""
        return SEGMENTS[self.index][1]

    def label(self):
        """Big text for the projector: 'EFECTO 3/10: APAGON'."""
        return (f"EFECTO {self.index + 1}/{SEGMENT_COUNT}: "
                f"{self.name().upper()}")

    def remaining(self):
        """Seconds left in this segment (0 when the demo is over)."""
        if self.done:
            return 0.0
        return max(0.0, self.seconds - self.elapsed)


def _blackout_points(state):
    """Point of the head of the first player (the blackout keeps it lit)."""
    players = (state or {}).get("players") or ()
    if not players:
        return ()
    first = players[0]
    return ((first["x"], first["y"] - G.HEAD_ABOVE),)


def _fire_point(state):
    """Hot air around the ball (x, y, radius) of the fire segment."""
    ball = (state or {}).get("ball") or {}
    return (float(ball.get("x") or 0.0), float(ball.get("y") or 0.0),
            FIRE_RADIUS)


FORCED = {
    "ice": {"ice": ICE_FORCED},
    "confusion": {"confusion": CONFUSION_FORCED},
    "blackout": {"blackout": _blackout_points},
    "fire": {"fire": _fire_point},
    "shock": {"trail": TRAIL_FORCED},
}


class DemoScreen(match_screens.MatchScreen):
    """The match of the demo: two bots, ten segments, one CSV.

    Every segment forces its effect (the match does not have to produce it)
    and the timings of the frame go to a `MeasurementLog`. With both
    backends the demo runs twice: first with the GPU and then with numpy
    (or the other way round when there is no GPU).
    """

    VIEWER = 0                 # the demo is watched from player 0

    def __init__(self, app, chars=None, log=None):
        self.seed = self._seed(app)
        self.matches = 0
        self._init_run(app, log)
        chars = list(chars or config.CHARACTER_IDS[:AVATARS])
        super().__init__(app, chars)
        self.bots = [bot.Bot(index, BOT_LEVEL, self.seed + index)
                     for index in range(AVATARS)]
        self._dt = ONE_SECOND / config.UI_FPS
        self._shock = 0.0
        self._replay = 0.0

    def _init_run(self, app, log):
        """Clock, passes and measurement log of the run."""
        self.director = DemoDirector(getattr(app.options, "demo_seconds",
                                             None),
                                     getattr(app.options, "demo_frame_clock",
                                             False))
        self.passes = _passes(app.options)
        self.compare = len(self.passes) > 1     # two passes: same quality
        self.pass_index = 0
        self.finished = False
        self.measure = log or gpu_metrics.MeasurementLog(
            getattr(app.options, "measure_csv", None),
            frames_csv=bool(getattr(app.options, "measure_frames", False)))
        self._index = None

    @staticmethod
    def _seed(app):
        """Seed of the first match (`--seed` or the default of the demo)."""
        return app.options.seed if app.options.seed is not None else G.DEMO_SEED

    # ------------------------------------------------------------ cycle
    def enter(self):
        """Warms the sprites and starts the first segment."""
        super().enter()
        postfx = self.app.postfx
        if getattr(postfx, "enabled", False) and getattr(postfx, "ops",
                                                         None) is None:
            postfx.start()          # compile before measuring, not inside
        self._switch_backend(self.passes[self.pass_index])
        self._enter_segment(self.director.index)

    def _start_payload(self):
        """Every match of the demo uses a seed of its own."""
        payload = super()._start_payload()
        payload["seed"] = self.seed + self.matches
        self.matches += 1
        return payload

    def controls(self, active):
        """The two bots play (nobody touches the keyboard in the demo)."""
        if self.state is None:
            return [None, None]
        return [player.controls(self.state, self._dt)
                for player in self.bots]

    def update(self, dt):
        """Advances the clock of the demo and the effect of the segment."""
        self._dt = dt
        super().update(dt)
        if self.finished:
            return
        self._measure_frame()
        index = self.director.step(dt, ONE_SECOND / config.UI_FPS)
        if index != self._index:
            self._enter_segment(index)
        self._tick_segment(dt)

    def _measure_frame(self):
        """One line of the CSV with the work and the chain of this frame."""
        frames = getattr(getattr(self.app.postfx, "metrics", None), "frames",
                         ())
        self.measure.add_frame(self.app.work_ms,
                               frames[-1] if frames else 0.0)

    def _enter_segment(self, index):
        """Closes the previous segment and prepares the new one."""
        self._close_segment()
        self._index = index
        self._apply_effect(self.director.kind())
        self._shock = 0.0
        self._replay = 0.0
        self.measure.begin_segment(
            index + 1, self.director.name(), self._backend(),
            self._device(), self._resolution(), self._window(),
            self.app.remote, self.app.postfx.quality_label(), self._block())

    def _close_segment(self):
        """Ends the measurement (nothing to close the first time)."""
        if self._index is None:
            return
        self.measure.end_segment(self._kernels())

    def _kernels(self):
        """Mean ms per stage of the segment being closed."""
        summary = self.app.postfx.summary()
        return {name: summary.get(name, 0.0) for name in gpu_metrics.STAGES}

    def _apply_effect(self, kind):
        """Forces what the segment has to show (and nothing else)."""
        postfx = self.app.postfx
        postfx.force(clear=True)
        postfx.night = (kind == "night")
        postfx.enabled = self._chain_wanted() and kind is not None
        for name, params in FORCED.items():
            if kind == name:
                postfx.force(**params)

    def _chain_wanted(self):
        """Whether the effects can run at all in this machine."""
        return getattr(self.app.postfx, "mode", "off") != "off"

    def _tick_segment(self, dt):
        """The per-segment extra: waves and replays every few seconds."""
        if self.director.kind() == "shock":
            self._shock = self._periodic(dt, self._shock,
                                         G.DEMO_SHOCK_EVERY, self._wave)
        if self.director.kind() in ("replay", "var"):
            self._replay = self._periodic(dt, self._replay,
                                          G.DEMO_REPLAY_EVERY,
                                          self._replay_once)
        if self.director.done:
            self._finish_pass()

    def _periodic(self, dt, timer, period, action):
        """Calls `action` every `period` seconds; returns the new timer."""
        timer += dt
        if timer >= period:
            action()
            return 0.0
        return timer

    def _wave(self):
        """A goal wave in the middle of the pitch (segment 7)."""
        ball = (self.state or {}).get("ball") or {}
        self.app.postfx.event({"type": protocol.EV_GOAL,
                               "x": ball.get("x", 0.0),
                               "y": ball.get("y", 0.0)})

    def _replay_once(self):
        """Starts a replay or the VAR (segments 8 and 9)."""
        if self.app.postfx.replay_mode() is None:
            self.app.postfx.begin_replay(self.director.kind() == "var")

    def _finish_pass(self):
        """Ends the pass; with both backends it starts the other one."""
        self._close_segment()
        self._index = None
        if not self._next_pass():
            self.finished = True
            self.measure.close()

    def _next_pass(self):
        """Switches the backend and restarts the demo (False if no more)."""
        self.pass_index += 1
        if self.pass_index >= len(self.passes):
            return False
        self._switch_backend(self.passes[self.pass_index])
        self.director = DemoDirector(self.director.seconds,
                                     self.director.frame_clock)
        self._enter_segment(self.director.index)
        return True

    def _switch_backend(self, target):
        """F4-like switch: GPU <-> numpy, without restarting the game."""
        if self.app.postfx.mode != target and self.app.postfx.mode != "off":
            self.app.postfx.toggle()
        if self.compare:
            self.app.postfx.governor.enabled = False

    # ------------------------------------------------------------ events
    def on_match_over(self):
        """The whistle restarts the match: the demo never stops."""
        self._start(protocol.CMD_RESTART)

    def handle_event(self, ev):
        """Esc quits, Tab skips to the next segment; the rest as usual."""
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.quit()
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_TAB:
            self._skip()
            return
        super().handle_event(ev)

    def _skip(self):
        """Tab: closes this segment and jumps to the next one."""
        if self.finished:
            return
        self._close_segment()
        self.director._next()         # pylint: disable=protected-access
        self._index = self.director.index
        self._enter_segment(self._index)

    # ------------------------------------------------------------ drawing
    def draw(self, surf):
        """The match, the heat overlay of the last segment and the label."""
        super().draw(surf)
        if self.finished:
            self._draw_finished(surf)
            return
        if self.director.kind() == "heat" and self.state is not None:
            self.app.postfx.heat_overlay(surf, HEAT_CHANNEL)
        self._draw_label(surf)

    def _draw_label(self, surf):
        """Segment name and seconds left, big (it is for a projector)."""
        assets.draw_text(surf, self.director.label(), layout.FONT_LARGE,
                         (layout.CENTER_X, LABEL_Y), palette.WHITE,
                         outline=palette.INK)
        note = (f"{self.director.remaining():.1f} s · Tab: siguiente · "
                f"Esc: salir · F4: GPU/numpy")
        assets.draw_text(surf, note, layout.FONT_SMALL,
                         (layout.CENTER_X, LABEL_Y + LABEL_NOTE_Y),
                         palette.WHITE, outline=palette.INK)

    def _draw_finished(self, surf):
        """Sign of the end of the demo (the CSV is already closed)."""
        assets.draw_text(surf, "FIN DE LA DEMO", layout.FONT_LARGE,
                         (layout.CENTER_X, LABEL_Y), palette.GOLD,
                         outline=palette.INK)
        assets.draw_text(surf, f"Tiempos en {self.measure.path}",
                         layout.FONT_SMALL,
                         (layout.CENTER_X, LABEL_Y + LABEL_NOTE_Y),
                         palette.WHITE, outline=palette.INK)

    # ------------------------------------------------------------ data
    def _backend(self):
        """'gpu' or 'cpu' as the chain is running now."""
        return getattr(self.app.postfx, "mode", "off")

    def _device(self):
        """Name of the device that runs the effects."""
        return getattr(self.app.postfx, "device", "CPU")

    def _resolution(self):
        """Size of the image the chain processes."""
        return f"{config.LOGICAL_WIDTH}x{config.LOGICAL_HEIGHT}"

    def _window(self):
        """Size of the real window."""
        width, height = self.app.screen.get_size()
        return f"{width}x{height}"

    def _block(self):
        """Threads per block of the kernels (for the CSV)."""
        size = backend.BLOCK
        return f"{size[0]}x{size[1]}"

    def report(self):
        """Summary of the demo for the tool and the tests."""
        return {"csv": self.measure.path, "rows": list(self.measure.rows),
                "finished": self.finished, "passes": len(self.passes),
                "segments": SEGMENT_COUNT}


def _passes(options):
    """Backends of the demo: both ('gpu' first when it is available)."""
    wanted = getattr(options, "demo_backends", "both") or "both"
    if wanted != "both":
        return [wanted]
    if getattr(options, "force_cpu", False) or not _cuda_here():
        return ["cpu"]          # a machine without NVIDIA measures once
    return ["gpu", "cpu"]


def _cuda_here():
    """True if the demo may use CUDA (FDC_GPU=1 and PyCUDA works)."""
    return bool(config.Gpu.ENABLED) and backend.available()


def run_demo(argv=(), max_frames=None):
    """Runs the whole demo headless; returns what `DemoScreen.report` says."""
    headless()
    pygame.init()
    options = main_module.parse_args(list(argv) + ["--demo", "--no-audio"])
    main_module.apply_gpu_options(options)
    game = ui_app.App(options)
    try:
        return _loop_demo(game, max_frames)
    finally:
        game.shutdown()


def _loop_demo(game, max_frames):
    """Frames until the demo finishes (or the limit is reached)."""
    screen, played = _play_frames(game, max_frames or _demo_frames())
    if not isinstance(screen, DemoScreen):
        return {"finished": False, "rows": [], "csv": None}
    report = screen.report()
    report["frames"] = played
    return report


def _play_frames(game, limit):
    """Calls frame() until the demo ends; returns (screen, frames)."""
    screen = None
    played = 0
    while game.running and played < limit:
        game.frame()
        screen = game.current
        played += 1
        if isinstance(screen, DemoScreen) and screen.finished:
            break
    return screen, played


def _demo_frames():
    """Frames of a whole demo with the two backends (plus a margin)."""
    return int((SEGMENT_COUNT * G.DEMO_SECONDS * config.UI_FPS
                + WAIT_SECONDS) * 2)
