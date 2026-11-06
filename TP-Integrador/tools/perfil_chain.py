"""Per-kernel cost of the chain in FULL (F11): where the frame time goes.

Usage (PowerShell, from the repository):
    py tools\\perfil_chain.py            # FULL with the GPU
    py tools\\perfil_chain.py --cpu      # FULL with numpy
    py tools\\perfil_chain.py --modo optimizado

It runs the real match for a few seconds and prints the mean of every
kernel of `postfx.summary()`, biggest first.
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

FRAMES = 20              # frames measured
WARM = 5                 # frames drawn before measuring
WAIT_SECONDS = 20.0      # s until the simulation sends its first state
WAIT_STEP = 0.01         # s between frames while waiting
PLAY_TIMEOUT = 60.0      # s waiting for the kick off
NO_AUDIO = "--no-audio"  # the measurement has no sound
NO_GPU = "--no-gpu"      # flag of the command line of the game
MODE_FLAG = "--modo"     # flag that changes the quality mode
FULL = "full"            # the mode with everything
NOT_TIME = ("frames", "fps", "frame", "work_ms", "fx_ms", "other",
            "mode", "quality", "quality_level", "quality_mode",
            "quality_name", "active", "gpu")


def main(argv):
    """Measures the chain and prints the kernels from the slowest one."""
    gpu_env.setup()
    pygame.init()
    game = ui_app.App(main_module.parse_args([NO_AUDIO]))
    try:
        data = _run(game, _mode(argv), "--cpu" in argv)
    finally:
        game.shutdown()
    _report(data)
    return 0


def _mode(argv):
    """Quality mode of the command line (FULL by default)."""
    if MODE_FLAG in argv:
        index = argv.index(MODE_FLAG)
        if index + 1 < len(argv):
            return argv[index + 1]
    return FULL


def _run(game, mode, cpu):
    """Frames of a real match with that mode: the summary of the chain."""
    screen = match_screens.MatchScreen(game, config.CHARACTER_IDS[:2])
    game.switch(screen)
    game.clock.sleep = False
    screen.on_focus_lost = _ignore
    _wait_playing(game, screen)
    _switch(game, mode, cpu)
    for _ in range(WARM + FRAMES):
        game.frame()
    return game.postfx.summary()


def _switch(game, mode, cpu):
    """Sets the quality mode and, if asked, the numpy backend (F4)."""
    game.postfx.set_quality_mode(mode)
    if cpu and game.postfx.mode != "cpu":
        game.postfx.toggle()


def _ignore():
    """Nothing on focus loss: the measurement needs the match playing."""
    return None


def _wait_playing(game, screen):
    """Frames until the kick off."""
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


def _report(data):
    """Kernels from the slowest one, with the total of the chain."""
    print(f"modo {data.get('quality_name')} · {data.get('gpu')} · "
          f"frame {data.get('frame', 0):.1f} ms")
    rows = [(name, value) for name, value in data.items()
            if name not in NOT_TIME and isinstance(value, (int, float))
            and value > 0.0]
    for name, value in sorted(rows, key=lambda row: -row[1]):
        print(f"  {name:14} {value:7.3f} ms")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
