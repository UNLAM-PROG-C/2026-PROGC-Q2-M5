"""Cliente del modo online (versión de escritorio y navegador).

NetClient no usa pygame: las pantallas online lo consultan en cada cuadro.
Guarda lo último que se sabe (nombre, salas, sala actual, partido, pausa,
rival, resultado) para que ningún mensaje se pierda al cambiar de pantalla, y
se reconecta solo si la conexión se corta (hay RECONNECT_GRACE segundos para
volver sin perder el lugar).

Por debajo usa un TRANSPORTE intercambiable:
  * BrowserTransport: dentro del navegador (pygbag). Usa el WebSocket de
    JavaScript; lo que llega se acumula en un arreglo JS y Python lo retira una
    vez por cuadro. En el navegador no hay hilos ni procesos.
  * ThreadTransport: versión de escritorio. Un hilo lector (bloqueado en la
    red, sin espera activa) deja lo que llega en una cola ACOTADA; la interfaz
    la vacía sin bloquear en cada cuadro.
Los dos entregan eventos ("open" | "msg" | "closed", dato) en orden.
"""
import json
import logging
import queue
import sys
import threading
import time

from ..config import Online
from . import wire as W

log = logging.getLogger("fdc.net")

IN_BROWSER = sys.platform == "emscripten"

# códigos de cierre que NO deben provocar reconexión
NO_RETRY_CODES = {4000: "Tu sesión se abrió en otra ventana.", 1008: "El servidor cortó la conexión.",
                  1013: "El servidor está lleno: probá más tarde."}


# ---------------------------------------------------------------------------
# Transportes
# ---------------------------------------------------------------------------
class ThreadTransport:
    """WebSocket de escritorio (librería websockets) con un hilo lector."""

    def __init__(self, url):
        self.url = url
        self.inbox = queue.Queue(Online.CLIENT_INBOX)   # acotada: si se llena, el hilo espera
        self.stop = threading.Event()
        self.ws = None
        self.thread = threading.Thread(target=self._run, name="fdc-red", daemon=True)
        self.thread.start()

    def _put(self, item):
        while not self.stop.is_set():
            try:
                self.inbox.put(item, timeout=0.2)
                return
            except queue.Full:
                continue           # la interfaz la vacía en el próximo cuadro

    def _run(self):
        try:
            from websockets.sync.client import connect
            from websockets.exceptions import ConnectionClosed
        except ImportError:
            self._put(("closed", {"code": None, "reason": "Falta la librería websockets: "
                                  "pip install -r requirements-online.txt"}))
            return
        code, reason = None, "conexión cerrada"
        try:
            with connect(self.url, open_timeout=5, close_timeout=1, max_size=2 ** 20) as ws:
                self.ws = ws
                self._put(("open", None))
                for raw in ws:                    # bloquea en la red (no consume CPU)
                    self._put(("msg", raw))
                    if self.stop.is_set():
                        break
                code, reason = ws.close_code, ws.close_reason or reason
        except ConnectionClosed as exc:
            if exc.rcvd is not None:
                code, reason = exc.rcvd.code, exc.rcvd.reason or reason
        except Exception as exc:  # noqa: BLE001 - cualquier falla de red se informa igual
            reason = (f"No se pudo conectar con {self.url} ({exc})" if self.ws is None else str(exc))
        self._put(("closed", {"code": code, "reason": reason}))

    def receive(self, limit=400):
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
        except Exception:  # noqa: BLE001 - el hilo lector informa el corte
            return False

    def close(self):
        self.stop.set()
        ws = self.ws
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass


_JS = r"""
window.fdcNet = window.fdcNet || {
  socks: {}, next: 1,
  open: function (url) {
    var id = this.next++, box = {ws: null, q: []};
    this.socks[id] = box;
    try { box.ws = new WebSocket(url); }
    catch (e) { box.q.push(['closed', {code: null, reason: String(e)}]); return id; }
    box.ws.onopen = function () { box.q.push(['open', null]); };
    box.ws.onmessage = function (e) { box.q.push(['msg', e.data]); };
    box.ws.onclose = function (e) { box.q.push(['closed', {code: e.code, reason: e.reason || 'conexión cerrada'}]); };
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
    return (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
  }
};
"""


def _window():
    import platform               # en pygbag, "platform" expone el objeto window de JS
    return platform.window


class BrowserTransport:
    """WebSocket del navegador (pygbag)."""
    _installed = False

    def __init__(self, url):
        self.win = _window()
        install_js()
        self.id = int(self.win.fdcNet.open(url))

    def receive(self, limit=400):
        raw = str(self.win.fdcNet.take(self.id))
        if not raw:
            return []
        return [tuple(item) for item in json.loads(raw)]

    def send(self, text):
        return bool(self.win.fdcNet.send(self.id, text))

    def close(self):
        self.win.fdcNet.close(self.id)


def install_js():
    if not BrowserTransport._installed:
        _window().eval(_JS)
        BrowserTransport._installed = True


def default_url():
    """En el navegador, el mismo sitio de donde se cargó la página; en el
    escritorio, config.Online.SERVER_URL (o --servidor / FDC_SERVIDOR)."""
    if IN_BROWSER:
        install_js()
        return str(_window().fdcNet.defaultUrl())
    return Online.SERVER_URL


def default_transport():
    return BrowserTransport if IN_BROWSER else ThreadTransport


# En el navegador, el token se guarda en sessionStorage (sólo esa pestaña):
# si se recarga la página por error, se puede volver a la misma sala y
# partido dentro del plazo de reconexión. En el escritorio no hace falta.
_SESSION_KEY = "fdc_sesion"


def remember_session(username, token):
    if IN_BROWSER and token:
        _window().sessionStorage.setItem(_SESSION_KEY, json.dumps([username, token]))


def forget_session():
    if IN_BROWSER:
        _window().sessionStorage.removeItem(_SESSION_KEY)


def saved_session():
    """(nombre, token) guardados por esta pestaña, o None."""
    if not IN_BROWSER:
        return None
    try:
        raw = _window().sessionStorage.getItem(_SESSION_KEY)
        name, token = json.loads(str(raw)) if raw else (None, None)
    except (ValueError, TypeError):
        return None
    return (name, token) if name and token else None


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
IDLE, CONNECTING, OPEN, RECONNECTING, CLOSED = "inactivo", "conectando", "conectado", "reconectando", "cerrado"


class NetClient:
    def __init__(self, url=None, transport=None, clock=time.monotonic):
        self.url = url or default_url()
        self.transport_cls = transport or default_transport()
        self.clock = clock
        self.transport = None
        self.status = IDLE
        self.fatal = None              # texto si la conexión se perdió del todo
        self.wanted_name = None
        self.username = None
        self.token = None
        self.welcomed = False
        self.rooms = []
        self.room = None               # detalle de la sala en la que estoy
        self.match = None              # último match_start
        self.pause = {"type": W.PAUSE_INFO, "status": W.PAUSE_NONE}
        self.opponent = None
        self.result = None             # último match_over
        self.last_error = None         # último error del servidor (nombre en uso, clave...)
        self.lost_at = None
        self.next_retry = 0.0
        self.rtt = None
        self.next_ping = 0.0
        self.sent = self.received = self.bad = 0

    # ------------------------------------------------------------------ conexión
    def connect(self, username):
        """Abre la conexión (o reusa la actual) y se presenta con ese nombre."""
        self.wanted_name = username
        self.fatal = None
        if self.status == OPEN:
            self.send({"type": W.HELLO, "username": username})
        elif self.status not in (CONNECTING, RECONNECTING):
            self.status = CONNECTING
            self._open()

    def _open(self):
        self.transport = self.transport_cls(self.url)

    def close(self):
        """Salida voluntaria: no se reintenta."""
        if self.transport is not None:
            self.transport.close()
        self.transport = None
        self.status = IDLE
        self.welcomed = False
        self.token = None
        self.room = self.match = self.result = None
        forget_session()

    @property
    def connected(self):
        return self.status == OPEN and self.welcomed

    # ------------------------------------------------------------------ envío
    def send(self, msg):
        if self.transport is None or self.status != OPEN:
            return False
        ok = self.transport.send(W.encode(msg))
        self.sent += ok
        return ok

    def send_input(self, p):
        self.send({"type": W.INPUT, "p": p})

    def leave_room(self):
        self.send({"type": "leave_room"})
        self.room = None
        self.match = None

    def abandon(self):
        self.send({"type": W.ABANDON})
        self.room = None
        self.match = None

    # ------------------------------------------------------------------ recepción
    def poll(self):
        """Sin bloquear: procesa lo que llegó y devuelve los mensajes nuevos."""
        now = self.clock()
        out = []
        if self.transport is not None:
            for kind, data in self.transport.receive():
                if kind == "open":
                    self.status = OPEN
                    hello = {"type": W.HELLO, "username": self.wanted_name}
                    if self.token:
                        hello["token"] = self.token          # recuperar la sesión
                    self.send(hello)
                elif kind == "msg":
                    try:
                        msg = W.decode(data)
                    except W.WireError:
                        self.bad += 1
                        continue
                    self.received += 1
                    self._apply(msg, now)
                    out.append(msg)
                elif kind == "closed":
                    self._on_closed(data or {}, now)
                    break
        if self.status == RECONNECTING:
            if now - self.lost_at > Online.RECONNECT_GRACE:
                self._give_up("Se perdió la conexión con el servidor.")
            elif self.transport is None and now >= self.next_retry:
                self.next_retry = now + Online.RETRY_EVERY
                self._open()
        if self.connected and now >= self.next_ping:
            self.next_ping = now + Online.PING_EVERY
            self.send({"type": W.PING, "t": now})
        return out

    def _on_closed(self, info, now):
        if self.transport is not None:
            self.transport.close()
        self.transport = None
        code, reason = info.get("code"), info.get("reason") or ""
        if self.status == IDLE:
            return
        if self.welcomed and code not in NO_RETRY_CODES:
            if self.status != RECONNECTING:
                self.status = RECONNECTING
                self.lost_at = now
                self.next_retry = now + 0.5
                log.info("se cortó la conexión (%s): reintentando", reason)
            return
        self._give_up(NO_RETRY_CODES.get(code) or reason or "No se pudo conectar con el servidor.")

    def _give_up(self, text):
        log.warning("conexión perdida: %s", text)
        if self.transport is not None:
            self.transport.close()
        self.transport = None
        self.status = CLOSED
        self.fatal = text
        self.welcomed = False

    def _apply(self, msg, now):
        """Actualiza lo que se sabe. Las pantallas leen estos atributos."""
        t = msg["type"]
        if t == W.WELCOME:
            self.welcomed = True
            self.username = msg["username"]
            self.token = msg.get("token")
            self.lost_at = None
            remember_session(self.username, self.token)
            if not msg.get("restored"):
                self.room = self.match = None             # sesión nueva: no hay sala ni partido
        elif t == W.ROOMS:
            self.rooms = msg["rooms"]
            self.room = None                              # sólo lo recibe quien está en la lista
        elif t == W.ROOM:
            self.room = msg
        elif t == W.MATCH_START:
            if self.match is None or self.match["match"] != msg["match"]:
                self.result = None
                self.pause = {"type": W.PAUSE_INFO, "status": W.PAUSE_NONE}
                self.opponent = None
            self.match = msg
        elif t == W.PAUSE_INFO:
            self.pause = dict(msg, at=now)
        elif t == W.OPPONENT:
            self.opponent = dict(msg, at=now)
        elif t == W.MATCH_OVER:
            self.result = msg
            self.match = None
        elif t == W.ERROR:
            self.last_error = dict(msg, at=now)
        elif t == W.PONG and isinstance(msg.get("t"), (int, float)):
            self.rtt = max(0.0, now - msg["t"])

    # ------------------------------------------------------------------ ayudas
    def countdown(self, info):
        """Segundos que faltan según un mensaje con "left" y su hora de llegada."""
        if not info or info.get("left") is None:
            return None
        return max(0.0, info["left"] - (self.clock() - info.get("at", self.clock())))

    def reconnect_left(self):
        if self.status != RECONNECTING or self.lost_at is None:
            return None
        return max(0.0, Online.RECONNECT_GRACE - (self.clock() - self.lost_at))

    def debug_lines(self):
        rtt = f"{self.rtt * 1000:.0f} ms" if self.rtt is not None else "-"
        return {"url": self.url, "status": self.status, "user": self.username or "-", "rtt": rtt,
                "traffic": f"{self.sent} enviados / {self.received} recibidos / {self.bad} inválidos"}
