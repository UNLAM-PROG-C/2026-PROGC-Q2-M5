"""Utilidades para probar el servidor online con conexiones reales."""
import asyncio
import json
import threading
import time

import helpers  # noqa: F401  (agrega la raíz al path)
from websockets.sync.client import connect

from fdc.online.server import GameServer


class ServerThread:
    """Levanta un GameServer real (puerto libre) en un hilo con su propio bucle."""

    def __init__(self, **kw):
        kw.setdefault("web_dir", None)
        kw.setdefault("sim_logs", False)
        self.server = GameServer(**kw)
        self.loop = None
        self.started = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.server.run("127.0.0.1", 0, started=self.started.set))
        self.loop.close()

    def __enter__(self):
        self.thread.start()
        if not self.started.wait(10):
            raise RuntimeError("el servidor no arrancó")
        return self

    def __exit__(self, *exc):
        self.loop.call_soon_threadsafe(self.server.request_stop)
        self.thread.join(15)

    @property
    def url(self):
        return f"ws://127.0.0.1:{self.server.port}/ws"

    def call(self, fn):
        """Ejecuta fn() dentro del bucle del servidor y devuelve su resultado."""
        fut = asyncio.run_coroutine_threadsafe(_wrap(fn), self.loop)
        return fut.result(5)


async def _wrap(fn):
    return fn()


class Client:
    """Cliente de prueba sincrónico: guarda todo lo que llega."""

    def __init__(self, url, name=None, player_id=None):
        self.ws = connect(url, open_timeout=5, close_timeout=1, legacy=True)
        self.inbox = []
        self.token = None
        self.welcome = None
        if name:
            self.send({"type": "hello", "username": name, "player_id": player_id or f"prueba-{name}"})
            self.welcome = self.wait("welcome")
            self.token = self.welcome["token"]

    def send(self, msg):
        self.ws.send(json.dumps(msg))

    def send_raw(self, raw):
        self.ws.send(raw)

    def _recv(self, timeout):
        msg = json.loads(self.ws.recv(timeout=timeout))
        self.inbox.append(msg)
        return msg

    def wait(self, mtype, timeout=10.0, cond=None):
        """Espera un mensaje de ese tipo (que cumpla cond); conserva los demás."""
        for k, m in enumerate(self.inbox):
            if m["type"] == mtype and (cond is None or cond(m)):
                return self.inbox.pop(k)
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise AssertionError(f"no llegó {mtype}; llegaron {[m['type'] for m in self.inbox][-15:]}")
            try:
                m = self._recv(left)
            except TimeoutError:
                continue
            if m["type"] == mtype and (cond is None or cond(m)):
                self.inbox.remove(m)
                return m

    def pump(self):
        """Lee lo que ya llegó, sin esperar (para usar entre cuadros de la UI)."""
        while True:
            try:
                self._recv(0)
            except TimeoutError:
                return

    def drain(self, seconds=0.2):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                self._recv(max(0.01, deadline - time.monotonic()))
            except TimeoutError:
                break
        out, self.inbox = self.inbox, []
        return out

    def close(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass

    def kill(self):
        """Corte brusco (como si se cayera la red): sin saludo de cierre."""
        self.ws.socket.close()


def start_match(srv, a_name="Ale", b_name="Bruno", chars=("messi", "pele")):
    a, b = Client(srv.url, a_name), Client(srv.url, b_name)
    a.send({"type": "create_room", "name": "Picadito"})
    rid = a.wait("room")["room"]
    b.send({"type": "join_room", "room": rid})
    b.wait("room")
    a.send({"type": "choose_character", "character": chars[0]})
    b.send({"type": "choose_character", "character": chars[1]})
    a.send({"type": "ready"})
    b.send({"type": "ready"})
    sa, sb = a.wait("match_start"), b.wait("match_start")
    return a, b, sa, sb, rid
