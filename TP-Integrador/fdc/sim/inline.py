"""Simulación dentro de la misma página (versión de navegador).

En el navegador (pygbag, WebAssembly) no hay procesos ni hilos, así que los
modos locales (Mundialito y Multijugador local) no pueden lanzar el proceso de
simulación. InlineLink cumple el MISMO contrato que SimLink (fdc/link.py) con
el MISMO núcleo de simulación (fdc/sim/core.py): las órdenes se confirman con
ACK, los controles viajan como fotos con contadores y los estados llevan
partido y número de actualización. La diferencia es que todo ocurre en el
mismo hilo, una vez por cuadro:

    poll():  órdenes pendientes -> última foto de controles -> pasos de física
             hasta "ahora" (paso fijo de 1/120 s) -> eventos y último estado

La versión de escritorio sigue usando dos procesos (SimLink), y el online
usa un proceso por sala en el servidor.
"""
import logging
import time
import traceback

from .. import config as C
from .. import protocol as P
from ..link import MatchLink
from .core import SimulationCore

log = logging.getLogger("fdc.inline")



class InlineSimulation(SimulationCore):
    """El núcleo con "colas" en memoria: listas que se vacían en cada cuadro."""

    def __init__(self, options):
        super().__init__(options)
        self.events = []
        self.state = None

    def put_reliable(self, msg):
        self.events.append(msg)
        return True

    def put_cosmetic(self, msg):
        self.events.append(msg)
        return True

    def put_state(self, snap):
        if self.state is not None:
            self.dropped_states += 1      # la pantalla sólo dibuja el último
        self.state = snap

    def take(self):
        events, state = self.events, self.state
        self.events, self.state = [], None
        return events, state


class InlineLink(MatchLink):
    inline = True

    def __init__(self, test_mode=False, seed=None, duration=None, clock=time.perf_counter):
        self.options = {"test_mode": test_mode, "seed": seed, "duration": duration}
        self.clock = clock
        self.core = None
        self._reset_state()

    def _reset_state(self):
        self.ready = False
        self.ready_info = {}
        self.error = None
        self.error_detail = ""
        self.shutdown_report = None
        self.commands = []
        self.latest_input = None
        self.pending = {}
        self.next_cid = 1
        self.iseq = 0
        self.next_tick = self.clock()
        self.last_confirmed = None
        self.inputs_sent = 0
        self.states_received = self.events_received = 0

    # ------------------------------------------------------------------ ciclo de vida
    def start(self):
        self._reset_state()
        self.core = InlineSimulation(self.options)
        self.core.put_reliable(self.core.ready_event())

    def stop(self):
        if self.core is None:
            return self.shutdown_report
        self.core = None
        self.shutdown_report = {"method": "en el mismo hilo", "bye": True, "exitcode": 0}
        return self.shutdown_report

    @property
    def alive(self):
        return self.core is not None and self.error is None

    # ------------------------------------------------------------------ envío
    def send_command(self, ctype, **payload):
        if self.core is None or self.error:
            return None
        cid = self.next_cid
        self.next_cid += 1
        self.commands.append(P.make_command(ctype, cid, **payload))
        self.pending[cid] = (ctype, self.clock())
        return cid

    def send_input(self, players):
        if self.core is None or self.error:
            return
        self.iseq += 1
        self.latest_input = P.make_input(self.iseq, players)   # reemplazable: gana la última
        self.inputs_sent += 1

    # ------------------------------------------------------------------ simulación
    def poll(self):
        """Avanza la simulación hasta ahora y devuelve (eventos, último estado)."""
        core = self.core
        if core is None or self.error:
            return [], None
        try:
            commands, self.commands = self.commands, []
            for cmd in commands:
                core.handle_command(cmd)
            if self.latest_input is not None:
                core.apply_inputs(self.latest_input)
                self.latest_input = None
            self._advance()
        except Exception as exc:  # noqa: BLE001 - se muestra en la pantalla de error, como en escritorio
            log.exception("error en la simulación")
            self.fail("La simulación informó un error: " + str(exc), traceback.format_exc())
        events, state = core.take()
        out = []
        for msg in events:
            self.events_received += 1
            if not self._handle_control(msg):
                out.append(msg)
        if state is not None:
            self.states_received += 1
        return out, state

    def _advance(self):
        core = self.core
        now = self.clock()
        if not core.match_running():
            self.next_tick = now              # sin partido o en pausa: no hay atraso que recuperar
            return
        steps = 0
        while now >= self.next_tick and steps < C.MAX_CATCHUP_STEPS:
            core.step_once()
            self.next_tick += C.PHYSICS_DT
            steps += 1
            if not core.match_running():
                break
        if steps >= C.MAX_CATCHUP_STEPS and now >= self.next_tick:
            self.next_tick = now              # demasiado atraso: se descarta en vez de acelerar

    def _handle_control(self, msg):
        t = msg.get("type")
        if t == P.EV_READY:
            self.ready = True
            self.ready_info = dict(msg, inline=True)
        elif t == P.EV_ACK:
            sent = self.pending.pop(msg.get("cid"), None)
            rtt = (self.clock() - sent[1]) if sent else None
            self.last_confirmed = {"cmd": msg.get("cmd"), "cid": msg.get("cid"), "ok": msg.get("ok"),
                                   "rtt": rtt, "at": self.clock()}
        return False

    # ------------------------------------------------------------------ salud
    def fail(self, message, detail=""):
        if self.error is None:
            self.error = message
            self.error_detail = detail or ""

    def check_health(self):
        return self.error

    def debug_lines(self):
        lc = self.last_confirmed
        if lc:
            ok = "ok" if lc["ok"] else "rechazada"
            rtt = f", {lc['rtt'] * C.MS_PER_SECOND:.0f} ms" if lc["rtt"] is not None else ""
            confirmed = f"{lc['cmd']} #{lc['cid']} ({ok}{rtt}) hace {self.clock() - lc['at']:.1f} s"
        else:
            confirmed = "-"
        return {
            "sim_pid": "mismo hilo", "alive": self.alive, "confirmed": confirmed,
            "pending": len(self.pending),
            "inputs": f"{self.inputs_sent} enviados (se aplica la última por cuadro)",
            "received": f"{self.states_received} estados, {self.events_received} eventos",
        }
