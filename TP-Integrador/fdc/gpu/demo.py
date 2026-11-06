"""Automatic demo: plays a match without a window and measures the effects.

`tools/demo_gpu.py` calls this. It is the way to check that the loop with
the post-processing chain neither breaks nor slows the game down: the same
frames run with the effects on and off and the numbers are compared.
"""
import os
import time

import pygame

import main as main_module
from fdc import config
from fdc.sim import match as sim_match   # noqa: F401  (imported by the link)
from fdc.ui import app as ui_app
from fdc.ui import match_screens

DEFAULT_FRAMES = 600      # 10 s at 60 fps
SPEED = 60.0              # frames per second: the simulated time
MS_PER_S = 1000.0         # milliseconds in a second
WAIT_SECONDS = 15.0       # s until the simulation sends the first state
WAIT_STEP = 0.01          # s between frames while waiting


def run(frames=DEFAULT_FRAMES, argv=()):
    """Plays `frames` frames headless; returns the metrics of the chain."""
    options = main_module.parse_args(list(argv) + ["--no-audio"])
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
