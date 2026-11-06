"""A picture of FULL drawn by the numpy chain (a machine without CUDA).

Usage (PowerShell, from the repository):

    py tools\\captura_cpu_full.py                  # capturas\\cpu-full.png
    py tools\\captura_cpu_full.py --out otra.png   # another file

It plays a real match without a window, in FULL and with the effects on, and
saves one frame drawn by the CPU chain: the same picture a Mac, a notebook or
the CPU executable shows when there is no CUDA. The tool refuses to save when
the chain turned out to be the GPU one, so the picture is always honest.
"""
import json
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

OUT = "--out"             # flag that changes the output file
OVERLAY = "full"          # overlay that shows quality and backend
FULL = "full"             # quality mode with every effect
CPU_MODE = "cpu"          # name of the numpy chain
DT = 1.0 / 60.0           # s: fixed step of the frame that is saved
PLAY_FRAMES = 120         # frames of play before the picture (crowd moving)
WAIT_SECONDS = 20.0       # s until the simulation sends its first state
WAIT_STEP = 0.01          # s between frames while waiting
PLAY_TIMEOUT = 60.0       # s waiting for the kick off
DEFAULT_OUT = os.path.join("capturas", "cpu-full.png")
NO_AUDIO = "--no-audio"   # the capture has no sound


def main(argv):
    """Opens a match on the CPU chain, plays and saves one frame."""
    path = _options(argv)
    _capture(path)
    print(path)
    return 0


def _capture(path):
    """The whole capture: the match, the frames and the picture."""
    gpu_env.setup()
    pygame.init()
    _make_folder(path)
    game = _open_game()
    try:
        _save_frame(game, path)
    finally:
        game.shutdown()


def _open_game():
    """The app with the overlay on (the capture has no sound)."""
    return ui_app.App(main_module.parse_args([NO_AUDIO, "--overlay", OVERLAY]))


def _save_frame(game, path):
    """Opens the match, plays and saves the picture of that frame."""
    screen = _open_match(game)
    _require_cpu(game)          # before the match: starting is slow
    _wait_playing(game, screen)
    _play(game, screen, PLAY_FRAMES)
    _require_unpaused(screen)
    _draw_and_save(game, screen, path)
    _summary(game, screen)


def _options(argv):
    """Output file of the capture."""
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == OUT and args:
            return os.path.abspath(args.pop(0))
    return os.path.abspath(DEFAULT_OUT)


def _make_folder(path):
    """The folder of the picture, if it does not exist yet."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)


def _open_match(game):
    """Match screen between the first two characters, in FULL."""
    screen = match_screens.MatchScreen(game, config.CHARACTER_IDS[:2])
    game.switch(screen)
    game.clock.sleep = False        # the capture is not a measurement
    screen.on_focus_lost = _ignore  # the dummy window loses focus: no pause
    game.postfx.set_quality_mode(FULL)
    return screen


def _ignore():
    """Nothing on focus loss: the capture needs the match playing."""
    return None


def _wait_playing(game, screen):
    """Frames until the simulation sends a state and the kick off happens."""
    limit = time.perf_counter() + WAIT_SECONDS
    while screen.state is None and time.perf_counter() < limit:
        _heartbeat(screen)
        game.frame()
        time.sleep(WAIT_STEP)
    limit = time.perf_counter() + PLAY_TIMEOUT
    while time.perf_counter() < limit:
        _heartbeat(screen)
        if (screen.state or {}).get("phase") == protocol.PHASE_PLAYING:
            return True
        game.frame()
    raise SystemExit("El partido no arrancó: no hay estado en juego.")


def _play(game, screen, frames):
    """Frames of play (the crowd moves); the control keeps the match on."""
    for _ in range(frames):
        _heartbeat(screen)
        game.frame()


def _heartbeat(screen):
    """Neutral controls: they also keep the simulation's watchdog asleep."""
    screen.app.link.send_input(screen.controls(False))


def _require_unpaused(screen):
    """The pause menu covers the scene: the capture would be useless."""
    state = screen.state or {}
    if screen.pause_state is not None or state.get("paused"):
        raise SystemExit("El partido se pausó durante la captura: ui=%s "
                         "motivo=%s sim_paused=%s" % (
                             screen.pause_state,
                             getattr(screen, "pause_reason", None),
                             state.get("paused")))


def _require_cpu(game):
    """Without the CPU chain the picture would be the GPU one."""
    postfx = game.postfx
    if postfx is None:
        raise SystemExit("No hay cadena de efectos: revisá la configuración.")
    postfx.start()
    if postfx.mode != CPU_MODE or not postfx.enabled:
        raise SystemExit("Esta captura necesita la cadena CPU: probá con "
                         "FDC_GPU=0 (backend numpy).")


def _draw_and_save(game, screen, path):
    """Draws the current frame with a fixed step and saves it."""
    game.last_dt = DT
    screen.draw(game.screen)
    game.overlay.draw(game.screen, game._overlay_info())  # the F2 panel
    pygame.image.save(game.screen, path)


def _summary(game, screen):
    """Backend, quality and pause state of the picture (for the record)."""
    state = screen.state or {}
    print(json.dumps({"backend": game.postfx.mode,
                      "calidad": game.postfx.quality_mode,
                      "efectos": bool(game.postfx.enabled),
                      "pausado": screen.pause_state or state.get("paused"),
                      "overlay": game.overlay.mode}))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
