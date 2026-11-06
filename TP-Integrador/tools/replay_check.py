"""Real check of the replay of a goal in an online match.

It starts the real server and two real windows (headless SDL): one in FULL and
one in the mode "SIN EFECTOS". They play, one of them scores, and both have to
show the replay inside the same window of the simulation and come back to play
at the same moment. It leaves a JSON summary and, if asked, one capture per
client.

From the repo root, in PowerShell:

    py tools\\replay_check.py --captures C:\\temp\\replay

It exits with 0 when the two clients agree.
"""
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import online_helpers  # noqa: E402
from fdc import config  # noqa: E402

CLIENT = os.path.join(ROOT, "tools", "replay_client.py")
LOGS = ("client-full.json", "client-plain.json")   # what each client saves
CLIENT_WAIT = 90        # s: each client plays and exits
ROOM_WAIT = 4.0         # s: the room has to exist before the rival looks
WINDOW = config.MatchRules.GOAL_REPLAY   # s of the replay window
SAME_STATES = 4         # states apart that count as "the same moment"
MATCH_SECONDS = 60.0    # s of the match of the check
MATCH_SEED = 7          # seed of that match


def parse():
    """Options of the check (python, captures folder and the two modes)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--captures", default=os.getcwd())
    parser.add_argument("--full", default="full")
    parser.add_argument("--plain", default="sin-efectos")
    return parser.parse_args()


def start_client(python, args, out):
    """Launches one real client in its own process."""
    return subprocess.Popen([python, CLIENT, "--output", out] + args,
                            cwd=ROOT, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)


def read_log(path):
    """JSON of one client (empty dict if it did not finish)."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def ends(rows, key):
    """First and last value of that key (empty if there are no rows)."""
    values = [row[key] for row in rows if row[key] is not None]
    return [values[0], values[-1]] if values else []


def modes(rows):
    """What each client said it was drawing inside the window."""
    return sorted({str(row["mode"]) for row in rows})


def still(rows):
    """True if nobody moved during the goal (all the rows say the same)."""
    return len({tuple(row["x"]) for row in rows}) == 1


def client_summary(log):
    """What one client saw of the goal and of the replay."""
    rows = log.get("rows") or []
    goal = [row for row in rows if row["phase"] == "goal"]
    window = [row for row in goal if row["window"] is not None]
    return {"quality": log.get("quality"), "side": log.get("side"),
            "goal_at": log.get("goal_at"), "modes": modes(window),
            "frames": len(window), "progress": ends(window, "window"),
            "ball": ends(window, "ball"), "still": still(goal),
            "resumed": log.get("resumed"),
            "captures": log.get("captures", [])}


def problems_of(name, seen):
    """Basic checks of one client: window, rewind, nobody moved, resume."""
    found = []
    if seen["frames"] < 2:
        found.append(f"{name}: the window of the replay never opened")
    if seen["ball"] and seen["ball"][0] == seen["ball"][1]:
        found.append(f"{name}: the ball did not move in the replay")
    if not seen["still"]:
        found.append(f"{name}: somebody moved during the goal")
    if not seen["resumed"]:
        found.append(f"{name}: it never came back to play")
    return found


def together(seen):
    """Both clients come back at the same moment (same states of the server)."""
    states = [item["resumed"]["seq"] for item in seen if item["resumed"]]
    if len(states) != len(seen):
        return ["they did not come back to play (both of them)"]
    if abs(states[0] - states[1]) > SAME_STATES:
        return [f"they came back in different states: {states}"]
    return []


def report(full, plain):
    """Summary and list of problems of the two clients."""
    seen = [client_summary(full), client_summary(plain)]
    found = problems_of("full", seen[0]) + problems_of("plain", seen[1])
    found += together(seen)
    return {"window_s": WINDOW, "clients": seen, "problems": found}


def run(opt):
    """The whole check: server, two clients, summary."""
    folder = opt.captures
    os.makedirs(folder, exist_ok=True)
    with online_helpers.ServerThread(duration=MATCH_SECONDS,
                                     seed=MATCH_SEED) as srv:
        logs = [os.path.join(folder, name) for name in LOGS]
        play_both(opt, srv.url, folder, logs)
        result = report(read_log(logs[0]), read_log(logs[1]))
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return not result["problems"]


def args_of(quality, name, url, folder, create):
    """Command line of one client."""
    args = ["--url", url, "--name", name, "--quality", quality,
            "--captures", folder]
    return args + ["--create"] if create else args


def play_both(opt, url, folder, logs):
    """Starts the two clients and waits for both of them."""
    clients = [start_client(opt.python,
                            args_of(opt.full, "Ale", url, folder, True),
                            logs[0])]
    time.sleep(ROOM_WAIT)   # the room has to exist before the rival
    clients.append(start_client(opt.python,
                                args_of(opt.plain, "Bruno", url, folder,
                                        False), logs[1]))
    for client in clients:
        client.wait(CLIENT_WAIT)


def main():
    """Runs the check and exits with 0 when the clients agree."""
    sys.exit(0 if run(parse()) else 1)


if __name__ == "__main__":
    main()
