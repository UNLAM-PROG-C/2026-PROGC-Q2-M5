"""Frame rate of the real game in each quality mode (F11), at 1280x720.

Usage (PowerShell, from the repository):
    py tools\\bench_modos.py            # FULL GPU, FULL CPU, OPTIMIZADO CPU
    py tools\\bench_modos.py --frames 60

It opens a real match without a window, lets the simulation start, and then
times `FRAMES` frames of the *whole* game (simulation state + world drawing
+ effects) with the clock limiter off, in each configuration of the table
of the card. The kernels keep their own measurement in `postfx.summary()`,
so the table also shows how much of the frame is the effects chain.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame                                     # noqa: E402

import main as main_module                        # noqa: E402
from fdc import config                            # noqa: E402
from fdc import protocol                          # noqa: E402
from fdc.gpu import env as gpu_env                # noqa: E402
from fdc.ui import app as ui_app                  # noqa: E402
from fdc.ui import match_screens                  # noqa: E402

FULL = "full"            # the mode with everything
OPTIMIZED = "optimizado"  # the light mode
CPU = "cpu"              # the numpy backend
GPU = "gpu"              # the CUDA backend
FRAMES = 30              # frames timed per configuration
WARM = 5                 # frames drawn before timing (buffers, governor)
WAIT_SECONDS = 20.0      # s until the simulation sends its first state
WAIT_STEP = 0.01         # s between frames while waiting
PLAY_TIMEOUT = 60.0      # s waiting for the kick off
NO_AUDIO = "--no-audio"  # the measurement has no sound
NO_GPU = "--no-gpu"      # flag of the command line of the game
FRAMES_FLAG = "--frames"  # flag that changes the number of frames
MS = 1000.0              # seconds to milliseconds
# Configurations of the card: (quality mode, backend wanted).
TABLE = ((FULL, GPU), (FULL, CPU), (OPTIMIZED, CPU))


def main(argv):
    """Measures each configuration and prints the table."""
    frames = _frames(argv)
    gpu_env.setup()
    pygame.init()
    game = ui_app.App(main_module.parse_args([NO_AUDIO]))
    try:
        rows = _run(game, frames)
    finally:
        game.shutdown()
    _report(rows)
    return 0


def _frames(argv):
    """`--frames N` or the default."""
    if FRAMES_FLAG in argv:
        index = argv.index(FRAMES_FLAG)
        if index + 1 < len(argv):
            return int(argv[index + 1])
    return FRAMES


def _run(game, frames):
    """One row per configuration: (mode, backend, ms, fps, effects ms)."""
    screen = _open_match(game)
    _wait_playing(game, screen)
    rows = []
    for mode, backend in TABLE:
        rows.append(_measure(game, mode, backend, frames))
    return rows


def _open_match(game):
    """Match screen between the first two characters."""
    screen = match_screens.MatchScreen(game, config.CHARACTER_IDS[:2])
    game.switch(screen)
    game.clock.sleep = False        # no limiter: we measure capacity
    screen.on_focus_lost = _ignore  # the dummy window loses focus: no pause
    return screen


def _ignore():
    """Nothing on focus loss: the measurement needs the match playing."""
    return None


def _wait_playing(game, screen):
    """Frames until the simulation sends a state and the kick off happens."""
    limit = time.perf_counter() + WAIT_SECONDS
    while screen.state is None and time.perf_counter() < limit:
        game.frame()
        time.sleep(WAIT_STEP)
    limit = time.perf_counter() + PLAY_TIMEOUT
    while time.perf_counter() < limit:
        if (screen.state or {}).get("phase") == protocol.PHASE_PLAYING:
            return True
        game.frame()
    return False


def _measure(game, mode, backend, frames):
    """Timed frames of one configuration (the effects of the last one win)."""
    _switch(game, mode, backend)
    for _ in range(WARM):
        game.frame()
    start = time.perf_counter()
    for _ in range(frames):
        game.frame()
    elapsed = time.perf_counter() - start
    data = game.postfx.summary()
    return mode, data.get("gpu", "-"), elapsed * MS / frames, data


def _switch(game, mode, backend):
    """Sets the quality mode and the backend (F4 is a toggle)."""
    game.postfx.set_quality_mode(mode)
    if (game.postfx.mode == GPU) != (backend == GPU):
        game.postfx.toggle()


def _report(rows):
    """Markdown table with the frame rate and the cost of the effects."""
    print("| modo | backend | ms/frame | fps | ms efectos |")
    print("|---|---|---|---|---|")
    for mode, device, ms, data in rows:
        fps = MS / ms if ms else 0.0
        effects = float(data.get("frame") or 0.0)
        print(f"| {mode} | {device} | {ms:.1f} | {fps:.1f} | {effects:.1f} |")
    print("\n(1280x720, ventana sin driver: sin vsync ni presentación)")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
