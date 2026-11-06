"""One headless desktop client for the two-instance online check.

It is not a test: `tools/online_two_apps.py` starts the server and one
process per backend, each one running this script. The client opens the
online mode, enters (or joins) a room, readies up, plays for a few seconds
with the effects chain on and leaves a JSON with what it measured.
"""
import argparse
import json
import os
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pygame  # noqa: E402

import main as game_main  # noqa: E402
from fdc import profile as profiles  # noqa: E402
from fdc.ui import app as ui_app  # noqa: E402
from fdc.ui import online_screens  # noqa: E402
from fdc.ui import screens  # noqa: E402

BOOT_WAIT = 40.0        # s until the main menu
CONNECT_WAIT = 20.0     # s until the room list
ROOM_WAIT = 25.0        # s until the room (created or joined)
MATCH_WAIT = 40.0       # s until the match starts
STATE_WAIT = 10.0       # s until the first state of the match
DEFAULT_SECONDS = 6.0   # s of play when --seconds is not given
MOVE_MIN = 20           # px the player must move to count as "moving"
ICE = 0.85              # forced ice strength (0-1)
TRAIL = 1.0             # forced ball trail (0-1)
KICK_EVERY = 0.4        # s between kicks
# Keys from the main menu to the online room list.
ONLINE_KEYS = (pygame.K_RETURN, pygame.K_s, pygame.K_RETURN, pygame.K_s,
               pygame.K_RETURN)
# Keys that move the player to the right on each side.
RIGHT_KEYS = (pygame.K_d, pygame.K_LEFT)


def parse():
    """Command line of one client."""
    parser = argparse.ArgumentParser(description="headless online client")
    parser.add_argument("--role", choices=("create", "join"), required=True)
    parser.add_argument("--backend", choices=("gpu", "cpu"), required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--name", default="Cliente")
    parser.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    parser.add_argument("--out", required=True)
    parser.add_argument("--shots", default=None)
    return parser.parse_args()


def profile_file(name):
    """Temporary profile so the game does not ask for the name."""
    folder = tempfile.mkdtemp(prefix="fdc-online-")
    path = os.path.join(folder, "profile.json")
    profiles.save(profiles.Profile(name, None), path)
    return path


def game_options(args):
    """Options of the real App for this client."""
    flags = ["--backend", args.backend, "--no-audio", "--overlay", "full"]
    options = game_main.parse_args(flags)
    game_main.apply_gpu_options(options)
    options.profile_path = profile_file(args.name)
    options.server_url = args.server
    return options


class Driver:
    """Runs frames of the App and posts synthetic keyboard events."""

    def __init__(self, app, shots_dir=None):
        self.app = app
        self.shots_dir = shots_dir
        self.frames_drawn = 0

    def frames(self, n=1):
        for _ in range(n):
            self.app.frame()
            self.frames_drawn += 1

    def until(self, cond, timeout, what):
        start = time.monotonic()
        while not cond():
            self.frames(1)
            if time.monotonic() - start > timeout:
                raise AssertionError(f"timed out waiting for {what}")

    def seconds(self, secs):
        start = time.monotonic()
        while time.monotonic() - start < secs:
            self.frames(1)

    def tap(self, key):
        self.post(pygame.KEYDOWN, key=key)
        self.post(pygame.KEYUP, key=key)

    def post(self, etype, **kw):
        attrs = {"key": None, "mod": 0, "unicode": "", "scancode": 0}
        attrs.update(kw)
        pygame.event.post(pygame.event.Event(etype, **attrs))
        self.frames(1)

    def screen(self):
        return self.app.current

    def shot(self, name):
        if self.shots_dir:
            path = os.path.join(self.shots_dir, name + ".png")
            pygame.image.save(self.app.screen, path)
            return path
        return None


def reach_rooms(d):
    """From the boot screen to the online room list."""
    d.until(lambda: isinstance(d.screen(), screens.MenuScreen), BOOT_WAIT,
            "menu")
    for key in ONLINE_KEYS:
        d.tap(key)
    d.until(lambda: isinstance(d.screen(), online_screens.RoomsScreen),
            CONNECT_WAIT, "room list")


def open_room(d, role):
    """Creates a free room or joins the first one in the list."""
    if role == "create":
        d.tap(pygame.K_c)
        d.until(lambda: isinstance(d.screen(), online_screens.CreateRoomScreen),
                ROOM_WAIT, "create form")
        d.tap(pygame.K_RETURN)
    else:
        d.until(lambda: bool(d.app.net and d.app.net.rooms), ROOM_WAIT,
                "room in the list")
        d.tap(pygame.K_RETURN)
    d.until(lambda: isinstance(d.screen(), online_screens.RoomScreen),
            ROOM_WAIT, "room")


def _two_players(room):
    """True when the room has the two players and can start."""
    members = (room.net.room or {}).get("members") or ()
    return room.choosing() and len(members) >= 2


def start_match(d):
    """Ready up and wait until the server starts the match."""
    room = d.screen()
    d.until(lambda: _two_players(room), MATCH_WAIT, "rival in the room")
    d.tap(pygame.K_SPACE)
    d.until(lambda: isinstance(d.screen(), online_screens.OnlineMatchScreen),
            MATCH_WAIT, "match")
    match = d.screen()
    d.until(lambda: match.state is not None, STATE_WAIT, "first state")
    return match


def play(d, match, secs, shots):
    """Plays for `secs` seconds with forced effects and measures the chain."""
    postfx = d.app.postfx
    mode = postfx.mode
    me = match.you
    x0 = match.state["players"][me]["x"]
    costs = _hold(d, postfx, mode, secs)
    d.post(pygame.KEYUP, key=RIGHT_KEYS[me])
    x1 = match.state["players"][me]["x"]
    data = {"mode": mode, "frames": d.frames_drawn,
            "moved_px": round(abs(x1 - x0), 1)}
    data.update(_costs(costs), effects=postfx.active_effects(),
                shot=d.shot(f"online_{mode}_{me}"))
    return data


def _costs(costs):
    """Average and maximum fx ms of the frames measured."""
    if not costs:
        return {"fx_ms_avg": None, "fx_ms_max": None}
    return {"fx_ms_avg": round(sum(costs) / len(costs), 2),
            "fx_ms_max": round(max(costs), 2)}


def _hold(d, postfx, mode, secs):
    """Forces ice and trail while the clock runs; returns the fx ms seen."""
    costs = []
    start = time.monotonic()
    while time.monotonic() - start < secs:
        postfx.force(ice=ICE, trail=TRAIL)
        d.frames(1)
        if postfx.last_ms.get(mode):
            costs.append(postfx.last_ms[mode])
    return costs


def _flow(d, args, result):
    """Menus, room, match and the measured play (raises on any problem)."""
    reach_rooms(d)
    open_room(d, args.role)
    match = start_match(d)
    d.post(pygame.KEYDOWN, key=RIGHT_KEYS[match.you])
    result["score"] = list(match.state["score"])
    result.update(play(d, match, args.seconds, args.shots))
    if result["moved_px"] < MOVE_MIN:
        raise AssertionError("the player did not move")
    result["ok"] = True


def _save(d, path, result):
    """Writes the JSON and closes the game (window and simulation process)."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    d.app.running = False
    d.app.shutdown()


def run(args):
    """Whole flow of one client; always writes the JSON."""
    app = ui_app.App(game_options(args))
    d = Driver(app, args.shots)
    result = {"role": args.role, "backend": args.backend, "name": args.name,
              "ok": False}
    try:
        _flow(d, args, result)
    except Exception as exc:      # pylint: disable=broad-except
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["screen"] = type(d.screen()).__name__
    _save(d, args.out, result)
    return result


def main():
    """Entry point of one client."""
    args = parse()
    if args.shots:
        os.makedirs(args.shots, exist_ok=True)
    result = run(args)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
