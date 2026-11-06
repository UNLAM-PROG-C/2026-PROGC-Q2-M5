"""Captures of the F11 improvements: modes, crowd, powers and icons.

Usage (PowerShell, from the repository):
    py tools\\capture_mejoras.py             # FULL on the GPU + OPTIMIZADO CPU
    py tools\\capture_mejoras.py --cpu       # everything on numpy
    py tools\\capture_mejoras.py --out otro  # another output folder

It runs a real match at 1280x720 (no window) and saves:
    mejoras-full-00.png   the match in FULL (crowd and all the effects)
    mejoras-full-gol.png  a goal: the stand of the scorer jumps, confetti
    mejoras-opt-00.png    the same moment in OPTIMIZADO (no crowd)
    poder-hielo/apagon/confusion/fuego.png   each power at full strength
    poder-noche.png       the night mode with the lamps swinging
    iconos.png            the legend screen with the new icons
    iconos-montaje.png    the 20 icons big, and one with the pulse steps
The images go to `capturas\\mejoras\\`, to compare with `capturas\\gpu\\`.
"""
import math
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
from fdc.ui import app as ui_app                  # noqa: E402
from fdc.ui import icons                          # noqa: E402
from fdc.ui import match_screens                  # noqa: E402
from fdc.ui import palette                        # noqa: E402
from fdc.ui import screens                        # noqa: E402

FOLDER = os.path.join(PROJECT, "capturas", "mejoras")   # where the PNGs go
CPU = "--cpu"            # flag: the whole capture on the numpy backend
OUT = "--out"            # flag that changes the output folder
NO_AUDIO = "--no-audio"  # the capture has no sound
NO_GPU = "--no-gpu"      # flag of the command line of the game
FULL = "full"            # the mode with everything
OPTIMIZED = "optimizado"  # the light mode
SKIP_FRAMES = 60         # frames of play before the first shot
POWER_FRAMES = 8         # frames drawn with a power on (the effect settles)
GOAL_AT = 0.35           # s after the goal for the shot of the party
GOAL_LIMIT = 900         # frames drawn at most to reach that moment
WAIT_SECONDS = 20.0      # s until the simulation sends its first state
WAIT_STEP = 0.01         # s between frames while waiting
PLAY_TIMEOUT = 60.0      # s waiting for the kick off
SCORER = 0               # character that scores in the forced goal
SIDE = 0                 # left goal of the forced goal
# Powers of the shots: name of the file and the effect of the state.
POWERS = (
    ("hielo", {"power": "freeze_self", "prop": "frozen", "target": "p0",
               "left": 6.0, "dur": 8.0}),
    ("apagon", {"power": "blackout", "prop": "blackout", "target": "p1",
                "left": 5.0, "dur": 6.0}),
    ("confusion", {"power": "confusion", "prop": "confusion",
                   "target": "p0", "left": 4.0, "dur": 5.0}),
    ("fuego", {"power": "fire", "prop": "fire", "target": "ball",
               "left": 5.0, "dur": 6.0}),
)
NIGHT = "noche"          # name of the shot of the night mode
ICON_GRID = 5            # icons per row of the montage
ICON_PX = 96             # px of the icons of the montage
ICON_GAP = 8             # px between icons of the montage
PULSE_STEPS = 5          # brightness steps of the pulse shot
PULSE_ICON = "blackout"  # icon used to show the pulse
DARK = (18, 18, 24)      # background of the montages


def main(argv):
    """Runs the match and saves the pictures."""
    folder, backend = _options(argv)
    gpu_env.setup()
    pygame.init()
    os.makedirs(folder, exist_ok=True)
    game = ui_app.App(main_module.parse_args([NO_AUDIO, *backend]))
    try:
        saved = _run(game, folder)
    finally:
        game.shutdown()
    for path in saved:
        print(path)
    return 0


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


def _run(game, folder):
    """The match, the goal, the optimized mode, the powers and the icons."""
    screen = _open_match(game)
    _wait_playing(game, screen)
    _play(game, SKIP_FRAMES)
    saved = [_save(game, folder, "mejoras-full-00")]
    saved += _goal_shots(game, screen, folder)
    saved += _mode_shot(game, folder, OPTIMIZED, "mejoras-opt-00")
    game.postfx.set_quality_mode(FULL)
    saved += _power_shots(game, screen, folder)
    saved += _icon_shots(game, folder)
    return saved


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


def _play(game, frames):
    """Frames of play (the crowd moves, the ball goes)."""
    for _ in range(frames):
        game.frame()


def _goal_shots(game, screen, folder):
    """Forces a goal and takes the shot of the party in FULL."""
    _force_goal(game, screen)
    start = game.postfx.clock
    frames = 0
    while game.postfx.clock - start < GOAL_AT and frames < GOAL_LIMIT:
        game.frame()
        frames += 1
    saved = [_save(game, folder, "mejoras-full-gol")]
    game.postfx.skip()
    return saved


def _force_goal(game, screen):
    """Sends the event of a goal from the middle of the pitch."""
    ball = (screen.state or {}).get("ball") or {}
    game.postfx.skip()
    game.postfx.event({"type": protocol.EV_GOAL,
                       "x": ball.get("x") or config.Arena.WIDTH / 2.0,
                       "y": ball.get("y") or config.Arena.HEIGHT / 2.0,
                       "side": SIDE, "scorer": SCORER})


def _mode_shot(game, folder, mode, name):
    """One shot of the match in another quality mode."""
    game.postfx.set_quality_mode(mode)
    _play(game, POWER_FRAMES)
    return [_save(game, folder, name)]


def _power_shots(game, screen, folder):
    """One shot per power, at full strength, in FULL mode."""
    saved = []
    for name, effect in POWERS:
        original = _fix_state(screen, [effect])
        _play(game, POWER_FRAMES)
        saved.append(_save(game, folder, f"poder-{name}"))
        screen.on_link = original
    return saved + _night_shot(game, screen, folder)


def _fix_state(screen, effects):
    """Completes every state the sim sends with these effects (the power).

    The match is played by the simulation, so the state is replaced as soon
    as one arrives: the injection has to be done on each one. Returns the
    original `on_link` so the caller can put it back.
    """
    original = screen.on_link

    def on_link(msgs, state):
        original(msgs, state)
        if screen.state is not None:
            screen.state = dict(screen.state, effects=list(effects))

    screen.on_link = on_link
    return original


def _night_shot(game, screen, folder):
    """The night mode with the lamps of the stadium."""
    game.postfx.night = True
    _play(game, POWER_FRAMES)
    path = _save(game, folder, f"poder-{NIGHT}")
    game.postfx.night = False
    _play(game, 1)
    return [path]


def _icon_shots(game, folder):
    """The legend screen, the options menu and a montage of the 20 icons."""
    game.switch(screens.LegendScreen(game))
    game.frame()
    saved = [_save(game, folder, "iconos")]
    game.switch(screens.OptionsScreen(game))
    game.frame()
    saved.append(_save(game, folder, "opciones"))
    saved.append(_montage(os.path.join(folder, "iconos-montaje.png")))
    saved.append(_pulse_montage(os.path.join(folder, "iconos-pulso.png")))
    return saved


def _save(game, folder, name):
    """Saves the screen as a PNG and returns its path."""
    path = os.path.join(folder, f"{name}.png")
    pygame.image.save(game.screen, path)
    return path


def _montage(path):
    """All the icons of the game big, in a grid, over a dark background."""
    ids = [p.id for p in config.POWERS]
    cols = ICON_GRID
    rows = math.ceil(len(ids) / cols)
    step = ICON_PX + ICON_GAP
    surf = pygame.Surface((cols * step + ICON_GAP, rows * step + ICON_GAP))
    surf.fill(DARK)
    for k, power_id in enumerate(ids):
        x = ICON_GAP + (k % cols) * step
        y = ICON_GAP + (k // cols) * step
        surf.blit(icons.power_icon(power_id, ICON_PX), (x, y))
    pygame.image.save(surf, path)
    return path


def _pulse_montage(path):
    """One icon at each brightness of the pulse (it shines when it appears)."""
    step = ICON_PX + ICON_GAP
    surf = pygame.Surface((PULSE_STEPS * step + ICON_GAP, step + ICON_GAP))
    surf.fill(DARK)
    for k in range(PULSE_STEPS):
        icon = icons.power_icon(PULSE_ICON, ICON_PX, k / (PULSE_STEPS - 1))
        surf.blit(icon, (ICON_GAP + k * step, ICON_GAP))
    pygame.image.save(surf, path)
    return path


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
