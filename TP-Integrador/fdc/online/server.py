"""Server of the online mode: 1 against 1 rooms over WebSocket.

Concurrency (see docs/CONCURRENCY.md):
  * ONE server process with an asyncio loop. It serves every connection:
    each one has a coroutine that READS and another that WRITES
    (fdc/online/session.py). Only this loop touches the Lobby and the
    sessions, so no locks are needed.
  * ONE simulation process PER ROOM IN PLAY: the same of the local version
    (fdc.sim.process.simulation_main, with bounded queues, ACKs, match
    numbers and shutdown Event), handled with SimLink. A stuck room does not
    slow the others and each room can use another core.
  * One BRIDGE per room (asyncio task at 60 Hz, fdc/online/room_runner.py):
    it takes the controls of the two browsers to its process and forwards
    states (30 per second) and events.
  * Launching or closing a process may block: it runs in an executor thread
    (run_in_executor) so the loop is not slowed down.

It also serves, on the same port:
  * the files of the web client (build/web, made with tools/build_web.py);
  * the server PANEL (/status, fdc/online/panel.py): live processes,
    threads, tasks, rooms and traffic, to see the concurrency while playing.
    The full view (/status/full, with names) asks for a password.
"""
import argparse
import asyncio
import collections
import ctypes
import http
import json
import logging
import mimetypes
import os
import pathlib
import socket
import sys
import time

from websockets import datastructures
from websockets import exceptions as ws_exceptions
from websockets import http11
from websockets.asyncio import server as ws_server

from fdc import config
from fdc.online import lobby
from fdc.online import panel
from fdc.online import room_runner
from fdc.online import session as session_module
from fdc.online import wire

log = logging.getLogger("fdc.server")
ONLINE = config.Online

DEFAULT_WEB_DIR = os.path.join(config.ROOT_DIR, "build", "web")
PANEL_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "panel.html")
# /status.json: the data the panel page reads.
JSON_SUFFIX = ".json"
# Listening on all interfaces: not usable as a browser address.
ALL_INTERFACES = ("0.0.0.0", "", "::")
LOOPBACK = "127.0.0.1"
# Documentation address (RFC 5737) and any port: "connecting" a UDP socket
# sends nothing, it only tells which local network IP the computer uses.
LAN_PROBE = ("192.0.2.1", 9)
LOG_FORMAT = ("%(asctime)s [%(processName)s pid=%(process)d] %(levelname)s "
              "%(name)s: %(message)s")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/octet-stream", ".apk")
# The landing (spec-landing 2.2.4): Python does not know .webp, and a wrong
# type makes the browser download the picture instead of painting it.
mimetypes.add_type("image/webp", ".webp")
# Cache of the static files: the pictures and the clip of the landing can be
# kept for a while; the page, the style, the script and the data cannot.
CACHE_LONG = "public, max-age=3600"
CACHE_NONE = "no-cache"
CACHE_PREFIXES = ("img/", "media/")     # folders with the heavy media
# Command line options of server.py.
COMMAND_LINE = (
    ("--host", {"default": ALL_INTERFACES[0],
                "help": "interface to listen on (0.0.0.0 = all)"}),
    ("--port", {"type": int, "default": ONLINE.PORT}),
    ("--web", {"default": DEFAULT_WEB_DIR,
               "help": "folder of the compiled web client"}),
    ("--duration", {"type": float, "default": None,
                    "help": "match length (s)"}),
    ("--grace", {"type": float, "default": ONLINE.RECONNECT_GRACE,
                 "help": "seconds to come back after a drop before losing "
                         "by forfeit"}),
    ("--panel-password", {
        "default": ONLINE.PANEL_PASSWORD,
        "help": "password of the full panel view (/status/full); also the "
                "FDC_PANEL_PASSWORD variable. Without it there is only the "
                "public view"}),
)
# Limits of the WebSocket server (message size and keepalive pings).
SERVE_OPTIONS = {"max_size": ONLINE.MAX_MESSAGE_BYTES,
                 "ping_interval": ONLINE.KEEPALIVE_EVERY,
                 "ping_timeout": ONLINE.KEEPALIVE_TIMEOUT}
# Message types handled by the room bridge during a match.
MATCH_TYPES = (wire.INPUT, wire.PAUSE_REQUEST, wire.PAUSE_READY)


def set_nodelay(ws):
    """Sends every state as soon as it is written (no Nagle buffering).

    At 60 states per second a delayed ACK of the other side could hold two
    states together for tens of milliseconds: that is latency the player
    feels. asyncio already turns TCP_NODELAY on for the sockets it creates,
    so this is explicit (and checked by the tests) rather than new.
    """
    transport = getattr(ws, "transport", None)
    sock = transport.get_extra_info("socket") if transport else None
    if sock is not None:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


def begin_precise_timers():
    """Windows: 1 ms timers for this process (True if it could).

    The system timer is ~15.6 ms by default, so an asyncio sleep of 1/120 s
    lands at 15.6 ms: the bridge of each room would run at ~64 Hz and the
    states would come out at ~34 per second. With 1 ms resolution the bridge
    keeps its 120 Hz and the states leave at 60. It is system wide while the
    server runs; end_precise_timers() undoes it.
    """
    if sys.platform != "win32":
        return False
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except (AttributeError, OSError):
        return False
    return True


def end_precise_timers(began):
    """Undoes begin_precise_timers()."""
    if began:
        ctypes.windll.winmm.timeEndPeriod(1)


class GameServer:
    """Connections, sessions, rooms, panel and static files."""

    def __init__(self, web_dir=DEFAULT_WEB_DIR, duration=None,
                 grace=ONLINE.RECONNECT_GRACE, pause_max=ONLINE.PAUSE_MAX,
                 seed=None, rng=None, sim_logs=True,
                 panel_password=ONLINE.PANEL_PASSWORD):
        self.lobby = lobby.Lobby(rng)
        self.web_dir = pathlib.Path(web_dir).resolve() if web_dir else None
        self.duration, self.seed, self.sim_logs = duration, seed, sim_logs
        self.grace, self.pause_max = grace, pause_max
        self.panel_password = panel_password or ""
        # id -> named Session, token -> Session and room -> RoomRunner.
        self.sessions, self.tokens, self.runners = {}, {}, {}
        self.tasks = set()      # loose tasks (kept so they are not lost)
        self.port = self.stopped = None
        self._init_panel_data()

    def _init_panel_data(self):
        self.connections = 0
        self.started_at = time.monotonic()
        # Messages and states (totals, for the panel)...
        self.traffic = collections.Counter()
        self.rates = {}         # ...and the same per second
        self.process_log = collections.deque(maxlen=ONLINE.PANEL_LOG_SIZE)

    def spawn(self, coro):
        """Starts a task and keeps a reference until it ends."""
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def log_process(self, room_id, what, pid, detail=""):
        """Process log for the panel (no player names; texts are shown)."""
        self.process_log.appendleft({"time": time.strftime("%H:%M:%S"),
                                     "room": room_id, "event": what,
                                     "pid": pid, "detail": detail})

    # ------------------------------------------------------------------ HTTP
    async def http(self, connection, request):
        """HTTP requests: WebSocket handshake, panel or web client files."""
        path = request.path.split("?", 1)[0]
        if path == ONLINE.WS_PATH:
            return None                 # the WebSocket handshake goes on
        host = request.headers.get("Host", "")
        if host.split(":")[0].lower() == "localhost":
            return self._to_loopback(host, request.path)
        if path in (ONLINE.PANEL_PATH, ONLINE.PANEL_PATH + JSON_SUFFIX):
            return self._panel(path, full=False)
        if path in (ONLINE.PANEL_FULL_PATH,
                    ONLINE.PANEL_FULL_PATH + JSON_SUFFIX):
            return self._full_panel(connection, request, path)
        return await asyncio.to_thread(self._static, connection, path)

    def _to_loopback(self, host, path):
        """pygbag takes "localhost:8..." as ITS development server and looks
        for its packages on localhost:8000: the game does not start. The
        same computer as 127.0.0.1 does not have that problem."""
        port = host.split(":")[1] if ":" in host else str(self.port)
        location = f"http://{LOOPBACK}:{port}{path}"
        return _response(http.HTTPStatus.FOUND, b"",
                         extra=[("Location", location)])

    def _full_panel(self, connection, request, path):
        if not self.panel_password:
            return connection.respond(
                http.HTTPStatus.NOT_FOUND,
                "La vista completa del panel está desactivada: iniciá el "
                "servidor con --panel-password CLAVE (o la variable "
                "FDC_PANEL_PASSWORD).\n")
        if not panel.authorized(request, self.panel_password):
            return _response(
                http.HTTPStatus.UNAUTHORIZED,
                "Hace falta la contraseña del panel.\n".encode(),
                extra=[("WWW-Authenticate", 'Basic realm="Panel de Futbol '
                        'De Cabeza", charset="UTF-8"')])
        return self._panel(path, full=True)

    def _panel(self, path, full):
        if path.endswith(JSON_SUFFIX):
            body = json.dumps(panel.panel_data(self, full),
                              ensure_ascii=False).encode("utf-8")
            return _response(http.HTTPStatus.OK, body,
                             "application/json; charset=utf-8")
        with open(PANEL_PAGE, "rb") as fh:
            return _response(http.HTTPStatus.OK, fh.read(),
                             "text/html; charset=utf-8")

    def _static(self, connection, path):
        """A file of the web client (never outside its folder)."""
        if self.web_dir is None or not (self.web_dir / "index.html").is_file():
            return connection.respond(
                http.HTTPStatus.NOT_FOUND, "El cliente web no está "
                "compilado. Ejecutá: python tools/build_web.py\n")
        if path.endswith("/"):
            path += "index.html"
        target = (self.web_dir / path.lstrip("/")).resolve()
        if self.web_dir not in target.parents or not target.is_file():
            return connection.respond(http.HTTPStatus.NOT_FOUND, "No existe.\n")
        return _response(http.HTTPStatus.OK, target.read_bytes(),
                         _content_type(target.name),
                         cache=_cache_control(path))

    async def _stats_loop(self):
        """Messages per second for the panel (one per PANEL_REFRESH)."""
        previous, last = collections.Counter(), time.monotonic()
        while True:
            await asyncio.sleep(ONLINE.PANEL_REFRESH)
            now = time.monotonic()
            elapsed = now - last
            self.rates = {k: (v - previous[k]) / elapsed
                          for k, v in self.traffic.items()}
            previous, last = collections.Counter(self.traffic), now

    # ----------------------------------------------------------- connections
    async def handler(self, ws):
        """Reader task of one connection: hello first, then messages."""
        if await _refuse_if_full(ws, self.connections):
            return
        self.connections += 1
        session, stamps = None, collections.deque()
        pending = self._new_session(ws)
        try:
            session = await self._wait_hello(ws, pending, stamps)
            await self._serve(ws, session, pending, stamps)
        except (ws_exceptions.ConnectionClosed, asyncio.TimeoutError):
            pass
        finally:
            self.connections -= 1
            self._after_connection(session, pending, ws)

    def _new_session(self, ws):
        """Session of a connection that has not introduced itself yet."""
        set_nodelay(ws)
        pending = session_module.Session(self.traffic)
        pending.attach(ws)
        return pending

    async def _serve(self, ws, session, pending, stamps):
        """Reads and routes the messages of an introduced session."""
        if session is not pending:
            pending.detach()
        async for raw in ws:
            msg = self._decode(session, raw, stamps)
            if msg is not None:
                self.route(session, msg)

    async def _wait_hello(self, ws, pending, stamps):
        """The client must introduce itself in time (it gets more time while
        it keeps trying). Returns its session."""
        deadline = time.monotonic() + ONLINE.HELLO_TIMEOUT
        while True:
            wait = max(ONLINE.HELLO_MIN_WAIT, deadline - time.monotonic())
            raw = await asyncio.wait_for(ws.recv(), wait)
            deadline = time.monotonic() + ONLINE.HELLO_TIMEOUT
            session = self._first_message(
                ws, pending, self._decode(pending, raw, stamps))
            if session is not None:
                return session

    def _first_message(self, ws, pending, msg):
        """Only "hello" is accepted before having a name."""
        if msg is None:
            return None
        if msg["type"] != wire.HELLO:
            pending.send({"type": wire.ERROR, "code": "no_name",
                          "message": "Primero hay que elegir un nombre "
                                     "de usuario."})
            return None
        if msg.get("protocol") != config.PROTOCOL_VERSION:
            _refuse_version(pending)
            return None
        return self._hello(pending, ws, msg)

    def _after_connection(self, session, pending, ws):
        if session is None:
            pending.detach()
        else:
            self._connection_lost(session, ws)

    def _decode(self, session, raw, stamps):
        """Message rate limit and validation. None if it is dropped."""
        self.traffic["messages_received"] += 1
        if _too_many(stamps, time.monotonic()):
            log.warning("too many messages from %s: closing it",
                        session.username or "?")
            asyncio.ensure_future(session.ws.close(wire.CLOSE_POLICY,
                                                   "too many messages"))
            return None
        try:
            return wire.decode(raw, wire.CLIENT_TYPES)
        except wire.WireError as exc:
            _invalid_message(session, exc)
            return None

    def _hello(self, pending, ws, msg):
        """Returns the session if the hello was right (new or recovered),
        else None."""
        token = msg.get("token")
        old = self.tokens.get(token) if isinstance(token, str) else None
        if old is not None:
            return self._restore(old, ws)
        return self._new_user(pending, msg)

    def _new_user(self, pending, msg):
        """First hello of a session: the Lobby gives it name and tag."""
        out = self.lobby.handle(pending.id, dict(_hello_fields(msg),
                                                 type="hello"))
        welcome = next((m for _, m in out if m["type"] == wire.WELCOME), None)
        if welcome is None:
            for _, reply in out:        # the error of the Lobby
                pending.send(reply)
            return None
        self._register(pending, welcome)
        self.deliver(out)
        log.info("%s entered (%s)", pending.username, pending.id)
        return pending

    def _register(self, pending, welcome):
        pending.identity = {k: welcome[k] for k in ("username", "tag",
                                                    "display")}
        pending.username = welcome["display"]
        welcome.update(token=pending.token, restored=False)
        self.sessions[pending.id] = pending
        self.tokens[pending.token] = pending

    def _restore(self, old, ws):
        """Somebody who had dropped comes back: name, room and match."""
        _take_over(old, ws)
        old.attach(ws)
        old.send({"type": wire.WELCOME, **old.identity, "token": old.token,
                  "restored": True})
        self.deliver(self.lobby.set_connected(old.id, True))
        self.deliver(self.lobby.resync(old.id))
        runner, side = self._runner_side(old.id)
        if runner is not None and side is not None:
            runner.player_back(side, old)
        log.info("%s connected again", old.username)
        return old

    def _runner_side(self, sid):
        room = self.lobby.room_of_conn(sid)
        runner = self.runners.get(room.id) if room else None
        side = runner.side_of(sid) if runner else None
        return runner, side

    # --------------------------------------------------------------- routing
    def route(self, session, msg):
        """Sends each message to whoever handles it."""
        kind = msg["type"]
        if kind == wire.PING:
            session.send({"type": wire.PONG, "t": msg.get("t")})
        elif kind == wire.HELLO:
            session.send({"type": wire.ERROR, "code": "already_named",
                          "message": "Ya elegiste tu nombre."})
        elif kind in MATCH_TYPES:
            self._match_message(session, msg)
        else:
            self._lobby_message(session, msg)

    def _match_message(self, session, msg):
        """Controls and pause messages (ignored outside a match)."""
        runner, side = self._runner_side(session.id)
        if runner is None or side is None:
            return
        kind = msg["type"]
        try:
            if kind == wire.INPUT:
                runner.set_input(side, *wire.clean_controls(msg))
            elif kind == wire.PAUSE_REQUEST:
                runner.request_pause(side)
            else:
                runner.pause_ready(side)
        except wire.WireError as exc:
            _invalid_message(session, exc)

    def _lobby_message(self, session, msg):
        """Rooms; leaving during a match is a forfeit."""
        kind = msg["type"]
        room = self.lobby.room_of_conn(session.id)
        if kind == wire.ABANDON or (kind == wire.LEAVE_ROOM and room is not None
                                    and room.state == lobby.PLAYING):
            self._abandon(session, room)
            return
        self.deliver(self.lobby.handle(session.id, msg))
        if kind == wire.LEAVE_ROOM and room is not None:
            self.room_changed(room.id)

    def _abandon(self, session, room):
        runner, side = self._runner_side(session.id)
        if runner is not None and side is not None:
            runner.forfeit(side)        # loses and leaves the room
        if room is not None:
            self.deliver(self.lobby.handle(session.id,
                                           {"type": wire.LEAVE_ROOM}))
            self.room_changed(room.id)

    def deliver(self, out):
        """Sends what the Lobby returned and starts the matches that
        begin."""
        starts = {}
        for targets, msg in out:
            text = wire.encode(msg)
            for sid in targets:
                session = self.sessions.get(sid)
                if session is not None:
                    session.send_text(text)
            if msg["type"] == wire.MATCH_START:
                starts.setdefault(msg["room"], {})[msg["you"]] = msg
        for room_id, msgs in starts.items():
            self._start_match(room_id, msgs)

    def _start_match(self, room_id, msgs):
        room = self.lobby.rooms[room_id]
        any_msg = next(iter(msgs.values()))
        players = sorted(any_msg["players"], key=lambda p: p["side"])
        sids = _sids_by_side(room)
        runner = self.runners.get(room_id)
        if runner is None:
            runner = self.runners[room_id] = room_runner.RoomRunner(self,
                                                                   room_id)
        self.spawn(runner.begin(
            any_msg["match"], sids, [p["display"] for p in players],
            [p["character"] for p in players],
            [msgs[side] for side in range(lobby.MAX_PLAYERS)]))

    def room_changed(self, room_id):
        """If the room has fewer than 2 people, its process is not needed."""
        room = self.lobby.rooms.get(room_id)
        if room is None or len(room.members) < lobby.MAX_PLAYERS:
            runner = self.runners.get(room_id)
            if runner is not None:
                self.drop_runner(room_id, runner)

    def drop_runner(self, room_id, runner):
        if self.runners.get(room_id) is runner:
            del self.runners[room_id]
        self.spawn(runner.close())

    # ------------------------------------------------------ connection drops
    def _connection_lost(self, session, ws):
        if session.ws is not ws:
            return              # a reconnection already replaced it
        session.detach()
        log.info("%s disconnected: %.0f s to come back", session.username,
                 self.grace)
        self.deliver(self.lobby.set_connected(session.id, False))
        runner, side = self._runner_side(session.id)
        if runner is not None and side is not None:
            runner.player_away(side, time.monotonic() + self.grace)
        session.expire_task = self.spawn(self._expire_later(session))

    async def _expire_later(self, session):
        """Reconnection time: if it does not come back, it loses."""
        await asyncio.sleep(self.grace)
        if session.ws is not None:
            return
        session.expire_task = None
        runner, side = self._runner_side(session.id)
        if runner is not None and side is not None:
            runner.forfeit(side)        # it did not come back: the other wins
        self._forget(session)

    def _forget(self, session):
        """Frees the place of a session that did not come back."""
        room = self.lobby.room_of_conn(session.id)
        self.deliver(self.lobby.disconnect(session.id))
        if room is not None:
            self.room_changed(room.id)
        self.sessions.pop(session.id, None)
        self.tokens.pop(session.token, None)
        log.info("%s did not come back: its place was freed",
                 session.username)

    # ------------------------------------------------------ start and stop
    async def run(self, host=ALL_INTERFACES[0], port=ONLINE.PORT,
                  started=None):
        """Serves until request_stop(); then closes every room."""
        self.stopped = asyncio.Event()
        precise = begin_precise_timers()
        stats = asyncio.create_task(self._stats_loop())
        try:
            await self._serve_until_stopped(host, port, started, stats)
        finally:
            end_precise_timers(precise)

    async def _serve_until_stopped(self, host, port, started, stats):
        """Opens the port and runs until request_stop()."""
        async with ws_server.serve(self.handler, host, port,
                                   process_request=self.http,
                                   **SERVE_OPTIONS) as srv:
            self.port = srv.sockets[0].getsockname()[1]
            self._announce(host)
            if started is not None:
                started()
            await self._until_stopped(stats)

    async def _until_stopped(self, stats):
        try:
            await self.stopped.wait()
        finally:
            stats.cancel()
            await self.close_all()

    def _announce(self, host):
        urls = self.urls(host)
        log.info("server ready. Open in the browser: %s", "  or  ".join(urls))
        log.info("server panel: %s%s", urls[0], ONLINE.PANEL_PATH)

    def urls(self, host):
        """Addresses to open the game (0.0.0.0 is not a browser address)."""
        if host not in ALL_INTERFACES:
            return [f"http://{host}:{self.port}"]
        out = [f"http://{LOOPBACK}:{self.port}"]
        lan = _lan_address()
        if lan is not None:
            out.append(f"http://{lan}:{self.port} (from another computer "
                       "on your network)")
        return out

    def request_stop(self):
        if self.stopped is not None:
            self.stopped.set()

    async def close_all(self):
        """Coordinated shutdown: each room closes its process (with a time
        limit)."""
        for session in list(self.sessions.values()):
            if session.expire_task is not None:
                session.expire_task.cancel()    # reconnection times no more
            session.detach()
        runners = list(self.runners.values())
        self.runners.clear()
        await asyncio.gather(*(r.close() for r in runners),
                             return_exceptions=True)
        # Rooms that were already closing or starting: wait for them.
        pending = [t for t in self.tasks if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=ONLINE.SHUTDOWN_TASKS_WAIT)
        log.info("server closed (%d rooms in play closed)", len(runners))


async def _refuse_if_full(ws, connections):
    """Closes the connection if the server is full. True if it did."""
    if connections < ONLINE.MAX_CONNECTIONS:
        return False
    await ws.close(wire.CLOSE_TRY_AGAIN, "server full")
    return True


def _sids_by_side(room):
    """Session ids of the room members, ordered by side."""
    sids = [None] * lobby.MAX_PLAYERS
    for member in room.members:
        sids[member.side] = member.conn
    return sids


def _hello_fields(msg):
    return {"username": msg.get("username"),
            "player_id": msg.get("player_id")}


def _take_over(old, ws):
    """Closes the old connection of a session and stops its timer."""
    if old.ws is not None and old.ws is not ws:
        asyncio.ensure_future(old.ws.close(wire.CLOSE_REPLACED,
                                           "session opened elsewhere"))
    if old.expire_task is not None:
        old.expire_task.cancel()
        old.expire_task = None


def _too_many(stamps, now):
    """Counts the messages of the last RATE_WINDOW s; True if too many."""
    stamps.append(now)
    while stamps and now - stamps[0] > ONLINE.RATE_WINDOW:
        stamps.popleft()
    return len(stamps) > ONLINE.MAX_MESSAGES_PER_SEC


def _refuse_version(session):
    """A client of another version cannot play: it is told why and closed."""
    session.send({"type": wire.ERROR, "code": wire.CODE_VERSION,
                  "message": f"Tu versión del juego no coincide con el "
                             f"servidor: actualizá a la {config.GAME_VERSION} "
                             f"para jugar online."})
    asyncio.ensure_future(session.ws.close(wire.CLOSE_POLICY,
                                           "game version"))


def _invalid_message(session, exc):
    log.info("invalid message from %s: %s", session.username or "?", exc)
    session.send({"type": wire.ERROR, "code": "invalid_message",
                  "message": "Mensaje inválido."})


def _lan_address():
    """IP of this computer on the local network, or None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(LAN_PROBE)    # sends nothing: it picks the network
            lan = probe.getsockname()[0]
    except OSError:
        return None
    return None if lan.startswith("127.") else lan


def _content_type(name):
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype == "application/javascript":
        ctype += "; charset=utf-8"
    return ctype


def _cache_control(path):
    """A while for the pictures and the clip; revalidate everything else."""
    if path.lstrip("/").startswith(CACHE_PREFIXES):
        return CACHE_LONG
    return CACHE_NONE


def _response(status, body, ctype="text/plain; charset=utf-8", extra=(),
              cache=CACHE_NONE):
    headers = datastructures.Headers([
        ("Content-Type", ctype), ("Content-Length", str(len(body))),
        ("Cache-Control", cache), ("Connection", "close"), *extra])
    return http11.Response(status.value, status.phrase, headers, body)


def setup_logging():
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        handlers.append(logging.FileHandler(
            os.path.join(config.LOG_DIR, "server.log"), mode="a",
            encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT,
                        handlers=handlers, force=True)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Online server of Futbol De Cabeza (1 vs 1 rooms).")
    for flag, options in COMMAND_LINE:
        parser.add_argument(flag, **options)
    return parser.parse_args(argv)


def main(argv=None):
    """Entry point of server.py."""
    args = parse_args(argv)
    setup_logging()
    server = GameServer(web_dir=args.web, duration=args.duration,
                        grace=args.grace, panel_password=args.panel_password)
    try:
        asyncio.run(server.run(args.host, args.port))
    except KeyboardInterrupt:
        log.info("terminal interrupt: server stopped")
    except OSError as exc:
        log.error("could not open port %s (is another server running?): %s",
                  args.port, exc)
        return 1
    return 0
