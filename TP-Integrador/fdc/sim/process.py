"""Proceso secundario: la simulación.

Es la única autoridad sobre movimientos, colisiones, reloj, goles, poderes,
bombas y azar. No crea ventanas ni maneja audio: ni siquiera importa pygame
(lo informa en el mensaje READY para poder demostrarlo).

Bucle:
* Sin partido, en pausa o con el partido terminado -> espera BLOQUEANTE en la
  cola de órdenes con tiempo límite (no hay espera activa).
* Con partido en juego -> paso fijo de 1/120 s. Entre pasos duerme con
  stop_event.wait(resto), que además despierta al instante si la interfaz
  pide cerrar.
"""
import logging
import multiprocessing as mp
import os
import queue
import signal
import sys
import time
import traceback

from .. import config as C
from .. import protocol as P
from .core import SimulationCore

log = logging.getLogger("fdc.sim")


class SimulationServer(SimulationCore):
    """El núcleo de la simulación (fdc/sim/core.py) en su propio proceso, con colas."""

    def __init__(self, cmd_q, input_q, state_q, event_q, stop_event, options):
        super().__init__(options)
        self.cmd_q = cmd_q
        self.input_q = input_q
        self.state_q = state_q
        self.event_q = event_q
        self.stop_event = stop_event
        self.last_parent_check = 0.0
        self.last_heartbeat = 0.0

    # ------------------------------------------------------------------ envío (colas)
    def put_cosmetic(self, msg):
        try:
            self.event_q.put_nowait(msg)
            return True
        except queue.Full:
            return False

    def put_reliable(self, msg):
        """Entrega garantizada salvo que se esté cerrando todo."""
        while True:
            try:
                self.event_q.put(msg, timeout=0.2)
                return True
            except queue.Full:
                if self.stop_event.is_set() or not self._parent_alive():
                    log.warning("no se pudo entregar %s: cierre en curso", msg.get("type"))
                    return False
                log.warning("cola de eventos llena; reintentando %s", msg.get("type"))

    def put_state(self, snap):
        """Estados reemplazables: si la cola está llena se descarta el MÁS VIEJO."""
        try:
            self.state_q.put_nowait(snap)
            return
        except queue.Full:
            pass
        try:
            self.state_q.get_nowait()       # quita un estado viejo
            self.dropped_states += 1
        except queue.Empty:
            pass
        try:
            self.state_q.put_nowait(snap)
        except queue.Full:
            self.dropped_states += 1        # la UI lo reemplazará por el siguiente

    # ------------------------------------------------------------------ recepción (colas)
    def drain_commands(self):
        while True:
            try:
                cmd = self.cmd_q.get_nowait()
            except queue.Empty:
                return
            self.handle_command(cmd)

    def drain_inputs(self):
        """Compacta: sólo importa la última foto; los contadores no pierden pulsaciones."""
        latest = None
        while True:
            try:
                latest = self.input_q.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            self.apply_inputs(latest)

    # ------------------------------------------------------------------ bucle
    def _parent_alive(self):
        parent = mp.parent_process()
        return parent is None or parent.is_alive()

    def run(self):
        self.put_reliable(self.ready_event())
        next_tick = time.monotonic()
        while self.running and not self.stop_event.is_set():
            now = time.monotonic()
            if now - self.last_parent_check > C.IPC.PARENT_CHECK_EVERY:
                self.last_parent_check = now
                if not self._parent_alive():
                    log.error("la interfaz desapareció: la simulación termina sola")
                    return
            if not self.match_running():
                self._idle()
                next_tick = time.monotonic()
                continue

            self.drain_commands()
            self.drain_inputs()
            if not self.match_running():
                continue
            if time.monotonic() - self.last_input_time > C.MatchRules.INPUT_WATCHDOG:
                # la interfaz dejó de mandar controles (ventana bloqueada, etc.)
                self.match.pause(P.PAUSE_REASON_WATCHDOG)
                self.emit(P.EV_PAUSED, self.match.id, reason=P.PAUSE_REASON_WATCHDOG)
                self.publish_state()
                continue

            steps = 0
            now = time.monotonic()
            while now >= next_tick and steps < C.MAX_CATCHUP_STEPS:
                self.step_once()
                next_tick += C.PHYSICS_DT
                steps += 1
                if not self.match_running():
                    break
            if steps >= C.MAX_CATCHUP_STEPS and now >= next_tick:
                next_tick = now   # demasiado atraso: se descarta en vez de acelerar
            wait = next_tick - time.monotonic()
            if wait > 0:
                self.stop_event.wait(wait)

    def _idle(self):
        try:
            cmd = self.cmd_q.get(timeout=C.IPC.IDLE_WAIT)
        except queue.Empty:
            cmd = None
        if cmd is not None:
            self.handle_command(cmd)
        self.drain_inputs()
        m = self.match
        if m is not None and m.paused:
            now = time.monotonic()
            if now - self.last_heartbeat > C.IPC.PAUSED_HEARTBEAT:
                self.last_heartbeat = now
                self.publish_state()   # latido: la UI ve que la SIM sigue viva


def _setup_logging():
    fmt = "%(asctime)s [%(processName)s pid=%(process)d] %(levelname)s %(name)s: %(message)s"
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        os.makedirs(C.LOG_DIR, exist_ok=True)
        handlers.append(logging.FileHandler(os.path.join(C.LOG_DIR, "fdc.log"), mode="a",
                                            encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers, force=True)


def simulation_main(cmd_q, input_q, state_q, event_q, stop_event, options):
    """Función de entrada del proceso (importable, compatible con spawn)."""
    # Ctrl+C en la terminal llega a ambos procesos; el cierre lo coordina la UI.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if options.get("log", True):
        _setup_logging()
    server = SimulationServer(cmd_q, input_q, state_q, event_q, stop_event, options)
    exit_code = 0
    try:
        server.run()
        log.info("simulación finalizada ordenadamente")
    except Exception as exc:  # noqa: BLE001 - se informa a la interfaz
        exit_code = 1
        log.exception("error en la simulación")
        server.put_reliable(P.make_event(P.EV_ERROR, None, None, message=str(exc),
                                         traceback=traceback.format_exc()))
    finally:
        # Estados y eventos cosméticos pendientes se pueden perder sin daño:
        # no bloquear la salida esperando que la UI los lea.
        state_q.cancel_join_thread()
        server.put_reliable(P.make_event(P.EV_BYE, None, None, code=exit_code,
                                         dropped_states=server.dropped_states,
                                         dropped_cosmetic=server.dropped_cosmetic))
        # El BYE sí debe llegar: se espera a que el hilo alimentador lo vuelque,
        # salvo que la UI ya no exista.
        if not server._parent_alive():
            event_q.cancel_join_thread()
        event_q.close()
        state_q.close()
    sys.exit(exit_code)
