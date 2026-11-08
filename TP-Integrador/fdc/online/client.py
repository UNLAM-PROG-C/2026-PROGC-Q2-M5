"""Client of the online mode (desktop and browser versions).

NetClient does not use pygame: the online screens ask it every frame. It
keeps the latest known data (name, rooms, current room, match, pause, rival,
result) so no message is lost when the screen changes, and it reconnects by
itself if the connection drops (there are RECONNECT_GRACE seconds to come
back without losing the place).

Below it uses an interchangeable TRANSPORT (Strategy pattern):
  * BrowserTransport: inside the browser (pygbag). It uses the JavaScript
    WebSocket; what arrives is stored in a JS array and Python takes it once
    per frame. There are no threads or processes in the browser.
  * ThreadTransport: desktop version. A reader thread (blocked on the
    network, no busy waiting) puts what arrives in a BOUNDED queue; the
    interface empties it without blocking every frame.
Both deliver events ("open" | "msg" | "closed", data) in order.
"""
import json
import logging
import queue
import sys
import threading
import time

from fdc import config
from fdc.online import endpoint
from fdc.online import wire

log = logging.getLogger("fdc.net")
ONLINE = config.Online
IN_BROWSER = sys.platform == "emscripten"

# Close codes that must NOT cause a reconnection (texts shown on screen).
NO_RETRY_CODES = {
    wire.CLOSE_REPLACED: "Tu sesión se abrió en otra ventana.",
    wire.CLOSE_POLICY: "El servidor cortó la conexión.",
    wire.CLOSE_TRY_AGAIN: "El servidor está lleno: probá más tarde."}
CLOSED_TEXT = "conexión cerrada"      # shown when the server gives no reason


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------
class ThreadTransport:
    """Desktop WebSocket (websockets library) with a reader thread."""

    def __init__(self, url):
        self.url = url
        # Bounded: if it gets full, the thread waits.
        self.inbox = queue.Queue(ONLINE.CLIENT_INBOX)
        self.stop = threading.Event()
        self.ws = None
        self.thread = threading.Thread(target=self._run, name="fdc-network",
                                       daemon=True)
        self.thread.start()

    def _put(self, item):
        while not self.stop.is_set():
            try:
                self.inbox.put(item, timeout=ONLINE.INBOX_PUT_WAIT)
                return
            except queue.Full:
                continue           # the interface empties it next frame

    def _run(self):
        """Body of the reader thread."""
        try:
            # Optional dependency: only the online mode needs it.
            # pylint: disable-next=import-outside-toplevel
            from websockets.sync import client as sync_client
            # pylint: disable-next=import-outside-toplevel
            from websockets import exceptions as ws_exceptions
        except ImportError:
            self._put(("closed", {"code": None, "reason": (
                "Falta la librería websockets: pip install -r "
                "requirements-online.txt")}))
            return
        self._put(("closed", self._read_all(sync_client, ws_exceptions)))

    def _read_all(self, sync_client, ws_exceptions):
        """Reads messages until the connection closes; returns why."""
        code, reason = None, CLOSED_TEXT
        try:
            with _connect(sync_client, self.url) as ws:
                self._read_messages(ws)
                code, reason = ws.close_code, ws.close_reason or reason
        except ws_exceptions.ConnectionClosed as exc:
            if exc.rcvd is not None:
                code, reason = exc.rcvd.code, exc.rcvd.reason or reason
        except Exception as exc:  # pylint: disable=broad-exception-caught
            reason = (f"No se pudo conectar con {self.url} ({exc})"
                      if self.ws is None else str(exc))   # any network failure
        return {"code": code, "reason": reason}

    def _read_messages(self, ws):
        self.ws = ws
        self._put(("open", None))
        for raw in ws:              # blocks on the network (uses no CPU)
            self._put(("msg", raw))
            if self.stop.is_set():
                break

    def receive(self, limit=ONLINE.CLIENT_RECEIVE_BATCH):
        """Takes up to `limit` pending events without blocking."""
        out = []
        for _ in range(limit):
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                break
        return out

    def send(self, text):
        ws = self.ws
        if ws is None:
            return False
        try:
            ws.send(text)
            return True
        except Exception:  # pylint: disable=broad-exception-caught
            return False   # the reader thread reports the drop

    def close(self):
        self.stop.set()
        ws = self.ws
        if ws is not None:
            try:
                ws.close()
            except Exception:  # pylint: disable=broad-exception-caught
                pass       # it was already closed


def _connect(sync_client, url):
    """Opens the desktop WebSocket with the client limits."""
    return sync_client.connect(url, open_timeout=ONLINE.CONNECT_TIMEOUT,
                               close_timeout=ONLINE.CLOSE_TIMEOUT,
                               max_size=ONLINE.CLIENT_MAX_MESSAGE)


_JS = r"""
window.fdcNet = window.fdcNet || {
  socks: {}, next: 1,
  open: function (url) {
    var id = this.next++, box = {ws: null, q: []};
    this.socks[id] = box;
    try { box.ws = new WebSocket(url); }
    catch (e) {
      box.q.push(['closed', {code: null, reason: String(e)}]);
      return id;
    }
    box.ws.onopen = function () { box.q.push(['open', null]); };
    box.ws.onmessage = function (e) { box.q.push(['msg', e.data]); };
    box.ws.onclose = function (e) {
      box.q.push(['closed',
                  {code: e.code, reason: e.reason || 'conexión cerrada'}]);
    };
    return id;
  },
  send: function (id, s) {
    var b = this.socks[id];
    if (b && b.ws && b.ws.readyState === 1) { b.ws.send(s); return 1; }
    return 0;
  },
  take: function (id) {
    var b = this.socks[id];
    if (!b || !b.q.length) return '';
    var s = JSON.stringify(b.q); b.q = []; return s;
  },
  close: function (id) {
    var b = this.socks[id];
    if (b && b.ws) { try { b.ws.close(); } catch (e) {} }
    delete this.socks[id];
  },
  defaultUrl: function () {
    return (location.protocol === 'https:' ? 'wss://' : 'ws://')
        + location.host + '/ws';
  }
};
"""


def _window():
    # pylint: disable-next=import-outside-toplevel
    import platform     # in pygbag, "platform" exposes the JS window object
    return platform.window


class BrowserTransport:
    """Browser WebSocket (pygbag)."""
    js_installed = False      # the JS helper is installed once per page

    def __init__(self, url):
        self.win = _window()
        install_js()
        self.id = int(self.win.fdcNet.open(url))

    def receive(self, limit=ONLINE.CLIENT_RECEIVE_BATCH):
        del limit  # Unused: JS hands everything that arrived.
        raw = str(self.win.fdcNet.take(self.id))
        if not raw:
            return []
        return [tuple(item) for item in json.loads(raw)]

    def send(self, text):
        return bool(self.win.fdcNet.send(self.id, text))

    def close(self):
        self.win.fdcNet.close(self.id)


def install_js():
    """Installs the JS helper once per page."""
    if not BrowserTransport.js_installed:
        _window().eval(_JS)
        BrowserTransport.js_installed = True


def default_url():
    """In the browser, the same site the page came from; on the desktop,
    the address of --server, FDC_SERVER or servidor.txt (see endpoint)."""
    if IN_BROWSER:
        install_js()
        return str(_window().fdcNet.defaultUrl())
    return endpoint.resolve_url()


def default_transport():
    return BrowserTransport if IN_BROWSER else ThreadTransport


# In the browser the token is stored in sessionStorage (that tab only): if
# the page is reloaded by mistake, the player can come back to the same room
# and match within the reconnection time. The desktop does not need it.
_SESSION_KEY = "fdc_session"


def remember_session(username, token):
    if IN_BROWSER and token:
        _window().sessionStorage.setItem(_SESSION_KEY,
                                         json.dumps([username, token]))


def forget_session():
    if IN_BROWSER:
        _window().sessionStorage.removeItem(_SESSION_KEY)


def saved_session():
    """(name, token) stored by this tab, or None."""
    if not IN_BROWSER:
        return None
    try:
        raw = _window().sessionStorage.getItem(_SESSION_KEY)
        name, token = json.loads(str(raw)) if raw else (None, None)
    except (ValueError, TypeError):
        return None
    return (name, token) if name and token else None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
IDLE, CONNECTING, OPEN, RECONNECTING, CLOSED = (
    "idle", "connecting", "connected", "reconnecting", "closed")


class NetClient:
    """Connection with the online server and the latest data it sent."""

    def __init__(self, url=None, transport=None, clock=time.monotonic):
        self.url = url or default_url()
        self.transport_cls = transport or default_transport()
        self.clock = clock
        self.transport, self.status, self.welcomed = None, IDLE, False
        self.fatal = None       # text if the connection was lost for good
        self.wanted_name = self.player_id = None
        self.username = self.tag = self.token = None
        self.display = None     # "Ale #4821": how the others see the player
        self._reset_data()
        self.lost_at, self.rtt = None, None
        self.next_retry = self.next_ping = 0.0
        self.sent = self.received = self.bad = 0
        self._handlers = self._message_handlers()

    def _reset_data(self):
        self.rooms = []
        self.room = None        # detail of the room the player is in
        self.match = None       # latest match_start
        self.pause = {"type": wire.PAUSE_INFO, "status": wire.PAUSE_NONE}
        self.opponent = None
        self.result = None      # latest match_over
        self.room_info = None   # room data on the server (match F3 panel)
        # Latest server error (name taken, password...).
        self.last_error = None

    # ------------------------------------------------------------ connection
    def connect(self, username, player_id=None):
        """Opens the connection (or reuses it) and introduces itself with
        the profile name."""
        self.wanted_name = username
        self.player_id = player_id
        self.fatal = None
        if self.status == OPEN:
            self.send(self._hello())
        elif self.status not in (CONNECTING, RECONNECTING):
            self.status = CONNECTING
            self._open()

    def _hello(self):
        """Hello message: the name, the tag and the protocol it speaks."""
        hello = {"type": wire.HELLO, "username": self.wanted_name,
                 "player_id": self.player_id,
                 "protocol": config.PROTOCOL_VERSION}
        if self.token:
            hello["token"] = self.token          # recover the session
        return hello

    def _open(self):
        self.transport = self.transport_cls(self.url)

    def close(self):
        """Voluntary exit: no retries."""
        if self.transport is not None:
            self.transport.close()
        self.transport = None
        self.status = IDLE
        self.welcomed = False
        self.token = None
        self.room = self.match = self.result = self.room_info = None
        forget_session()

    @property
    def connected(self):
        return self.status == OPEN and self.welcomed

    # --------------------------------------------------------------- sending
    def send(self, msg):
        if self.transport is None or self.status != OPEN:
            return False
        ok = self.transport.send(wire.encode(msg))
        self.sent += ok
        return ok

    def is_me(self, member):
        """A room may hold two people with the same name: the name and the
        tag are compared."""
        return (member["username"] == self.username
                and member.get("tag") == self.tag)

    def send_input(self, p, seq=None):
        """Controls snapshot; `seq` numbers it for the client's prediction."""
        msg = {"type": wire.INPUT, "p": p}
        if seq is not None:
            msg["seq"] = seq
        self.send(msg)

    def leave_room(self):
        self.send({"type": wire.LEAVE_ROOM})
        self.room = None
        self.match = None

    def abandon(self):
        self.send({"type": wire.ABANDON})
        self.room = None
        self.match = None

    # ------------------------------------------------------------- receiving
    def poll(self):
        """Without blocking: handles what arrived; returns the new
        messages."""
        now = self.clock()
        out = self._receive(now) if self.transport is not None else []
        if self.status == RECONNECTING:
            self._retry(now)
        if self.connected and now >= self.next_ping:
            self.next_ping = now + ONLINE.PING_EVERY
            self.send({"type": wire.PING, "t": now})
        return out

    def _receive(self, now):
        out = []
        for kind, data in self.transport.receive():
            if kind == "open":
                self._on_open()
            elif kind == "msg":
                msg = self._decode(data)
                if msg is not None:
                    self._apply(msg, now)
                    out.append(msg)
            elif kind == "closed":
                self._on_closed(data or {}, now)
                break
        return out

    def _on_open(self):
        self.status = OPEN
        self.send(self._hello())

    def _decode(self, data):
        try:
            msg = wire.decode(data)
        except wire.WireError:
            self.bad += 1
            return None
        self.received += 1
        return msg

    def _retry(self, now):
        if now - self.lost_at > ONLINE.RECONNECT_GRACE:
            self._give_up("Se perdió la conexión con el servidor.")
        elif self.transport is None and now >= self.next_retry:
            self.next_retry = now + ONLINE.RETRY_EVERY
            self._open()

    def _on_closed(self, info, now):
        if self.fatal:                  # it already gave up (version refused)
            return
        if self.transport is not None:
            self.transport.close()
        self.transport = None
        code, reason = info.get("code"), info.get("reason") or ""
        if self.status == IDLE:
            return
        if self.welcomed and code not in NO_RETRY_CODES:
            self._start_retrying(now, reason)
            return
        self._give_up(NO_RETRY_CODES.get(code) or reason
                      or "No se pudo conectar con el servidor.")

    def _start_retrying(self, now, reason):
        if self.status != RECONNECTING:
            self.status = RECONNECTING
            self.lost_at = now
            self.next_retry = now + ONLINE.FIRST_RETRY_DELAY
            log.info("connection lost (%s): retrying", reason)

    def _give_up(self, text):
        log.warning("connection lost: %s", text)
        if self.transport is not None:
            self.transport.close()
        self.transport = None
        self.status = CLOSED
        # The message always says which host was tried.
        self.fatal = text if self.url in text else f"{text} ({self.url})"
        self.welcomed = False

    # ------------------------------------------- what the screens read
    def _message_handlers(self):
        """Each message type updates its data (the screens read it)."""
        return {
            wire.WELCOME: self._on_welcome, wire.ROOMS: self._on_rooms,
            wire.ROOM: self._on_room, wire.MATCH_START: self._on_match_start,
            wire.PAUSE_INFO: self._on_pause, wire.OPPONENT: self._on_opponent,
            wire.MATCH_OVER: self._on_match_over,
            wire.ROOM_INFO: self._on_room_info, wire.ERROR: self._on_error,
            wire.PONG: self._on_pong,
        }

    def _apply(self, msg, now):
        handler = self._handlers.get(msg["type"])
        if handler is not None:
            handler(msg, now)

    def _on_welcome(self, msg, now):
        del now  # Unused.
        self.welcomed = True
        self.username = msg["username"]
        self.tag = msg.get("tag")
        self.display = msg.get("display") or self.username
        self.token = msg.get("token")
        self.lost_at = None
        remember_session(self.username, self.token)
        if not msg.get("restored"):
            self.room = self.match = None    # new session: no room or match

    def _on_rooms(self, msg, now):
        del now  # Unused.
        self.rooms = msg["rooms"]
        self.room = None        # only whoever is on the list receives it

    def _on_room(self, msg, now):
        del now  # Unused.
        self.room = msg

    def _on_match_start(self, msg, now):
        del now  # Unused.
        if self.match is None or self.match["match"] != msg["match"]:
            self.result = None
            self.pause = {"type": wire.PAUSE_INFO, "status": wire.PAUSE_NONE}
            self.opponent = None
        self.match = msg

    def _on_pause(self, msg, now):
        self.pause = dict(msg, at=now)

    def _on_opponent(self, msg, now):
        self.opponent = dict(msg, at=now)

    def _on_match_over(self, msg, now):
        del now  # Unused.
        self.result = msg
        self.match = None
        self.room_info = None

    def _on_room_info(self, msg, now):
        del now  # Unused.
        self.room_info = msg

    def _on_error(self, msg, now):
        self.last_error = dict(msg, at=now)
        if msg.get("code") == wire.CODE_VERSION:
            # Another version of the game: there is nothing to retry.
            self._give_up(msg.get("message") or "Versión incompatible.")

    def _on_pong(self, msg, now):
        if isinstance(msg.get("t"), (int, float)):
            self.rtt = max(0.0, now - msg["t"])

    # --------------------------------------------------------------- helpers
    def countdown(self, info):
        """Seconds left according to a message with "left" and its
        arrival time."""
        if not info or info.get("left") is None:
            return None
        return max(0.0, info["left"]
                   - (self.clock() - info.get("at", self.clock())))

    def reconnect_left(self):
        if self.status != RECONNECTING or self.lost_at is None:
            return None
        return max(0.0, ONLINE.RECONNECT_GRACE - (self.clock() - self.lost_at))

    def debug_lines(self):
        """Lines of the F3 panel about the connection (shown in Spanish)."""
        rtt = "-"
        if self.rtt is not None:
            rtt = f"{self.rtt * config.MS_PER_SECOND:.0f} ms"
        return {"url": self.url, "status": self.status,
                "user": self.display or "-", "rtt": rtt,
                "traffic": f"{self.sent} enviados / {self.received} "
                           f"recibidos / {self.bad} inválidos"}
