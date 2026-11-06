"""The frozen goal: the party, the replay and the kickoff (F10 pause).

Usage (PowerShell, from the worktree):
    py tools\\capture_goal_hold.py             # 1280x720, no window
    py tools\\capture_goal_hold.py --cpu       # the effects on numpy
    py tools\\capture_goal_hold.py --out otro  # another output folder

It plays a local match with the real screen and the real effects (the
simulation runs inside the page, so the script can put the ball in the goal)
and saves one frame of each moment of the frozen goal:
    gol-00-fiesta.png     the party: confetti and the sign
    gol-01-repe.png       the replay on the old television
    gol-02-repe-final.png the last frame of the replay
    gol-03-saque.png      the kickoff at the centre
Every moment is awaited (never a fixed time), so it works at any frame rate.
While the party and the replay last it checks that the simulation does not
change at all (players, ball and clock) and that play comes back from the
centre afterwards. Each check prints OK or FALLA (exit code 1 if any fails).
The images go to `capturas\\mejoras\\repe\\`.
"""
import copy
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.dirname(ROOT)      # the worktree lives inside the project
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

FOLDER = os.path.join(PROJECT, "capturas", "mejoras", "repe")
CPU = "--cpu"            # flag: the effects on the numpy backend
OUT = "--out"            # flag that changes the output folder
NO_AUDIO = "--no-audio"  # the capture has no sound
NUMPY = "--gpu-cpu"      # flag of the command line: effects without CUDA
PROFILE = os.path.join(FOLDER, "perfil-de-prueba.json")   # never written
OK = "OK"                # the check passed
FAIL = "FALLA"           # the check did not pass
PARTY_SHOT = 0.5         # s of party before its frame
REPLAY_END = 0.3         # s before the end of the replay for the last frame
MOMENT_WAIT = 15.0       # s at most waiting for each moment
WAIT_SECONDS = 20.0      # s until the simulation sends its first state
WAIT_STEP = 0.01         # s between frames while waiting
PLAY_TIMEOUT = 60.0      # s waiting for the kick off
PRE_GOAL_SECONDS = 4.0   # s of play before the goal (the clip needs them)
GOAL_WAIT = 3.0          # s at most waiting for the goal to count
BALL_SIDE = 0            # goal where the ball goes in (left)
BALL_LEAD = 60           # px from the mouth where the ball appears
BALL_SPEED = 700         # px/s the ball goes in
# What the frozen goal must not touch: players, ball and match clock.
FROZEN_KEYS = ("players", "ball", "clock")


def main(argv):
    """Runs the match, takes the frames and prints the checks."""
    folder, backend = _options(argv)
    gpu_env.setup()
    pygame.init()
    os.makedirs(folder, exist_ok=True)
    game = ui_app.App(_arguments(backend))
    try:
        saved, checks = _run(game, folder)
    finally:
        game.shutdown()
    _report(saved, checks)
    return _exit_code(checks)


def _report(saved, checks):
    """Prints the images saved and the checks of the pause."""
    for path in saved:
        print(path)
    for line in checks:
        print(line)


def _exit_code(checks):
    """0 when every check passed (so a CI step can read the result)."""
    return 0 if all(line.startswith(OK) for line in checks) else 1


def _options(argv):
    """Output folder and backend flags of the command line."""
    folder, backend = FOLDER, []
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == CPU:
            backend = [NUMPY]
        elif arg == OUT and args:
            folder = os.path.abspath(args.pop(0))
    return folder, backend


def _arguments(backend):
    """Options of the game: no sound and the simulation inside the page."""
    options = main_module.parse_args([NO_AUDIO, *backend])
    options.web = True              # InlineLink: the script moves the ball
    options.profile_path = PROFILE
    return options


def _run(game, folder):
    """The match, the goal and the frames of the frozen goal."""
    if not game.postfx.enabled:
        return [], [f"{FAIL}: sin efectos no hay festejo ni repe que capturar"]
    screen = _open_match(game)
    _wait_playing(game, screen)
    _play_seconds(game, PRE_GOAL_SECONDS)
    return _goal_shots(game, screen, folder)


def _open_match(game):
    """Match screen between the first two characters."""
    screen = match_screens.MatchScreen(game, config.CHARACTER_IDS[:2])
    game.switch(screen)
    game.clock.sleep = False        # the capture is not a measurement
    screen.on_focus_lost = _ignore  # the dummy window loses focus: no pause
    return screen


def _ignore():
    """Nothing on focus loss: the capture needs the match playing."""
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


def _play_seconds(game, seconds):
    """Frames of play during that many seconds."""
    limit = time.perf_counter() + seconds
    while time.perf_counter() < limit:
        game.frame()


def _goal_shots(game, screen, folder):
    """Forces a goal and takes one frame per moment of the frozen goal."""
    _put_ball_in_goal(game.link.core.match)
    if not _wait_goal(game, screen):
        return [], [f"{FAIL}: el gol no entró"]
    frozen = _frozen(screen.state)
    saved, checks = [], []
    for name, moment, still in SHOTS:
        moment(game, screen)
        checks.append(_check(game, screen, frozen, still))
        saved.append(_save(game, folder, name))
    return saved, checks


def _put_ball_in_goal(match):
    """Puts the ball just before the mouth of the goal, going in."""
    goal = match.goals[BALL_SIDE]
    match.ball.x = goal.mouth_x + BALL_LEAD
    match.ball.y = config.Arena.FLOOR_Y - BALL_LEAD
    match.ball.vx, match.ball.vy = -BALL_SPEED, 0


def _wait_goal(game, screen):
    """Frames until the simulation is in the goal phase."""
    return _until(game, lambda: (screen.state or {}).get("phase")
                  == protocol.PHASE_GOAL, GOAL_WAIT)


def _until(game, cond, seconds):
    """Frames until `cond()` is true (False if it does not happen in time)."""
    limit = time.perf_counter() + seconds
    while time.perf_counter() < limit:
        if cond():
            return True
        game.frame()
    return False


def _hold(game):
    """s the frozen goal lasts in this match (party and, maybe, replay)."""
    return float(game.link.core.match.goal_hold)


def _left(screen):
    """s left of the frozen goal (the match clock does not run)."""
    return float((screen.state or {}).get("phase_left") or 0.0)


def _at_party(game, screen):
    """Frames until the party has been on screen PARTY_SHOT seconds."""
    limit = _hold(game) - PARTY_SHOT
    _until(game, lambda: _left(screen) <= limit, MOMENT_WAIT)


def _at_replay(game, screen):
    """Frames until the replay of the goal is on screen."""
    _until(game, lambda: _replaying(game), MOMENT_WAIT)


def _at_replay_end(game, screen):
    """Frames until the replay is REPLAY_END seconds from its end."""
    _until(game, lambda: _replay_ending(game), MOMENT_WAIT)


def _at_kickoff(game, screen):
    """Frames until the simulation is back at the kickoff."""
    _until(game, lambda: (screen.state or {}).get("phase")
           == protocol.PHASE_COUNTDOWN, MOMENT_WAIT)


def _replaying(game):
    """True while the effects draw the replay of the goal."""
    return game.postfx.replay_mode() == replay.REPLAY_KIND


def _replay_ending(game):
    """True when the replay is about to end (or it is already gone)."""
    if not _replaying(game):
        return True
    return game.postfx.player.finished(game.postfx.clock + REPLAY_END)


def _frozen(state):
    """What the frozen goal must not touch, copied (players, ball, clock)."""
    return copy.deepcopy([(state or {}).get(key) for key in FROZEN_KEYS])


def _check(game, screen, frozen, still):
    """One line per frame: the match does not move, or the kickoff came."""
    if still:
        same = _frozen(screen.state) == frozen
        return f"{_tag(same)} congelado, {_shown(game)}"
    back = (screen.state or {}).get("phase") == protocol.PHASE_COUNTDOWN
    return f"{_tag(back)} saque desde el centro"


def _shown(game):
    """What the screen is drawing: the party, the replay or the still pitch."""
    if _replaying(game):
        frames = game.postfx.player.frames
        return f"repe de {frames[-1][0] - frames[0][0]:.1f} s"
    if game.postfx.celebration is not None:
        return "festejo"
    return "cancha quieta"


def _tag(ok):
    """Text of a check."""
    return OK if ok else FAIL


def _save(game, folder, name):
    """Saves the screen as a PNG and returns its path."""
    path = os.path.join(folder, f"{name}.png")
    pygame.image.save(game.screen, path)
    return path


# Moments of the goal: file name, when to take the frame and whether the
# match must still be frozen there (the last one is the kickoff).
SHOTS = (("gol-00-fiesta", _at_party, True),
         ("gol-01-repe", _at_replay, True),
         ("gol-02-repe-final", _at_replay_end, True),
         ("gol-03-saque", _at_kickoff, False))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
