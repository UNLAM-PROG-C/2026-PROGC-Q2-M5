"""Helpers to test the online server with real connections."""
import asyncio
import json
import threading
import time

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from websockets.sync import client as ws_client

from fdc.online import server as game_server
from fdc.online import wire

START_WAIT = 10         # s for the server to start
STOP_WAIT = 15          # s for the server thread to end
CALL_WAIT = 5           # s for a call inside the server loop
OPEN_TIMEOUT = 5        # s to open a WebSocket
CLOSE_TIMEOUT = 1       # s to close it
WAIT_TIMEOUT = 10.0     # s to wait for a message
SHOWN_TYPES = 15        # message types listed when one does not arrive
DRAIN_TIME = 0.2        # s that drain() reads
MIN_RECV = 0.01         # s: shortest receive wait


class ServerThread:
    """Starts a real GameServer (free port) in a thread with its own loop."""

    def __init__(self, **kw):
        kw.setdefault("web_dir", None)
        kw.setdefault("sim_logs", False)
        self.server = game_server.GameServer(**kw)
        self.loop = None
        self.started = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(
            self.server.run("127.0.0.1", 0, started=self.started.set))
        self.loop.close()

    def __enter__(self):
        self.thread.start()
        if not self.started.wait(START_WAIT):
            raise RuntimeError("the server did not start")
        return self

    def __exit__(self, *exc):
        self.loop.call_soon_threadsafe(self.server.request_stop)
        self.thread.join(STOP_WAIT)

    @property
    def url(self):
        return f"ws://127.0.0.1:{self.server.port}/ws"

    def call(self, fn):
        """Runs fn() inside the server loop and returns its result."""
        fut = asyncio.run_coroutine_threadsafe(_wrap(fn), self.loop)
        return fut.result(CALL_WAIT)


async def _wrap(fn):
    return fn()


def _matches(m, mtype, cond):
    return m["type"] == mtype and (cond is None or cond(m))


class Client:
    """Synchronous test client: it keeps everything that arrives."""

    def __init__(self, url, name=None, player_id=None):
        self.ws = ws_client.connect(url, open_timeout=OPEN_TIMEOUT,
                                    close_timeout=CLOSE_TIMEOUT)
        self.inbox = []
        self.token = None
        self.welcome = None
        if name:
            self.send({"type": wire.HELLO, "username": name,
                       "player_id": player_id or f"test-{name}"})
            self.welcome = self.wait(wire.WELCOME)
            self.token = self.welcome["token"]

    def send(self, msg):
        self.ws.send(json.dumps(msg))

    def send_raw(self, raw):
        self.ws.send(raw)

    def _recv(self, timeout):
        msg = json.loads(self.ws.recv(timeout=timeout))
        self.inbox.append(msg)
        return msg

    def wait(self, mtype, timeout=WAIT_TIMEOUT, cond=None):
        """Waits for a message of that type (meeting cond); keeps the
        others."""
        for k, m in enumerate(self.inbox):
            if _matches(m, mtype, cond):
                return self.inbox.pop(k)
        deadline = time.monotonic() + timeout
        while True:
            m = self._recv_before(deadline, mtype)
            if m is not None and _matches(m, mtype, cond):
                self.inbox.remove(m)
                return m

    def _recv_before(self, deadline, mtype):
        left = deadline - time.monotonic()
        if left <= 0:
            seen = [m["type"] for m in self.inbox][-SHOWN_TYPES:]
            raise AssertionError(f"{mtype} did not arrive; arrived {seen}")
        try:
            return self._recv(left)
        except TimeoutError:
            return None

    def pump(self):
        """Reads what already arrived, without waiting (between UI frames)."""
        while True:
            try:
                self._recv(0)
            except TimeoutError:
                return

    def drain(self, seconds=DRAIN_TIME):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                self._recv(max(MIN_RECV, deadline - time.monotonic()))
            except TimeoutError:
                break
        out, self.inbox = self.inbox, []
        return out

    def close(self):
        try:
            self.ws.close()
        except Exception:  # pylint: disable=broad-exception-caught
            pass    # Already closed: nothing to do in a test.

    def kill(self):
        """Abrupt cut (as if the network fell): no closing handshake."""
        self.ws.socket.close()


def start_match(srv, a_name="Ale", b_name="Bruno", chars=("messi", "pele")):
    """Two clients, one room, both ready: returns (a, b, start of a,
    start of b, room)."""
    a, b = Client(srv.url, a_name), Client(srv.url, b_name)
    a.send({"type": wire.CREATE_ROOM, "name": "Picadito"})
    rid = a.wait(wire.ROOM)["room"]
    b.send({"type": wire.JOIN_ROOM, "room": rid})
    b.wait(wire.ROOM)
    for c, character in ((a, chars[0]), (b, chars[1])):
        c.send({"type": wire.CHOOSE_CHARACTER, "character": character})
    for c in (a, b):
        c.send({"type": wire.READY})
    return a, b, a.wait(wire.MATCH_START), b.wait(wire.MATCH_START), rid
