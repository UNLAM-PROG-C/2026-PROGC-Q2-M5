"""Check: S really skips the frozen goal (real screen, effects and match).

Usage (PowerShell, from the worktree):
    py tools\\check_skip_key.py            # effects on the GPU
    py tools\\check_skip_key.py --cpu      # effects on numpy

It plays a local match with the real screen, scores a goal, waits for the
replay and puts an "S" into the pygame queue. Then it checks that the
simulation came back to the kickoff well before the frozen goal would end
(GOAL_HOLD). It prints the times and exits with 1 if the skip did not work.
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
from fdc.gpu import replay                        # noqa: E402
from fdc.ui import app as ui_app                  # noqa: E402
from fdc.ui import match_screens                  # noqa: E402

CPU = "--cpu"            # flag: the effects on the numpy backend
NUMPY = "--gpu-cpu"      # flag of the command line: effects without CUDA
NO_AUDIO = "--no-audio"  # the check has no sound
GOAL_HOLD = config.MatchRules.GOAL_HOLD   # s the goal stays frozen
PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "perfil-de-prueba.json")   # never written
WAIT_PLAY = 60.0         # s at most waiting for the kick off
WAIT_STEP = 0.01         # s between frames while waiting
PRE_GOAL = 3.0           # s of play before the goal (the clip needs them)
GOAL_WAIT = 3.0          # s at most waiting for the goal
REPLAY_WAIT = 15.0       # s at most waiting for the replay on screen
SKIP_WAIT = 5.0          # s at most waiting for the kickoff after the S
EARLY_SKIP = 1.5         # s before the end of the goal to press S anyway
BALL_SIDE = 0            # goal where the ball goes in (left)
BALL_LEAD = 60           # px from the mouth where the ball appears
BALL_SPEED = 700         # px/s the ball goes in


def main(argv):
    """Plays a goal, presses S on the replay and checks the kickoff."""
    game = _app([NUMPY] if CPU in argv else [])
    try:
        left, back, elapsed = _run(game)
    finally:
        game.shutdown()
    print(f"S con {left:.1f} s de congelado por delante: saque a los "
          f"{elapsed:.2f} s (el congelado dura {GOAL_HOLD:.1f} s)")
    print(("OK" if back else "FALLA") + ": la S saltea el gol")
    return 0 if back else 1


def _app(backend):
    """Application with the effects asked for and the simulation in the page."""
    gpu_env.setup()
    pygame.init()
    return ui_app.App(_arguments(backend))


def _run(game):
    """Plays a goal, presses S during the replay and times the kickoff."""
    screen = _open_match(game)
    started = _score_goal(game, screen)
    _wait_replay(game, screen)
    left = _left(screen)
    _press_skip()
    back = _until(game, lambda: _phase(screen) == protocol.PHASE_COUNTDOWN,
                  SKIP_WAIT)
    return left, back and left > 0, time.perf_counter() - started


def _arguments(backend):
    """Options of the game: no sound and the simulation inside the page."""
    options = main_module.parse_args([NO_AUDIO, *backend])
    options.web = True              # InlineLink: the check moves the ball
    options.profile_path = PROFILE
    return options


def _open_match(game):
    """Match screen between the first two characters, playing."""
    screen = match_screens.MatchScreen(game, config.CHARACTER_IDS[:2])
    game.switch(screen)
    game.clock.sleep = False        # the check is not a measurement
    screen.on_focus_lost = _ignore  # the dummy window loses focus: no pause
    _until(game, lambda: _phase(screen) == protocol.PHASE_PLAYING, WAIT_PLAY)
    _pump(game, PRE_GOAL)
    return screen


def _ignore():
    """Nothing on focus loss: the check needs the match playing."""
    return None


def _score_goal(game, screen):
    """Puts the ball in the goal and returns when the goal counted."""
    _put_ball_in_goal(game.link.core.match)
    _until(game, lambda: _phase(screen) == protocol.PHASE_GOAL, GOAL_WAIT)
    started = time.perf_counter()
    print(f"gol: fase {_phase(screen)}, congelado de "
          f"{screen.state['phase_left']:.1f} s")
    return started


def _put_ball_in_goal(match):
    """Puts the ball just before the mouth of the goal, going in."""
    goal = match.goals[BALL_SIDE]
    match.ball.x = goal.mouth_x + BALL_LEAD
    match.ball.y = config.Arena.FLOOR_Y - BALL_LEAD
    match.ball.vx, match.ball.vy = -BALL_SPEED, 0


def _press_skip():
    """Puts an "S" in the queue, as the keyboard would."""
    key = match_screens.MatchScreen.SKIP_KEY
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))


def _replaying(game):
    """True while the effects draw the replay of the goal."""
    return game.postfx.replay_mode() == replay.REPLAY_KIND


def _wait_replay(game, screen):
    """Frames until the replay is on screen (or the goal is about to end)."""
    _until(game, lambda: _replaying(game) or _left(screen) <= EARLY_SKIP,
           REPLAY_WAIT)


def _left(screen):
    """s left of the frozen goal (the match clock does not run)."""
    return float((screen.state or {}).get("phase_left") or 0.0)


def _phase(screen):
    """Phase of the state the screen is drawing (None until it arrives)."""
    return (screen.state or {}).get("phase")


def _pump(game, seconds):
    """Frames of play during that many seconds."""
    limit = time.perf_counter() + seconds
    while time.perf_counter() < limit:
        game.frame()


def _until(game, cond, seconds):
    """Frames until `cond()` is true (False if it does not happen in time)."""
    limit = time.perf_counter() + seconds
    while time.perf_counter() < limit:
        if cond():
            return True
        game.frame()
    return False


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
