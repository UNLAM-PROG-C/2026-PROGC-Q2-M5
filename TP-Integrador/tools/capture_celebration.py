"""Captures of the goal celebration (F10) in a real match, without a window.

Usage (PowerShell, from the repository):
    py tools\\capture_celebration.py                # GPU backend
    py tools\\capture_celebration.py --cpu          # numpy backend
    py tools\\capture_celebration.py --out other\\path

It runs a real match at 1280x720 with the effects on, forces a goal and saves
one PNG per moment of the party (confetti and sign) plus one of the replay.
The images go to capturas\\mejoras\\ (celebracion-00 = the goal itself).
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

FOLDER = os.path.join(ROOT, "capturas", "mejoras")   # where the PNGs go
PREFIX = "celebracion"   # name of the shots of the party
BEFORE = "antes"         # name of the shot before the goal
AND = "y"                # joins the two names of a shot
# Frames (at 60 fps) after the goal in which a shot is taken: the burst, the
# paper in the air, the end of the party and the start of the replay.
SHOTS = (0, 6, 18, 36, 60, 96, 140, 200)
SKIP_FRAMES = 90         # frames of play before the goal (the ball moves)
PLAY_TIMEOUT = 60.0      # s waiting for the kick off (the countdown first)
WAIT_SECONDS = 20.0      # s until the simulation sends its first state
WAIT_STEP = 0.01         # s between frames while waiting
CPU = "--cpu"            # flag that switches to the numpy backend
OUT = "--out"            # flag that changes the output folder
NO_AUDIO = "--no-audio"  # the capture has no sound
NO_GPU = "--no-gpu"      # flag of the command line of the game
SCORER = 0               # character that scores in the forced goal
SIDE = 0                 # left goal of the forced goal


def main(argv):
    """Runs the match, forces the goal and saves the pictures."""
    folder, backend = _options(argv)
    gpu_env.setup()
    pygame.init()
    os.makedirs(folder, exist_ok=True)
    game = ui_app.App(main_module.parse_args([NO_AUDIO, *backend]))
    try:
        saved = _run(game, folder)
    finally:
        game.shutdown()
    _report(game, saved)
    return 0 if len(saved) == len(SHOTS) else 1


def _run(game, folder):
    """Plays until the kick off, forces a goal and takes the shots."""
    screen = _open_match(game)
    _wait_state(game, screen)
    _wait_playing(game, screen)
    _play(game, SKIP_FRAMES)
    return _shoot(game, screen, folder)


def _options(argv):
    """Output folder and backend flags of the command line."""
    folder, backend = FOLDER, []
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == CPU:
            backend = [NO_GPU]
        elif arg == OUT and args:
            folder = os.path.abspath(args.pop(0))
    return folder, backend


def _open_match(game):
    """Match screen between the first two characters."""
    screen = match_screens.MatchScreen(game, config.CHARACTER_IDS[:2])
    game.switch(screen)
    game.clock.sleep = False        # the capture is not a measurement
    return screen


def _wait_state(game, screen):
    """Frames until the simulation sends its first state."""
    limit = time.perf_counter() + WAIT_SECONDS
    while screen.state is None and time.perf_counter() < limit:
        game.frame()
        time.sleep(WAIT_STEP)


def _wait_playing(game, screen):
    """Frames until the kick off (the first countdown has to end)."""
    limit = time.perf_counter() + PLAY_TIMEOUT
    while time.perf_counter() < limit:
        if _phase(screen) == protocol.PHASE_PLAYING:
            return True
        game.frame()
    return False


def _phase(screen):
    """Phase of the last state the screen received."""
    return (screen.state or {}).get("phase")


def _play(game, frames):
    """Frames of play before the goal."""
    for _ in range(frames):
        game.frame()


def _goal(game, screen):
    """Forces a real goal: with a side, the party and the replay start."""
    ball = (screen.state or {}).get("ball") or {}
    game.postfx.force_var = False
    game.postfx.event({"type": protocol.EV_GOAL,
                       "x": ball.get("x") or config.Arena.WIDTH / 2.0,
                       "y": ball.get("y") or config.Arena.HEIGHT / 2.0,
                       "side": SIDE, "scorer": SCORER})


def _shoot(game, screen, folder):
    """One frame per moment of the party; returns the written paths."""
    saved = [_save(game, folder, BEFORE)]
    _goal(game, screen)
    frame = 0
    for shot, target in enumerate(SHOTS):
        frame = _advance(game, frame, target)
        print(f"  shot {shot}: {len(game.postfx.confetti.live()[0])} bits")
        saved.append(_save(game, folder, f"{PREFIX}-{shot:02d}"))
    return saved


def _advance(game, frame, target):
    """Draws frames until the counter reaches `target`."""
    while frame < target:
        game.frame()
        frame += 1
    return frame


def _save(game, folder, name):
    """Saves the screen as a PNG and returns its path."""
    path = os.path.join(folder, f"{name}.png")
    pygame.image.save(game.screen, path)
    return path


def _report(game, saved):
    """Paths and milliseconds of the confetti measured in the run."""
    data = game.postfx.summary()
    print(f"{data['mode']} {data['quality']} gpu={data['gpu']}")
    print(f"confetti {data.get('confetti', 0.0):.3f} ms   "
          f"crt {data.get('crt', 0.0):.3f} ms")
    for path in saved:
        print(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
