"""Núcleo de la simulación, sin transporte.

Atiende las órdenes (con su ACK), aplica las fotos de controles, avanza el
partido un paso fijo y produce estados y eventos. NO sabe cómo viajan los
mensajes: eso lo define cada subclase.
  * SimulationServer (fdc/sim/process.py): proceso aparte con colas acotadas.
    Es lo que usan la versión de escritorio y el servidor online (una por sala).
  * InlineSimulation (fdc/sim/inline.py): en el navegador, donde no hay
    procesos, corre dentro de la misma página.
Así la lógica de la simulación es UNA sola, la misma en los tres lugares.
"""
import logging
import os
import sys
import time

from .. import config as C
from .. import protocol as P
from .match import Match

log = logging.getLogger("fdc.sim")


class SimulationCore:
    def __init__(self, options):
        self.test_mode = bool(options.get("test_mode"))
        self.seed = options.get("seed")
        self.duration = options.get("duration")   # partidos cortos para pruebas/demostración
        self.match = None
        self.eid = 0
        self.seq = 0
        self.press = [[P.PressCounter(), P.PressCounter()] for _ in range(2)]
        self.last_input_time = time.monotonic()
        self.running = True
        self.dropped_cosmetic = 0
        self.dropped_states = 0

    # ------------------------------------------------------------------ transporte (subclases)
    def put_reliable(self, msg):
        """Entrega garantizada (órdenes confirmadas, goles, poderes...)."""
        raise NotImplementedError

    def put_cosmetic(self, msg):
        """Entrega si hay lugar; devuelve False si se descartó."""
        raise NotImplementedError

    def put_state(self, snap):
        """Estado reemplazable: "el último gana"."""
        raise NotImplementedError

    # ------------------------------------------------------------------ envío
    def ready_event(self):
        return P.make_event(P.EV_READY, None, None, pid=os.getpid(), protocol=C.PROTOCOL_VERSION,
                            hz=C.PHYSICS_HZ, test_mode=self.test_mode, seed=self.seed,
                            pygame_loaded="pygame" in sys.modules)

    def emit(self, etype, match_id=None, **payload):
        self.eid += 1
        msg = P.make_event(etype, self.eid, match_id, **payload)
        if etype in P.COSMETIC_EVENTS:
            if not self.put_cosmetic(msg):
                self.dropped_cosmetic += 1   # política explícita: sólo cosméticos
            return
        self.put_reliable(msg)

    def publish_state(self):
        self.seq += 1
        snap = self.match.snapshot(self.seq)
        snap["dropped_states"] = self.dropped_states
        snap["dropped_cosmetic"] = self.dropped_cosmetic
        self.put_state(snap)

    def flush_match_events(self, events):
        mid = self.match.id if self.match else None
        for etype, data in events:
            self.emit(etype, mid, **data)

    # ------------------------------------------------------------------ órdenes
    def handle_command(self, cmd):
        ctype, cid = cmd.get("type"), cmd.get("cid")
        ack = lambda ok=True, detail="", match=None: self.put_reliable(P.make_ack(  # noqa: E731
            cid, ctype, ok, match if match is not None else (self.match.id if self.match else None),
            detail))

        if ctype == P.CMD_START or ctype == P.CMD_RESTART:
            chars = cmd.get("characters") or (self.match.characters if self.match else ("?", "?"))
            seed = cmd.get("seed", self.seed)
            # un partido nuevo es un objeto nuevo: no arrastra efectos ni estado viejo
            self.match = Match(cmd["match"], seed=seed, characters=chars, duration=self.duration,
                               golden_goal=bool(cmd.get("golden_goal", False)))
            self.last_input_time = time.monotonic()
            log.info("%s partido #%s (%s vs %s, semilla %s)", ctype, self.match.id,
                     chars[0], chars[1], self.match.seed)
            ack(True, f"semilla {self.match.seed}")
            self.publish_state()
        elif ctype == P.CMD_PAUSE:
            if self.match is None:
                ok = False
            elif cmd.get("after_goal"):
                # online: queda pendiente hasta después del próximo gol
                ok = self.match.request_pause_after_goal(cmd.get("by"))
            else:
                ok = self.match.pause(cmd.get("reason", P.PAUSE_REASON_USER))
            ack(ok, "" if ok else "no hay partido en curso")
            if ok:
                self.publish_state()
        elif ctype == P.CMD_RESUME:
            ok = self.match is not None and self.match.resume()
            self.last_input_time = time.monotonic()
            ack(ok, "" if ok else "no estaba en pausa")
            if ok:
                self.publish_state()
        elif ctype == P.CMD_END:
            self.match = None
            ack(True)
        elif ctype == P.CMD_DEBUG_POWER:
            if not self.test_mode or self.match is None:
                ack(False, "modo de prueba desactivado" if not self.test_mode else "sin partido")
                return
            ok, detail, events = self.match.debug_power(cmd.get("power"), cmd.get("mode", "spawn"))
            ack(ok, detail)
            self.flush_match_events(events)
        elif ctype == P.CMD_DEBUG_CRASH:
            if not self.test_mode:
                ack(False, "modo de prueba desactivado")
                return
            ack(True, "fallo provocado")
            raise RuntimeError("Fallo provocado desde el modo de prueba (F12)")
        elif ctype == P.CMD_SHUTDOWN:
            ack(True)
            self.running = False
        else:
            ack(False, f"orden desconocida {ctype!r}")

    # ------------------------------------------------------------------ controles y pasos
    def apply_inputs(self, latest):
        """Última foto de controles: los contadores dicen cuántas pulsaciones hubo."""
        self.last_input_time = time.monotonic()
        for idx, (left, right, jumps, kicks) in enumerate(latest["p"][:2]):
            new_j = self.press[idx][0].update(jumps)
            new_k = self.press[idx][1].update(kicks)
            if self.match is not None:
                self.match.set_input(idx, left, right, new_j, new_k)

    def match_running(self):
        m = self.match
        return m is not None and not m.paused and m.phase != P.PHASE_FINISHED

    def step_once(self):
        """Un paso fijo de física; publica un estado cada STATE_EVERY_TICKS pasos."""
        events = self.match.step(C.PHYSICS_DT)
        self.flush_match_events(events)
        if self.match.tick % C.STATE_EVERY_TICKS == 0 or self.match.phase == P.PHASE_FINISHED:
            self.publish_state()
