"""Night captures: the same frame through the chain, before and after.

Usage (PowerShell, from the repository, with the venv activated):

    py tools\\captura_noche.py --raw              # picks the frame
    py tools\\captura_noche.py --chain despues    # GPU chain -> despues.png
    py tools\\captura_noche.py --chain despues --cpu

`--raw` plays a real match in FULL, walks the first player to the middle of
two lamps and saves the frame **without effects**
(`capturas\\noche\\cuadro.png`) with its match state.  `--chain NAME` runs the
chain of effects over that same frame until the auto exposure settles and
writes `NAME.png`: so every picture of the night is one identical frame.
"""
import json
import os
import sys
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np                                  # noqa: E402
import pygame                                       # noqa: E402

import main as main_module                          # noqa: E402
from fdc import config                              # noqa: E402
from fdc import protocol                            # noqa: E402
from fdc.gpu import effects_state                   # noqa: E402
from fdc.gpu import env as gpu_env                  # noqa: E402
from fdc.gpu import postfx                          # noqa: E402
from fdc.ui import app as ui_app                    # noqa: E402
from fdc.ui import match_screens                    # noqa: E402

SHOTS = os.path.join(ROOT, "capturas", "noche")   # folder of the pictures
FRAME = "cuadro.png"        # the frame of the capture (no effects)
STATE = "cuadro.json"       # match state of that frame
WIDTH, HEIGHT = 1280, 720   # logical screen of the game
DT = 1.0 / 60.0             # s of each frame of the chain
CONVERGE = 120              # frames until the auto exposure settles
QUALITY = "full"            # quality mode of the capture
NO_TIME = 0.0               # clock of the frame: the lamps do not swing
ROUND = 2                   # decimals of the printed numbers
P95 = 95                    # percentile reported for the pitch
BURNT = 250                 # from this level a pixel looks burnt
MIDDLE = 2                  # the player walks between lamp 2 and lamp 3
PLAYERS = 2                 # players of a match of the capture
WALK_SECONDS = 25.0         # s the player may walk to its place
GOAL_TOLERANCE = 8.0        # px: close enough to the place of the walk
WAIT_STEP = 0.005           # s between frames while waiting
WAIT_SECONDS = 20.0         # s until the simulation sends its first state
KICKOFF_SECONDS = 60.0      # s waiting for the kick off
FALL_FLOOR = 0.0            # light of a lamp out of its radius
LUMA = np.array([0.299, 0.587, 0.114], np.float32)  # Rec. 601
NO_AUDIO = "--no-audio"     # the capture has no sound
RAW = "--raw"               # flag that picks the frame
CHAIN = "--chain"           # flag that draws a stored frame
CPU = "--cpu"               # flag that runs the numpy chain
DEFAULT_NAME = "despues"    # file name when `--chain` has no name
KEPT = ("players", "ball", "phase", "score", "goals", "effects")


def main():
    """`--raw` picks the frame; `--chain NAME` draws it with the chain."""
    args = list(sys.argv[1:])
    if RAW in args:
        return _capture_raw()
    if CHAIN in args:
        return _chain(_name(args), CPU in args)
    print(__doc__)
    return 1


def _name(args):
    """File name asked after `--chain`."""
    index = args.index(CHAIN) + 1
    return args[index] if index < len(args) else DEFAULT_NAME


def _options(no_gpu):
    """Command line the effects read (quality FULL, the night is local)."""
    return types.SimpleNamespace(no_gpu=False, force_cpu=bool(no_gpu),
                                 gpu_quality=QUALITY, web=False,
                                 quality=QUALITY, overlay=None, demo=False,
                                 window=None, record=False, test_mode=False)


def _chain(name, no_gpu):
    """Runs the chain over the saved frame and writes `name`.png."""
    fx, screen = _open_chain(no_gpu)
    raw, state = _load_frame()
    _settle(fx, raw, state, screen)
    fx.clock = NO_TIME                  # same phase of the lamps
    _draw(fx, raw, state, screen)
    _write(name, screen, fx, state)
    return 0


def _open_chain(no_gpu):
    """Effects chain in FULL with the night on (GPU or numpy)."""
    gpu_env.setup()
    pygame.init()
    pygame.display.set_mode((WIDTH, HEIGHT))
    fx = postfx.PostFx(_options(no_gpu), (WIDTH, HEIGHT))
    fx.start()
    fx.enabled = True
    fx.set_quality_mode(QUALITY)
    fx.night = True
    return fx, pygame.Surface((WIDTH, HEIGHT))


def _load_frame():
    """The picture without effects and the state that drew it."""
    raw = pygame.image.load(os.path.join(SHOTS, FRAME)).convert()
    with open(os.path.join(SHOTS, STATE), encoding="utf-8") as handle:
        state = json.load(handle)
    return raw, state


def _settle(fx, raw, state, screen):
    """Feeds the same frame until the auto exposure stops moving."""
    for _ in range(CONVERGE):
        _draw(fx, raw, state, screen)


def _draw(fx, raw, state, screen):
    """One frame of the chain over the stored picture."""
    target = fx.begin(screen, state)
    target.blit(raw, (0, 0))
    fx.finish(screen, DT)


def _write(name, screen, fx, state):
    """Saves the picture and prints what the frame looks like."""
    path = os.path.join(SHOTS, name + ".png")
    pygame.image.save(screen, path)
    print(json.dumps({"archivo": path, "backend": fx.mode,
                      "gain": round(float(fx.exposure.gain), ROUND),
                      "noche": bool(fx.fx.night), **_stats(screen, state)},
                     ensure_ascii=False))


def _stats(screen, state):
    """Brightness of the grass, the burnt pixels and the players."""
    lum = _to_array(screen) @ LUMA
    pitch = lum[config.Gpu.PITCH_TOP:]
    return {"cancha": {"media": round(float(pitch.mean()), ROUND),
                       "p95": round(float(np.percentile(pitch, P95)), ROUND),
                       "max": round(float(pitch.max()), ROUND)},
            "quemados": int((lum >= BURNT).sum()),
            "jugadores": _players(state)}


def _players(state):
    """Players of the frame with the light of the night on each one."""
    return [{"x": round(p["x"]), "y": round(p["y"]),
             "lampara": round(_lamp_distance(p["x"])),
             "luz": round(_light(p["x"], p["y"]), ROUND)}
            for p in state.get("players") or ()]


def _light(x, y):
    """Light of the night at a point: the formula of `k_spotlights`."""
    light = config.Gpu.NIGHT_AMBIENT
    top = config.Gpu.NIGHT_LIGHT_MAX
    for lx, ly, radius, power in effects_state.night_lights():
        fall = max(FALL_FLOOR, 1.0 - ((x - lx) ** 2 + (y - ly) ** 2)
                   / (radius * radius))
        light += power * fall * fall * (top - light)
    return light


def _lamp_distance(x):
    """Distance in px from `x` to the nearest lamp of the night."""
    return min(abs(x - lamp[0]) for lamp in effects_state.night_lights())


def _capture_raw():
    """A real match frame with the first player between two lamps."""
    game, screen = _open_match()
    _wait_playing(game, screen)
    if not _playing(screen):
        raise SystemExit("El partido no arranco: no hay estado en juego.")
    state = _walk(game, screen)
    _save_raw(state, _copy(game.postfx.target))
    game.shutdown()
    return 0


def _open_match():
    """The app with the night on (no sound) and its match screen."""
    gpu_env.setup()
    pygame.init()
    os.makedirs(SHOTS, exist_ok=True)
    game = ui_app.App(main_module.parse_args([NO_AUDIO]))
    screen = match_screens.MatchScreen(game, config.CHARACTER_IDS[:PLAYERS])
    game.switch(screen)
    game.clock.sleep = False            # the capture is not a measurement
    screen.on_focus_lost = _ignore      # the dummy window loses focus
    game.postfx.set_quality_mode(QUALITY)
    game.postfx.start()
    game.postfx.night = True
    return game, screen


def _ignore():
    """Nothing on focus loss: the capture needs the match playing."""
    return None


def _wait_playing(game, screen):
    """Frames until the simulation is playing the match."""
    deadline = time.perf_counter() + WAIT_SECONDS
    while screen.state is None and time.perf_counter() < deadline:
        _heartbeat(screen, game)
        time.sleep(WAIT_STEP)
    deadline = time.perf_counter() + KICKOFF_SECONDS
    while time.perf_counter() < deadline and not _playing(screen):
        _heartbeat(screen, game)
    return screen.state


def _playing(screen):
    """True when the match is being played."""
    return (screen.state or {}).get("phase") == protocol.PHASE_PLAYING


def _walk(game, screen):
    """Walks one player between two lamps; the other stays under a lamp."""
    _walk_to(game, screen, _middle_lamp())
    game.input.release_all()
    _heartbeat(screen, game)
    return screen.state


def _middle_lamp():
    """x of the middle between two lamps of the night."""
    lamps = [lamp[0] for lamp in effects_state.night_lights()]
    return (lamps[MIDDLE] + lamps[MIDDLE + 1]) * 0.5


def _walk_to(game, screen, target):
    """Steps until the first player reaches `target` (or time is out)."""
    deadline = time.perf_counter() + WALK_SECONDS
    while time.perf_counter() < deadline and not _arrived(screen, target):
        _steer(game, screen, target)
        _heartbeat(screen, game, True)


def _arrived(screen, target):
    """True when the first player is close enough to `target`."""
    players = screen.state.get("players") or ()
    return bool(players) and abs(players[0]["x"] - target) <= GOAL_TOLERANCE


def _steer(game, screen, target):
    """Presses left or right of the first player to reach `target`."""
    players = screen.state.get("players") or ()
    held = game.input.held[0]
    held["left"] = bool(players) and players[0]["x"] > target + GOAL_TOLERANCE
    held["right"] = bool(players) and players[0]["x"] < target - GOAL_TOLERANCE


def _heartbeat(screen, game, active=False):
    """One frame with the controls of the keyboard (or none)."""
    screen.app.link.send_input(screen.controls(active))
    game.frame()


def _save_raw(state, image):
    """The picture without effects and the state that drew it."""
    pygame.image.save(image, os.path.join(SHOTS, FRAME))
    keep = {key: state.get(key) for key in KEPT}
    with open(os.path.join(SHOTS, STATE), "w", encoding="utf-8") as handle:
        json.dump(keep, handle, ensure_ascii=False, indent=1)
    print(json.dumps({"cuadro": os.path.join(SHOTS, FRAME),
                      "jugadores": _players(state)}, ensure_ascii=False))


def _copy(surface):
    """A copy of a surface (the target is reused every frame)."""
    copy = pygame.Surface(surface.get_size())
    copy.blit(surface, (0, 0))
    return copy


def _to_array(surface):
    """(h, w, 3) uint8 image of a surface."""
    raw = pygame.surfarray.array3d(surface)
    return np.ascontiguousarray(np.transpose(raw, (1, 0, 2)))


if __name__ == "__main__":
    sys.exit(main())
