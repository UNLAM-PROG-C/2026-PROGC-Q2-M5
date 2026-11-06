"""Cost of the effects chain with each power on (F11), at 1280x720.

Usage (PowerShell, from the repository):
    py tools\\bench_poderes.py            # each power in FULL on the GPU
    py tools\\bench_poderes.py --cpu      # the same on numpy
    py tools\\bench_poderes.py --frames 40

It opens a real match without a window, lets the simulation start and, for
every power of the table, replaces the effects of the state, lets the chain
settle and then times `FRAMES` frames. Two numbers per row: the whole chain
(`postfx.summary()["frame"]`) and the frame of the game (simulation state
plus world plus effects).
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
from fdc.gpu import metrics as gpu_metrics        # noqa: E402
from fdc.ui import app as ui_app                  # noqa: E402
from fdc.ui import match_screens                  # noqa: E402

FULL = "full"            # the mode with every stage
CPU = "--cpu"            # flag: the numpy backend
STAGES_FLAG = "--stages"  # flag: print every stage of every power
FRAMES_FLAG = "--frames"  # flag that changes the timed frames
FRAMES = 20              # frames timed per power and round
ROUNDS = 3               # rounds per power (the best one is reported)
CLOCK_WARM = 90          # frames drawn before measuring (GPU clocks)
WARM = 6                 # frames drawn before timing (the effect settles)
WAIT_SECONDS = 20.0      # s until the simulation sends its first state
WAIT_STEP = 0.01         # s between frames while waiting
PLAY_TIMEOUT = 60.0      # s waiting for the kick off
NO_AUDIO = "--no-audio"  # the measurement has no sound
NO_GPU = "--no-gpu"      # flag of the command line of the game
MS = 1000.0              # seconds to milliseconds
STAGES = ("glow", "particles", "lights", "ice",
          "confusion", "confusion_rot", "fire", "blackout", "night",
          "exposure", "tribuna")
# Powers of the table: the same effects `capture_mejoras` uses for the shots.
POWERS = (
    ("ninguno", []),
    ("hielo", [{"power": "freeze_self", "prop": "frozen", "target": "p0",
                "left": 6.0, "dur": 8.0}]),
    ("apagon", [{"power": "blackout", "prop": "blackout", "target": "p1",
                 "left": 5.0, "dur": 6.0}]),
    ("confusion", [{"power": "confusion", "prop": "confusion", "target": "p0",
                    "left": 4.0, "dur": 5.0}]),
    ("fuego", [{"power": "fire", "prop": "fire", "target": "ball",
                "left": 5.0, "dur": 6.0}]),
)
TENTH = 0.1              # ms: below this a stage is noise in the breakdown
HEADER = "| poder | cadena ms | cuadro ms | etapa mas cara | costosa ms |"
RULE = "| --- | ---: | ---: | --- | ---: |"


def main(argv):
    """Measures every power and prints the table."""
    frames = _frames(argv)
    gpu_env.setup()
    pygame.init()
    game = ui_app.App(main_module.parse_args(
        [NO_AUDIO, *([NO_GPU] if CPU in argv else [])]))
    try:
        rows = _run(game, frames, CPU in argv)
    finally:
        game.shutdown()
    _report(rows, STAGES_FLAG in argv)
    return 0


def _frames(argv):
    """`--frames N` or the default."""
    if FRAMES_FLAG in argv:
        index = argv.index(FRAMES_FLAG)
        if index + 1 < len(argv):
            return int(argv[index + 1])
    return FRAMES


def _run(game, frames, cpu):
    """One row per power: (name, chain ms, frame ms, data of the best round)."""
    screen = _open_match(game)
    _wait_playing(game, screen)
    game.postfx.set_quality_mode(FULL)
    _play(game, CLOCK_WARM)       # the GPU clocks are cold at the start
    rows = []
    for name, effects in POWERS:
        original = _inject(screen, effects)
        rounds = [_measure(game, name, frames) for _ in range(ROUNDS)]
        rows.append(_best(rounds))
        screen.on_link = original
    return rows


def _play(game, frames):
    """Frames of play (they warm the clocks up)."""
    for _ in range(frames):
        game.frame()


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


def _inject(screen, effects):
    """Replaces the effects of every state the sim sends (the power).

    Returns the original `on_link` so the caller can put it back.
    """
    original = screen.on_link

    def on_link(msgs, state):
        original(msgs, state)
        if screen.state is not None:
            screen.state = dict(screen.state, effects=list(effects))

    screen.on_link = on_link
    return original


def _measure(game, name, frames):
    """Timed frames of one power: the chain, the whole frame and the data."""
    for _ in range(WARM):
        game.frame()
    game.postfx.metrics = gpu_metrics.Metrics()
    start = time.perf_counter()
    for _ in range(frames):
        game.frame()
    elapsed = time.perf_counter() - start
    data = game.postfx.summary()
    return name, data.get("frame", 0.0), elapsed * MS / frames, data


def _best(rounds):
    """Row of the fastest round: the shortest frame of the power."""
    return min(rounds, key=lambda row: row[1])


def _worst(data):
    """(name, ms) of the most expensive stage of the summary."""
    pairs = [(name, data.get(name, 0.0)) for name in STAGES]
    return max(pairs, key=lambda pair: pair[1]) if pairs else ("-", 0.0)


def _report(rows, verbose):
    """Markdown table of the measurements (and, if asked, every stage)."""
    print(HEADER)
    print(RULE)
    for name, chain, frame, data in rows:
        stage, stage_ms = _worst(data)
        print(f"| {name} | {chain:.2f} | {frame:.2f} | {stage} "
              f"| {stage_ms:.2f} |")
    if verbose:
        _report_stages(rows)


def _report_stages(rows):
    """One line per power with the stages that cost more than a tenth."""
    for name, _, _, data in rows:
        used = [f"{key} {data.get(key, 0.0):.2f}" for key in STAGES
                if data.get(key, 0.0) >= TENTH]
        print(f"{name}: " + ", ".join(used))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
