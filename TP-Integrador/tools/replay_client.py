"""One real client of an online match, used by `tools/replay_check.py`.

It opens the game with the quality it is given, goes to the online mode,
creates the room or joins the first one, says ready and plays: the player on
the left chases the ball and kicks it, the other one stands still. It saves a
JSON with what it saw during the goal: the window of the replay, the states
and the moment it came back to play.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import driver  # noqa: E402  (dummy SDL before pygame)
import pygame  # noqa: E402

from fdc import config  # noqa: E402
from fdc import protocol  # noqa: E402
from fdc.ui import online_screens  # noqa: E402
from fdc.ui import screens  # noqa: E402

ONLINE_KEYS = (pygame.K_RETURN, pygame.K_s, pygame.K_RETURN, pygame.K_s,
               pygame.K_RETURN)
WAIT_BALL = 4.0         # s of play before chasing: the ball has to land
KICK_RANGE = 55.0       # px: foot to ball
LOW_BALL = config.Arena.FLOOR_Y - 120.0   # px: ball low enough to kick
GOAL_WAIT = 30.0        # s: give up if there is no goal
WALK_BACK = 4.0         # px: the kicker walks only if the ball is not close
LOG_DECIMALS = 3        # decimals of the times and the progress in the JSON
WAIT_MENU = 25          # s until the menu of the game
WAIT_LIST = 10          # s until the list of rooms
WAIT_FORM = 5           # s until the form of a new room
WAIT_ROOMS = 20         # s until some room appears in the list
WAIT_ROOM = 15          # s until the screen of the room
WAIT_RIVAL = 20         # s until the other player is in the room
WAIT_MATCH = 15         # s until the screen of the match
WAIT_PLAY = 15          # s until the match is in play


def parse():
    """Options of one client (all of them given by the parent script)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--quality", default="full")
    parser.add_argument("--name", default="Ale")
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--captures", default=None)
    return parser.parse_args()


def enter_online(drive):
    """Menu -> multiplayer -> online -> room list."""
    drive.until(lambda: isinstance(drive.screen(), screens.MenuScreen),
                WAIT_MENU, "menu")
    for key in ONLINE_KEYS:
        drive.tap(key)
    drive.until(lambda: isinstance(drive.screen(), online_screens.RoomsScreen),
                WAIT_LIST, "room list")


def open_room(drive, create):
    """Creates a public room or joins the first one of the list."""
    if create:
        create_own_room(drive)
    else:
        join_room(drive)
    drive.until(lambda: isinstance(drive.screen(), online_screens.RoomScreen),
                WAIT_ROOM, "in the room")


def create_own_room(drive):
    """Opens the create form and sends it."""
    drive.tap(pygame.K_c)
    drive.until(lambda: isinstance(drive.screen(),
                                   online_screens.CreateRoomScreen), WAIT_FORM,
                "create form")
    drive.tap(pygame.K_RETURN)


def join_room(drive):
    """Waits for a room of the list and enters it."""
    drive.until(lambda: drive.app.net.rooms, WAIT_ROOMS, "some room")
    drive.tap(pygame.K_RETURN)


def get_ready(drive):
    """Chooses a character, says ready and waits for the match to be in play."""
    wait_rival(drive)
    drive.tap(pygame.K_d)
    drive.tap(pygame.K_SPACE)
    wait_match_screen(drive)
    screen = drive.screen()
    drive.until(lambda: screen.state is not None
                and screen.state["phase"] == protocol.PHASE_PLAYING, WAIT_PLAY,
                "play")
    return screen


def wait_match_screen(drive):
    """Waits until the game shows the screen of the match."""
    match_screen = online_screens.OnlineMatchScreen
    drive.until(lambda: isinstance(drive.screen(), match_screen), WAIT_MATCH,
                "match screen")


def wait_rival(drive):
    """Waits until the other player is in the room."""
    drive.until(lambda: drive.app.net.room is not None
                and len(drive.app.net.room["members"]) == 2, WAIT_RIVAL,
                "rival in the room")


def bot_keys(state, side):
    """Controls of the shooter: walk to the ball and kick it when it is low."""
    player, ball = state["players"][side], state["ball"]
    gap = ball["x"] - player["x"]
    near = abs(gap) < KICK_RANGE and ball["y"] > LOW_BALL
    return gap < -WALK_BACK and not near, gap > WALK_BACK and not near, near


def drive_bot(app, state, side):
    """Writes those controls (there is no keyboard: the window is dummy)."""
    left, right, kick = bot_keys(state, side)
    keys = app.input
    keys.held[0]["left"], keys.held[0]["right"] = left, right
    if kick:
        keys.kicks[0] += 1


def sample(screen):
    """What the client is showing now: state, replay window and drawn ball."""
    state = screen.state
    window = screen.goal_window(state)
    row = {"time": round(time.monotonic(), LOG_DECIMALS),
           "phase": state["phase"],
           "left": round(state["phase_left"], 2), "seq": state.get("seq"),
           "x": [round(p["x"], 1) for p in state["players"]],
           "mode": screen.app.postfx.replay_mode(),
           "window": None if window is None
           else round(window[0], LOG_DECIMALS),
           "ball": drawn_ball(screen, state, window)}
    return row


def drawn_ball(screen, state, window):
    """X of the ball the client is drawing (the live one outside the window)."""
    if window is None:
        return None
    # pylint: disable-next=protected-access
    view = screen._replay_view(state, state, window)
    return round(view["ball"]["x"], 1)


def play(drive, screen, log):
    """Plays until the replay of a goal is over; fills `log`."""
    shooter, rows, goal = screen.you == 0, [], None
    start = time.monotonic()
    while time.monotonic() - start < GOAL_WAIT:
        frame(drive, screen, shooter, start)
        goal = goal or goal_time(screen, start, log)
        if goal is not None:
            rows.append(sample(screen))
            note_window(drive, rows, log)
            if came_back(screen, rows):
                log["resumed"] = sample(screen)
                break
    log["rows"] = rows


def note_window(drive, rows, log):
    """Saves one capture the first time the window of the replay is open."""
    if rows[-1]["window"] is not None and not log.get("captures"):
        capture(drive, log)


def frame(drive, screen, shooter, start):
    """One frame: the shooter chases the ball while the match is in play."""
    state = screen.state
    chasing = (shooter and state["phase"] == protocol.PHASE_PLAYING
               and time.monotonic() - start > WAIT_BALL)
    if chasing:
        drive_bot(drive.app, state, screen.you)
    drive.app.frame()


def goal_time(screen, start, log):
    """Now, if the score just changed (and it is written in the log)."""
    if screen.state["score"] == [0, 0] or "goal_at" in log:
        return None
    log["goal_at"] = round(time.monotonic() - start, 2)
    return time.monotonic()


def came_back(screen, rows):
    """True when the match is in play again after the frozen goal."""
    seen_goal = any(row["phase"] == protocol.PHASE_GOAL for row in rows)
    return seen_goal and screen.state["phase"] == protocol.PHASE_PLAYING


def capture(drive, log):
    """Saves one capture of the replay, at its first frame (if asked)."""
    if not drive.shots_dir:
        return
    name = f"{log['quality']}-replay"
    drive.shot(name)
    log.setdefault("captures", []).append(f"{name}.png")


def save(app, path, log):
    """Closes the game and writes the JSON (even if the match went wrong)."""
    try:
        app.running = False
        app.shutdown()
    finally:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(log, handle, ensure_ascii=False, indent=1)


def main():
    """One client of the check: it plays and writes what it saw."""
    args = parse()
    app = driver.make_app(test_mode=False, seed=None, server_url=args.url,
                          profile_name=args.name, quality_mode=args.quality)
    drive = driver.Driver(app, args.captures)
    app.show_debug = False      # the F3 panel would cover the replay sign
    log = {"quality": args.quality, "name": args.name}
    try:
        play_online(drive, args.create, log)
    finally:
        save(app, args.output, log)


def play_online(drive, create, log):
    """From the menu to the match: it enters, opens the room and plays."""
    enter_online(drive)
    open_room(drive, create)
    screen = get_ready(drive)
    log["side"] = screen.you
    play(drive, screen, log)


if __name__ == "__main__":
    main()
