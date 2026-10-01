"""Enlace de la interfaz con el proceso de simulación.

SimLink encapsula TODO lo que la interfaz sabe de multiprocessing:
  * crea las cuatro colas acotadas y el Event de cierre con contexto "spawn";
  * lanza el proceso (función de entrada importable: fdc.sim.process.simulation_main);
  * envía órdenes confiables (con cid y espera de ACK) y controles reemplazables;
  * recibe sin bloquear (get_nowait: si no hay nada, se sigue dibujando);
  * detecta fallas: proceso muerto, mensaje de error o ACK que no llega;
  * coordina el cierre: orden + Event, drenaje hasta BYE, join con tiempo
    límite y, sólo como recuperación excepcional, terminate()/kill().
"""
import logging
import multiprocessing as mp
import os
import queue
import time

from . import protocol as P
from .config import IPC
from .link import MatchLink
from .sim.process import simulation_main

log = logging.getLogger("fdc.ipc")

COMMAND_NAMES = {
    P.CMD_START: "iniciar", P.CMD_PAUSE: "pausar", P.CMD_RESUME: "continuar",
    P.CMD_RESTART: "reiniciar", P.CMD_END: "terminar", P.CMD_SHUTDOWN: "cerrar",
    P.CMD_DEBUG_POWER: "poder de prueba", P.CMD_DEBUG_CRASH: "fallo de prueba",
}


class SimLink(MatchLink):
    """Implementación local de MatchLink: un proceso de simulación y colas."""

    def __init__(self, test_mode=False, seed=None, log_to_file=True, duration=None):
        self.ctx = mp.get_context("spawn")
        self.options = {"test_mode": test_mode, "seed": seed, "log": log_to_file,
                        "duration": duration}
        self.proc = None
        self._reset_state()

    def _reset_state(self):
        self.ready = False
        self.ready_info = {}
        self.sim_pid = None
        self.error = None
        self.error_detail = ""
        self.bye = None
        self.stopping = False
        self.pending = {}
        self.next_cid = 1
        self.last_confirmed = None
        self.iseq = 0
        self.inputs_sent = self.inputs_dropped = 0
        self.states_received = self.events_received = 0
        self.deduper = P.EventDeduper()
        self.shutdown_report = None
        self.started_at = time.monotonic()

    # ------------------------------------------------------------------ ciclo de vida
    def start(self):
        self._reset_state()
        ctx = self.ctx
        self.cmd_q = ctx.Queue(IPC.COMMAND_QUEUE_SIZE)
        self.input_q = ctx.Queue(IPC.INPUT_QUEUE_SIZE)
        self.state_q = ctx.Queue(IPC.STATE_QUEUE_SIZE)
        self.event_q = ctx.Queue(IPC.EVENT_QUEUE_SIZE)
        self.stop_event = ctx.Event()
        self.proc = ctx.Process(
            target=simulation_main, name="fdc-simulacion",
            args=(self.cmd_q, self.input_q, self.state_q, self.event_q,
                  self.stop_event, self.options),
            daemon=True)   # red de seguridad: nunca queda huérfano
        self.proc.start()
        log.info("proceso de simulación lanzado (pid %s)", self.proc.pid)

    @property
    def ui_pid(self):
        return os.getpid()

    # ------------------------------------------------------------------ envío
    def send_command(self, ctype, **payload):
        """Orden confiable. Devuelve el cid o None si no se pudo entregar."""
        if self.proc is None or self.error:
            return None
        cid = self.next_cid
        self.next_cid += 1
        msg = P.make_command(ctype, cid, **payload)
        try:
            # bloquea como mucho COMMAND_PUT_TIMEOUT: una orden nunca se descarta
            # en silencio; si no entra, es una falla visible
            self.cmd_q.put(msg, timeout=IPC.COMMAND_PUT_TIMEOUT)
        except queue.Full:
            self.fail(f"No se pudo enviar la orden «{COMMAND_NAMES.get(ctype, ctype)}»: "
                       "la simulación no está leyendo órdenes.")
            return None
        self.pending[cid] = (ctype, time.monotonic())
        return cid

    def send_input(self, players):
        """Foto de controles reemplazable: si la cola está llena, se descarta."""
        if self.proc is None or self.error:
            return
        self.iseq += 1
        try:
            self.input_q.put_nowait(P.make_input(self.iseq, players))
            self.inputs_sent += 1
        except queue.Full:
            self.inputs_dropped += 1   # la próxima foto trae los mismos contadores

    # ------------------------------------------------------------------ recepción
    def _handle_control(self, msg):
        """Procesa mensajes del propio enlace. True si ya se consumió."""
        t = msg.get("type")
        if t == P.EV_READY:
            self.ready = True
            self.ready_info = msg
            self.sim_pid = msg.get("pid")
            log.info("simulación lista (pid %s, pygame cargado: %s)",
                     self.sim_pid, msg.get("pygame_loaded"))
            return False
        if t == P.EV_ACK:
            sent = self.pending.pop(msg.get("cid"), None)
            rtt = (time.monotonic() - sent[1]) if sent else None
            self.last_confirmed = {"cmd": msg.get("cmd"), "cid": msg.get("cid"),
                                   "ok": msg.get("ok"), "detail": msg.get("detail", ""),
                                   "match": msg.get("match"), "rtt": rtt,
                                   "at": time.monotonic()}
            return False
        if t == P.EV_ERROR:
            self.fail("La simulación informó un error: " + str(msg.get("message")),
                       msg.get("traceback", ""))
            return True
        if t == P.EV_BYE:
            self.bye = msg
            return True
        return False

    def poll(self):
        """Lee sin bloquear. Devuelve (mensajes_nuevos, último_estado_o_None)."""
        out = []
        if self.proc is None:
            return out, None
        for _ in range(IPC.MAX_EVENTS_PER_FRAME):
            try:
                msg = self.event_q.get_nowait()
            except (queue.Empty, OSError, ValueError):
                break
            self.events_received += 1
            if self._handle_control(msg):
                continue
            if self.deduper.fresh(msg):
                out.append(msg)
        state = None
        while True:
            try:
                state = self.state_q.get_nowait()   # el último gana
                self.states_received += 1
            except (queue.Empty, OSError, ValueError):
                break
        return out, state

    # ------------------------------------------------------------------ salud
    def fail(self, message, detail=""):
        if self.error is None:
            self.error = message
            self.error_detail = detail or ""
            log.error("%s\n%s", message, detail)

    def check_health(self):
        if self.error or self.proc is None or self.stopping:
            return self.error
        now = time.monotonic()
        if not self.proc.is_alive():
            self.fail(f"La simulación se detuvo inesperadamente "
                       f"(código de salida {self.proc.exitcode}).")
        elif not self.ready and now - self.started_at > IPC.READY_TIMEOUT:
            self.fail("La simulación no confirmó que estaba lista a tiempo.")
        else:
            for cid, (ctype, sent) in self.pending.items():
                if now - sent > IPC.ACK_TIMEOUT:
                    self.fail(f"La simulación no confirmó la orden "
                               f"«{COMMAND_NAMES.get(ctype, ctype)}» (#{cid}).")
                    break
        return self.error

    @property
    def alive(self):
        return self.proc is not None and self.proc.is_alive()

    # ------------------------------------------------------------------ cierre
    def stop(self):
        """Cierre coordinado. Devuelve un informe de cómo terminó."""
        if self.proc is None:
            return self.shutdown_report
        self.stopping = True
        t0 = time.monotonic()
        # 1) pedir el cierre por las dos vías: la orden (queda en el protocolo
        #    y se confirma) y el Event (despierta al instante cualquier espera)
        try:
            self.cmd_q.put_nowait(P.make_command(P.CMD_SHUTDOWN, self.next_cid))
        except (queue.Full, ValueError, OSError):
            pass
        self.stop_event.set()

        # 2) drenar hasta el BYE: si la SIM tiene eventos en tránsito, su hilo
        #    alimentador no puede terminar hasta que alguien los lea
        discarded = 0
        deadline = t0 + IPC.SHUTDOWN_BYE_TIMEOUT
        while self.bye is None and time.monotonic() < deadline:
            try:
                msg = self.event_q.get(timeout=0.1)   # espera bloqueante acotada
            except queue.Empty:
                if not self.proc.is_alive():
                    break
                continue
            except (OSError, ValueError):
                break
            if not self._handle_control(msg):
                discarded += 1
        while True:
            try:
                self.state_q.get_nowait()
                discarded += 1
            except (queue.Empty, OSError, ValueError):
                break

        # 3) esperar al proceso con tiempo límite; forzar sólo si no responde
        method = "ordenado"
        self.proc.join(IPC.JOIN_TIMEOUT)
        if self.proc.is_alive():
            log.warning("la simulación no terminó en %.1f s: se usa terminate()", IPC.JOIN_TIMEOUT)
            self.proc.terminate()
            self.proc.join(1.0)
            method = "terminate"
            if self.proc.is_alive():
                log.error("terminate() no alcanzó: se usa kill()")
                self.proc.kill()
                self.proc.join(1.0)
                method = "kill"

        # 4) lo que la UI había puesto en sus colas ya no lo leerá nadie:
        #    cancel_join_thread evita que la UI se cuelgue al salir por eso
        for q in (self.cmd_q, self.input_q):
            q.cancel_join_thread()
            q.close()
        for q in (self.state_q, self.event_q):
            q.close()

        self.shutdown_report = {
            "method": method, "exitcode": self.proc.exitcode,
            "bye": self.bye is not None, "discarded": discarded,
            "elapsed": time.monotonic() - t0,
        }
        log.info("cierre de la simulación: %s", self.shutdown_report)
        self.proc = None
        return self.shutdown_report

    def restart(self):
        self.stop()
        self.start()

    def debug_lines(self):
        lc = self.last_confirmed
        if lc:
            age = time.monotonic() - lc["at"]
            ok = "ok" if lc["ok"] else "rechazada"
            rtt = f", {lc['rtt'] * 1000:.0f} ms" if lc["rtt"] is not None else ""
            confirmed = f"{lc['cmd']} #{lc['cid']} ({ok}{rtt}) hace {age:.1f} s"
        else:
            confirmed = "—"
        return {
            "sim_pid": self.sim_pid or (self.proc.pid if self.proc else None),
            "alive": self.alive,
            "confirmed": confirmed,
            "pending": len(self.pending),
            "inputs": f"{self.inputs_sent} enviados / {self.inputs_dropped} reemplazados",
            "received": f"{self.states_received} estados, {self.events_received} eventos",
        }
