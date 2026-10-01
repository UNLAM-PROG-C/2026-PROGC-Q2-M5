"""Servidor del modo online: salas 1 contra 1 por WebSocket.

Concurrencia (ver docs/ONLINE.md):
  * UN proceso servidor con un bucle asyncio. Atiende todas las conexiones:
    por cada una hay una corrutina que LEE y otra que ESCRIBE. Sólo este bucle
    toca el Lobby y las sesiones, así que no hacen falta locks.
  * UN proceso de simulación POR SALA EN JUEGO: el mismo de la versión local
    (fdc.sim.process.simulation_main, con colas acotadas, ACKs, número de
    partido y Event de cierre), manejado con SimLink. Una sala trabada no
    frena a las demás y cada sala puede usar otro núcleo.
  * Un PUENTE por sala (tarea asyncio a 60 Hz): lleva los controles de los
    dos navegadores a su proceso y reenvía estados (30 por segundo) y eventos.
  * Lanzar o cerrar un proceso puede bloquear: se hace en un hilo del
    ejecutor (run_in_executor) para no frenar el bucle.

Además sirve los archivos del cliente web (build/web, generado con
tools/construir_web.py) en el mismo puerto: el navegador abre la página y se
conecta por WebSocket a /ws.
"""
import argparse
import asyncio
import collections
import itertools
import logging
import mimetypes
import os
import secrets
import sys
import time
from pathlib import Path

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Response

from .. import protocol as P
from ..config import LOG_DIR, ROOT_DIR, Online
from ..ipc import SimLink
from . import wire as W
from .lobby import PLAYING, Lobby

log = logging.getLogger("fdc.server")

DEFAULT_WEB_DIR = os.path.join(ROOT_DIR, "build", "web")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/octet-stream", ".apk")


# ---------------------------------------------------------------------------
# Sesión: una persona con nombre de usuario (sobrevive a cortes breves)
# ---------------------------------------------------------------------------
class Session:
    _ids = itertools.count(1)

    def __init__(self):
        self.id = f"s{next(self._ids)}"
        self.token = secrets.token_urlsafe(18)     # para volver después de un corte
        self.username = None
        self.ws = None
        self.queue = collections.deque()          # mensajes confiables, en orden
        self.state_text = None                    # último estado: reemplazable
        self.wake = asyncio.Event()
        self.writer = None
        self.expire_task = None
        self.dropped_states = 0

    # ------------------------------------------------------------------ envío
    def send(self, msg):
        self.send_text(W.encode(msg))

    def send_text(self, text, replaceable=False):
        """No bloquea nunca: deja el mensaje para la corrutina escritora.

        Política: los estados son reemplazables (si el navegador va lento se
        manda sólo el último); el resto se entrega en orden. Si se acumulan
        demasiados, el cliente no está leyendo: se corta la conexión (y corre
        el plazo para volver), así un cliente lento no afecta a nadie más."""
        if self.ws is None:
            return            # desconectado: al volver recibe un resumen actualizado
        if replaceable:
            if self.state_text is not None:
                self.dropped_states += 1
            self.state_text = text
        else:
            if len(self.queue) >= Online.OUTBOX_LIMIT:
                log.warning("%s no lee sus mensajes: se corta la conexión", self.username)
                asyncio.ensure_future(self.ws.close(1008, "cliente demasiado lento"))
                return
            self.queue.append(text)
        self.wake.set()

    def attach(self, ws):
        self.detach()
        self.ws = ws
        self.queue.clear()
        self.state_text = None
        self.writer = asyncio.create_task(self._write_loop(ws))

    def detach(self):
        if self.writer is not None:
            self.writer.cancel()
            self.writer = None
        self.ws = None

    async def _write_loop(self, ws):
        try:
            while True:
                await self.wake.wait()              # duerme hasta que haya algo
                self.wake.clear()
                while self.queue:
                    await ws.send(self.queue.popleft())
                if self.state_text is not None:
                    text, self.state_text = self.state_text, None
                    await ws.send(text)
        except ConnectionClosed:
            pass


# ---------------------------------------------------------------------------
# Puente de una sala con su proceso de simulación
# ---------------------------------------------------------------------------
class RoomRunner:
    def __init__(self, server, room_id):
        self.server = server
        self.room_id = room_id
        self.link = SimLink(log_to_file=server.sim_logs, duration=server.duration, seed=server.seed)
        self.link_started = False
        self.task = None
        self.closed = False
        self._reset_match()

    def _reset_match(self):
        self.match = None            # {"id", "sids", "names", "chars", "start_msgs"}
        self.start_pending = False
        self.inputs = [[False, False, 0, 0], [False, False, 0, 0]]
        self.last_state = None
        self.sent_seq = -1
        self.last_state_sent = 0.0
        self.hold = set()            # motivos por los que la simulación debe seguir en pausa
        self.pause = None            # {"status", "by", "deadline", "ready"}
        self.away = {}               # lado -> momento límite para volver

    # ------------------------------------------------------------------ ciclo
    async def begin(self, match_id, sids, names, chars, start_msgs):
        self._reset_match()
        self.match = {"id": match_id, "sids": sids, "names": names, "chars": chars,
                      "start_msgs": start_msgs}
        self.start_pending = True    # la orden sale cuando la simulación confirme READY
        if not self.link_started:
            self.link_started = True
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.link.start)
            self.task = asyncio.create_task(self._pump())
        log.info("sala %s: partido #%s %s (%s) vs %s (%s)", self.room_id, match_id,
                 names[0], chars[0], names[1], chars[1])

    async def close(self):
        self.closed = True
        if self.task is not None:
            self.task.cancel()
        if self.link_started:
            loop = asyncio.get_running_loop()
            report = await loop.run_in_executor(None, self.link.stop)
            log.info("sala %s: proceso de simulación cerrado %s", self.room_id, report)

    async def _pump(self):
        period = 1.0 / Online.PUMP_HZ
        while not self.closed:
            try:
                self.tick(time.monotonic())
            except Exception:  # noqa: BLE001 - una sala rota no tira abajo el servidor
                log.exception("sala %s: error en el puente", self.room_id)
                self._fail("error interno de la sala")
                return
            await asyncio.sleep(period)   # ritmo fijo: no es una espera activa

    # ------------------------------------------------------------------ puente
    def tick(self, now):
        msgs, state = self.link.poll()          # sin bloquear
        err = self.link.check_health()
        if err:
            self._fail(err)
            return
        m = self.match
        if m is None:
            return
        if self.start_pending and self.link.ready:
            self.start_pending = False
            self.link.send_command(P.CMD_START, match=m["id"], characters=m["chars"])
        for ev in msgs:
            t = ev.get("type")
            if t in (P.EV_READY, P.EV_ACK) or ev.get("match") != m["id"]:
                continue
            if t == P.EV_MATCH_END:
                self._finish(W.END_TIME, ev["winner"], ev["score"])
                return
            if t == P.EV_PAUSED and ev.get("reason") == P.PAUSE_REASON_REQUEST:
                self._pause_started(ev.get("by"), now)
            self.broadcast({"type": W.EVENT, "e": ev})
        if state is not None and state.get("match") == m["id"]:
            self.last_state = state
        st = self.last_state
        if (st is not None and st["seq"] != self.sent_seq
                and now - self.last_state_sent >= 1.0 / Online.STATE_HZ - 0.004):
            self.sent_seq = st["seq"]
            self.last_state_sent = now
            self.broadcast_text(W.encode(W.compact_state(st)), replaceable=True)
        # los controles van en cada vuelta: también son el "latido" del watchdog
        self.link.send_input(self.inputs)
        p = self.pause
        if p and p["status"] == W.PAUSE_ACTIVE and (all(p["ready"]) or now >= p["deadline"]):
            self._end_pause()

    def side_of(self, sid):
        if self.match is None or sid not in self.match["sids"]:
            return None
        return self.match["sids"].index(sid)

    def broadcast(self, msg):
        self.broadcast_text(W.encode(msg))

    def broadcast_text(self, text, replaceable=False):
        for sid in self.match["sids"] if self.match else ():
            s = self.server.sessions.get(sid)
            if s is not None:
                s.send_text(text, replaceable)

    # ------------------------------------------------------------------ jugadores
    def set_input(self, side, p):
        self.inputs[side] = p

    def request_pause(self, side):
        st = self.last_state
        if self.match is None or self.pause is not None or st is None or st["phase"] == P.PHASE_FINISHED:
            return
        self.link.send_command(P.CMD_PAUSE, after_goal=True, by=side, reason=P.PAUSE_REASON_REQUEST)
        self.pause = {"status": W.PAUSE_PENDING, "by": side, "deadline": None, "ready": [False, False]}
        self._send_pause_info()

    def pause_ready(self, side):
        p = self.pause
        if p and p["status"] == W.PAUSE_ACTIVE and not p["ready"][side]:
            p["ready"][side] = True
            self._send_pause_info()

    def _pause_started(self, by, now):
        prev = self.pause or {}
        self.pause = {"status": W.PAUSE_ACTIVE, "by": by if by is not None else prev.get("by"),
                      "deadline": now + self.server.pause_max, "ready": [False, False]}
        self.hold.add(P.PAUSE_REASON_REQUEST)
        self._send_pause_info()

    def _end_pause(self):
        self.pause = None
        self._send_pause_info()
        self._release(P.PAUSE_REASON_REQUEST)

    def _release(self, reason):
        if reason in self.hold:
            self.hold.discard(reason)
            if not self.hold and self.match is not None:
                self.link.send_command(P.CMD_RESUME)

    def pause_info(self):
        p = self.pause
        if p is None:
            return {"type": W.PAUSE_INFO, "status": W.PAUSE_NONE}
        left = None if p["deadline"] is None else max(0.0, p["deadline"] - time.monotonic())
        return {"type": W.PAUSE_INFO, "status": p["status"], "by": p["by"],
                "by_name": self.match["names"][p["by"]] if p["by"] is not None else None,
                "left": left, "ready": list(p["ready"])}

    def _send_pause_info(self):
        self.broadcast(self.pause_info())

    def opponent_msg(self, side):
        """Cómo está la conexión del rival de 'side'."""
        other = 1 - side
        deadline = self.away.get(other)
        return {"type": W.OPPONENT, "connected": deadline is None,
                "name": self.match["names"][other],
                "left": None if deadline is None else max(0.0, deadline - time.monotonic())}

    def player_away(self, side, deadline):
        if self.match is None:
            return
        self.away[side] = deadline
        if P.PAUSE_REASON_DISCONNECT not in self.hold:
            self.hold.add(P.PAUSE_REASON_DISCONNECT)
            self.link.send_command(P.CMD_PAUSE, reason=P.PAUSE_REASON_DISCONNECT)
        self._send_opponent_status()
        log.info("sala %s: %s perdió la conexión", self.room_id, self.match["names"][side])

    def player_back(self, side, session):
        if self.match is None:
            return
        self.away.pop(side, None)
        session.send(self.match["start_msgs"][side])     # vuelve a la pantalla del partido
        session.send(self.pause_info())
        if self.last_state is not None:
            session.send_text(W.encode(W.compact_state(self.last_state)), replaceable=True)
        self._send_opponent_status()
        if not self.away:
            self._release(P.PAUSE_REASON_DISCONNECT)
        log.info("sala %s: %s volvió", self.room_id, self.match["names"][side])

    def _send_opponent_status(self):
        for side, sid in enumerate(self.match["sids"]):
            s = self.server.sessions.get(sid)
            if s is not None:
                s.send(self.opponent_msg(side))

    def forfeit(self, side):
        """Abandono (botón o 30 s sin volver): gana el que se quedó."""
        m = self.match
        if m is None:
            return
        score = list(self.last_state["score"]) if self.last_state else [0, 0]
        self.link.send_command(P.CMD_END)
        log.info("sala %s: %s abandonó el partido #%s", self.room_id, m["names"][side], m["id"])
        self._finish(W.END_FORFEIT, 1 - side, score, by=side)

    def _finish(self, reason, winner, score, by=None):
        m = self.match
        self.broadcast({"type": W.MATCH_OVER, "match": m["id"], "score": score, "winner": winner,
                        "reason": reason, "by": by, "by_name": m["names"][by] if by is not None else None})
        self._reset_match()
        self.server.deliver(self.server.lobby.finish_match(self.room_id))

    def _fail(self, err):
        log.error("sala %s: falló la simulación: %s", self.room_id, err)
        if self.match is not None:
            self._finish(W.END_ERROR, None, list(self.last_state["score"]) if self.last_state else [0, 0])
        # la próxima partida usa un puente y un proceso nuevos
        self.server.drop_runner(self.room_id, self)

    def debug(self):
        return {"room": self.room_id, "match": self.match and self.match["id"], "pid": self.link.sim_pid,
                "hold": sorted(self.hold)}


# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------
class GameServer:
    def __init__(self, web_dir=DEFAULT_WEB_DIR, duration=None, grace=Online.RECONNECT_GRACE,
                 pause_max=Online.PAUSE_MAX, seed=None, rng=None, sim_logs=True):
        self.lobby = Lobby(rng)
        self.web_dir = Path(web_dir).resolve() if web_dir else None
        self.duration = duration
        self.grace = grace
        self.pause_max = pause_max
        self.seed = seed
        self.sim_logs = sim_logs
        self.sessions = {}           # id -> Session con nombre
        self.tokens = {}             # token -> Session
        self.runners = {}            # sala -> RoomRunner
        self.connections = 0
        self.tasks = set()           # tareas sueltas (referencia para que no se pierdan)
        self.port = None
        self.stopped = None

    def spawn(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    # ------------------------------------------------------------------ HTTP (archivos del cliente)
    async def http(self, connection, request):
        path = request.path.split("?", 1)[0]
        if path == Online.WS_PATH:
            return None                                   # sigue el saludo WebSocket
        if path == "/estado":
            body = (f"salas {len(self.lobby.rooms)}, en juego {len(self.runners)}, "
                    f"conexiones {self.connections}\n")
            return connection.respond(200, body)
        return await asyncio.to_thread(self._static, connection, path)

    def _static(self, connection, path):
        if self.web_dir is None or not (self.web_dir / "index.html").is_file():
            return connection.respond(404, "El cliente web no está compilado. Ejecutá: "
                                           "python tools/construir_web.py\n")
        if path.endswith("/"):
            path += "index.html"
        target = (self.web_dir / path.lstrip("/")).resolve()
        if self.web_dir not in target.parents or not target.is_file():
            return connection.respond(404, "No existe.\n")
        body = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        headers = Headers([("Content-Type", ctype), ("Content-Length", str(len(body))),
                           ("Cache-Control", "no-cache")])
        return Response(200, "OK", headers, body)

    # ------------------------------------------------------------------ conexiones
    async def handler(self, ws):
        if self.connections >= Online.MAX_CONNECTIONS:
            await ws.close(1013, "servidor lleno")
            return
        self.connections += 1
        session = None
        stamps = collections.deque()
        try:
            deadline = time.monotonic() + Online.HELLO_TIMEOUT
            pending = Session()
            pending.attach(ws)
            while session is None:                        # presentación (con tiempo límite)
                raw = await asyncio.wait_for(ws.recv(), max(0.1, deadline - time.monotonic()))
                deadline = time.monotonic() + Online.HELLO_TIMEOUT   # está probando nombres: se espera
                msg = self._decode(pending, raw, stamps)
                if msg is None:
                    continue
                if msg["type"] != W.HELLO:
                    pending.send({"type": W.ERROR, "code": "sin_nombre",
                                  "message": "Primero hay que elegir un nombre de usuario."})
                    continue
                session = self._hello(pending, ws, msg)
            if session is not pending:
                pending.detach()
            async for raw in ws:
                msg = self._decode(session, raw, stamps)
                if msg is not None:
                    self.route(session, msg)
        except (ConnectionClosed, asyncio.TimeoutError):
            pass
        finally:
            self.connections -= 1
            if session is None:
                pending.detach()
            else:
                self._connection_lost(session, ws)

    def _decode(self, session, raw, stamps):
        now = time.monotonic()
        stamps.append(now)
        while stamps and now - stamps[0] > 1.0:
            stamps.popleft()
        if len(stamps) > Online.MAX_MESSAGES_PER_SEC:
            log.warning("demasiados mensajes de %s: se corta", session.username or "?")
            asyncio.ensure_future(session.ws.close(1008, "demasiados mensajes"))
            return None
        try:
            return W.decode(raw, W.CLIENT_TYPES)
        except W.WireError as exc:
            session.send({"type": W.ERROR, "code": "mensaje_invalido", "message": str(exc)})
            return None

    def _hello(self, pending, ws, msg):
        """Devuelve la sesión si se presentó bien (nueva o recuperada), si no None."""
        token = msg.get("token")
        old = self.tokens.get(token) if isinstance(token, str) else None
        if old is not None:
            # vuelve alguien que se había cortado: recupera nombre, sala y partido
            if old.ws is not None and old.ws is not ws:
                asyncio.ensure_future(old.ws.close(4000, "sesión abierta en otro lado"))
            if old.expire_task is not None:
                old.expire_task.cancel()
                old.expire_task = None
            old.attach(ws)
            old.send({"type": W.WELCOME, "username": old.username, "token": old.token, "restored": True})
            self.deliver(self.lobby.set_connected(old.id, True))
            self.deliver(self.lobby.resync(old.id))
            runner, side = self._runner_side(old.id)
            if runner is not None and side is not None:
                runner.player_back(side, old)
            log.info("%s volvió a conectarse", old.username)
            return old
        out = self.lobby.handle(pending.id, {"type": "hello", "username": msg.get("username")})
        welcome = next((m for _, m in out if m["type"] == W.WELCOME), None)
        if welcome is None:
            for _, m in out:
                pending.send(m)
            return None
        pending.username = welcome["username"]
        welcome.update(token=pending.token, restored=False)
        self.sessions[pending.id] = pending
        self.tokens[pending.token] = pending
        self.deliver(out)
        log.info("entró %s (%s)", pending.username, pending.id)
        return pending

    def _runner_side(self, sid):
        room = self.lobby.room_of_conn(sid)
        runner = self.runners.get(room.id) if room else None
        side = runner.side_of(sid) if runner else None
        return runner, side

    def route(self, s, msg):
        t = msg["type"]
        if t == W.PING:
            s.send({"type": W.PONG, "t": msg.get("t")})
            return
        if t == W.HELLO:
            s.send({"type": W.ERROR, "code": "ya_presentado", "message": "Ya elegiste tu nombre."})
            return
        runner, side = self._runner_side(s.id)
        in_match = runner is not None and side is not None
        try:
            if t == W.INPUT:
                if in_match:
                    runner.set_input(side, W.clean_input(msg.get("p")))
                return
            if t == W.PAUSE_REQUEST:
                if in_match:
                    runner.request_pause(side)
                return
            if t == W.PAUSE_READY:
                if in_match:
                    runner.pause_ready(side)
                return
        except W.WireError as exc:
            s.send({"type": W.ERROR, "code": "mensaje_invalido", "message": str(exc)})
            return
        room = self.lobby.room_of_conn(s.id)
        if t == W.ABANDON or (t == "leave_room" and room is not None and room.state == PLAYING):
            if in_match:
                runner.forfeit(side)                      # pierde y se va de la sala
            if room is not None:
                self.deliver(self.lobby.handle(s.id, {"type": "leave_room"}))
                self.room_changed(room.id)
            return
        self.deliver(self.lobby.handle(s.id, msg))
        if t == "leave_room" and room is not None:
            self.room_changed(room.id)

    def deliver(self, out):
        """Manda lo que devolvió el Lobby y arranca los partidos que empiezan."""
        starts = {}
        for targets, msg in out:
            text = W.encode(msg)
            for sid in targets:
                s = self.sessions.get(sid)
                if s is not None:
                    s.send_text(text)
            if msg["type"] == W.MATCH_START:
                starts.setdefault(msg["room"], {})[msg["you"]] = msg
        for room_id, msgs in starts.items():
            self._start_match(room_id, msgs)

    def _start_match(self, room_id, msgs):
        room = self.lobby.rooms[room_id]
        any_msg = next(iter(msgs.values()))
        players = sorted(any_msg["players"], key=lambda p: p["side"])
        sids = [None, None]
        for m in room.members:
            sids[m.side] = m.conn
        runner = self.runners.get(room_id)
        if runner is None:
            runner = self.runners[room_id] = RoomRunner(self, room_id)
        self.spawn(runner.begin(any_msg["match"], sids, [p["username"] for p in players],
                                [p["character"] for p in players], [msgs[0], msgs[1]]))

    def room_changed(self, room_id):
        """Si la sala quedó con menos de 2 personas, su proceso ya no hace falta."""
        room = self.lobby.rooms.get(room_id)
        if room is None or len(room.members) < 2:
            runner = self.runners.get(room_id)
            if runner is not None:
                self.drop_runner(room_id, runner)

    def drop_runner(self, room_id, runner):
        if self.runners.get(room_id) is runner:
            del self.runners[room_id]
        self.spawn(runner.close())

    # ------------------------------------------------------------------ cortes de conexión
    def _connection_lost(self, s, ws):
        if s.ws is not ws:
            return                                        # ya la reemplazó una reconexión
        s.detach()
        log.info("%s se desconectó: tiene %.0f s para volver", s.username, self.grace)
        self.deliver(self.lobby.set_connected(s.id, False))
        runner, side = self._runner_side(s.id)
        if runner is not None and side is not None:
            runner.player_away(side, time.monotonic() + self.grace)
        s.expire_task = self.spawn(self._expire_later(s))

    async def _expire_later(self, s):
        await asyncio.sleep(self.grace)
        if s.ws is not None:
            return
        s.expire_task = None
        runner, side = self._runner_side(s.id)
        if runner is not None and side is not None:
            runner.forfeit(side)                          # no volvió: gana el que se quedó
        room = self.lobby.room_of_conn(s.id)
        self.deliver(self.lobby.disconnect(s.id))
        if room is not None:
            self.room_changed(room.id)
        self.sessions.pop(s.id, None)
        self.tokens.pop(s.token, None)
        log.info("%s no volvió: se liberó su lugar", s.username)

    # ------------------------------------------------------------------ arranque y cierre
    async def run(self, host="0.0.0.0", port=Online.PORT, started=None):
        self.stopped = asyncio.Event()
        async with serve(self.handler, host, port, process_request=self.http,
                         max_size=Online.MAX_MESSAGE_BYTES, ping_interval=5, ping_timeout=10) as srv:
            self.port = srv.sockets[0].getsockname()[1]
            log.info("servidor listo en http://%s:%s (WebSocket en %s)", host, self.port, Online.WS_PATH)
            if started is not None:
                started()
            try:
                await self.stopped.wait()
            finally:
                await self.close_all()

    def request_stop(self):
        if self.stopped is not None:
            self.stopped.set()

    async def close_all(self):
        """Cierre coordinado: cada sala cierra su proceso (con tiempo límite)."""
        for s in list(self.sessions.values()):
            if s.expire_task is not None:
                s.expire_task.cancel()                    # plazos de reconexión: ya no importan
            s.detach()
        runners = list(self.runners.values())
        self.runners.clear()
        await asyncio.gather(*(r.close() for r in runners), return_exceptions=True)
        # salas que ya se estaban cerrando o arrancando: se espera a que terminen
        pending = [t for t in self.tasks if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=10)
        log.info("servidor cerrado (%d salas en juego cerradas)", len(runners))


def setup_logging():
    fmt = "%(asctime)s [%(processName)s pid=%(process)d] %(levelname)s %(name)s: %(message)s"
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handlers.append(logging.FileHandler(os.path.join(LOG_DIR, "servidor.log"), mode="a", encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers, force=True)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Servidor online de Futbol De Cabeza (salas 1 contra 1).")
    p.add_argument("--host", default="0.0.0.0", help="interfaz donde escuchar (0.0.0.0 = todas)")
    p.add_argument("--puerto", type=int, default=Online.PORT)
    p.add_argument("--web", default=DEFAULT_WEB_DIR, help="carpeta del cliente web compilado")
    p.add_argument("--duracion", type=float, default=None, help="duración de los partidos (s)")
    p.add_argument("--gracia", type=float, default=Online.RECONNECT_GRACE,
                   help="segundos para volver tras un corte antes de perder por abandono")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    setup_logging()
    server = GameServer(web_dir=args.web, duration=args.duracion, grace=args.gracia)
    try:
        asyncio.run(server.run(args.host, args.puerto))
    except KeyboardInterrupt:
        log.info("interrupción desde la terminal: servidor detenido")
    except OSError as exc:
        log.error("no se pudo abrir el puerto %s (¿ya hay otro servidor andando?): %s", args.puerto, exc)
        return 1
    return 0
