"""Two real game instances (GPU and CPU) playing online on a local server.

Requirement 11 of spec.md section 15: two clients, one with the effects on
the GPU and one on numpy, play a match over the local WebSocket without
errors. Each client is the real application (menus, room, match) running
headless with the dummy SDL driver; the server is the real one, inside this
process. It also leaves one capture per instance in `frames/` (or --shots).

    python tools/online_two_apps.py
    python tools/online_two_apps.py --seconds 8 --duration 25
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = os.path.join(ROOT, "tools", "online_client.py")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fdc.online import server as game_server  # noqa: E402

START_WAIT = 10         # s for the server to start
STOP_WAIT = 15          # s for the server thread to end
CLIENT_TIMEOUT = 180    # s for each client to finish
DEFAULT_SECONDS = 6.0   # s of online play of each instance
DEFAULT_DURATION = 25.0  # s of the match on the server
SEED = 7                # fixed seed: same match on every run


class ServerThread:
    """The real GameServer on a free port, in its own thread and loop."""

    def __init__(self, **kw):
        kw.setdefault("web_dir", None)
        kw.setdefault("sim_logs", False)
        self.server = game_server.GameServer(**kw)
        self.started = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.server.run("127.0.0.1", 0,
                                                started=self.started.set))
        loop.close()

    def __enter__(self):
        self.thread.start()
        if not self.started.wait(START_WAIT):
            raise RuntimeError("the server did not start")
        return self

    def __exit__(self, *exc):
        self.server.request_stop()
        self.thread.join(STOP_WAIT)

    @property
    def url(self):
        return f"ws://127.0.0.1:{self.server.port}/ws"


def parse():
    """Command line of the check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=DEFAULT_SECONDS,
                        help="seconds of online play of each instance")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION,
                        help="seconds of the match on the server")
    parser.add_argument("--timeout", type=float, default=CLIENT_TIMEOUT)
    parser.add_argument("--shots", default=os.path.join(ROOT, "frames"))
    return parser.parse_args()


def spawn(role, backend, url, args, out_dir):
    """Starts one client process and returns it with its result path."""
    out = os.path.join(out_dir, f"client_{role}_{backend}.json")
    name = "Ale" if role == "create" else "Nico"
    cmd = [sys.executable, CLIENT, "--role", role, "--backend", backend,
           "--server", url, "--name", name, "--seconds", str(args.seconds),
           "--out", out, "--shots", args.shots]
    log = open(out + ".log", "w",  # pylint: disable=consider-using-with
               encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=log)
    return proc, out


def wait_all(pairs, timeout):
    """Waits for every client and returns the JSON of each one."""
    end = time.monotonic() + timeout
    results = []
    for proc, out in pairs:
        left = max(1.0, end - time.monotonic())
        try:
            code = proc.wait(timeout=left)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = None
        results.append((code, _read(out), out))
    return results


def _read(path):
    """The JSON a client left (or a note explaining why it is missing)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": f"no result: {exc}"}


def _line(result, code):
    """One row of the summary."""
    back = result.get("backend", "?")
    return (f"  {result.get('role', '?'):6} {back:4} "
            f"-> {result.get('mode', '?'):4} "
            f"frames {result.get('frames', 0):4} "
            f"movio {result.get('moved_px', 0):6} px  "
            f"fx {result.get('fx_ms_avg')} ms "
            f"(max {result.get('fx_ms_max')})  "
            f"efectos {result.get('effects', '-')}  "
            f"exit {code}  {result.get('error', '')}")


def report(results):
    """Prints the summary and returns True when both clients worked."""
    print("dos instancias (GPU + CPU) por WebSocket local:")
    ok = True
    for code, result, path in results:
        print(_line(result, code))
        print(f"    {path}")
        ok = ok and bool(result.get("ok")) and code == 0
        if not result.get("ok"):
            print(f"    pantalla: {result.get('screen')}  "
                  f"log: {path}.log")
    return ok


def main():
    """Runs the server, the two clients and prints the result."""
    args = parse()
    os.makedirs(args.shots, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fdc-two-") as out_dir, \
            ServerThread(duration=args.duration, seed=SEED) as srv:
        print(f"servidor {srv.url} (partido de {args.duration:.0f} s)")
        pairs = [spawn("create", "gpu", srv.url, args, out_dir),
                 spawn("join", "cpu", srv.url, args, out_dir)]
        results = wait_all(pairs, args.timeout)
    ok = report(results)
    print("OK: las dos instancias jugaron sin errores" if ok
          else "FALLO: alguna instancia no termino bien")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
