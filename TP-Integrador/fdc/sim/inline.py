"""Simulation inside the same page (browser version).

In the browser (pygbag, WebAssembly) there are no processes or threads, so
the local modes (tournament and local multiplayer) cannot launch the
simulation process. InlineLink keeps the SAME contract as SimLink
(fdc/link.py) with the SAME simulation core (fdc/sim/core.py): commands are
acknowledged with an ACK, controls travel as snapshots with counters and
states carry the match and update numbers. The difference is that
everything happens in the same thread, once per frame:

    poll():  pending commands -> latest controls snapshot -> physics steps
             until "now" (fixed step of 1/120 s) -> events and latest state

The desktop version still uses two processes (SimLink), and the online mode
uses one process per room on the server.
"""
import logging
import time
import traceback

from fdc import config
from fdc import link
from fdc import protocol
from fdc.sim import core

log = logging.getLogger("fdc.inline")


class InlineSimulation(core.SimulationCore):
    """The core with in-memory "queues": lists emptied every frame."""

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
            self.dropped_states += 1      # the screen only draws the newest
        self.state = snap

    def take(self):
        """Returns and clears (events, latest state)."""
        events, state = self.events, self.state
        self.events, self.state = [], None
        return events, state


class InlineLink(link.MatchLink):
    """MatchLink that simulates in the same thread (browser)."""
    inline = True

    def __init__(self, test_mode=False, seed=None, duration=None,
                 clock=time.perf_counter):
        self.options = {"test_mode": test_mode, "seed": seed,
                        "duration": duration}
        self.clock = clock
        self.core = None
        self._reset_state()

    def _reset_state(self):
        self.ready, self.ready_info = False, {}
        self.error, self.error_detail = None, ""
        self.shutdown_report = None
        self.commands, self.latest_input = [], None
        self.pending, self.next_cid = {}, 1
        self.iseq = 0
        self.next_tick = self.clock()
        self.last_confirmed = None
        self.inputs_sent = 0
        self.states_received = self.events_received = 0

    # ------------------------------------------------------------- lifecycle
    def start(self):
        self._reset_state()
        self.core = InlineSimulation(self.options)
        self.core.put_reliable(self.core.ready_event())

    def stop(self):
        if self.core is None:
            return self.shutdown_report
        self.core = None
        self.shutdown_report = {"method": "same_thread", "bye": True,
                                "exitcode": 0}
        return self.shutdown_report

    @property
    def alive(self):
        return self.core is not None and self.error is None

    # --------------------------------------------------------------- sending
    def send_command(self, ctype, **payload):
        if self.core is None or self.error:
            return None
        cid = self.next_cid
        self.next_cid += 1
        self.commands.append(protocol.make_command(ctype, cid, **payload))
        self.pending[cid] = (ctype, self.clock())
        return cid

    def send_input(self, players, seqs=None):
        if self.core is None or self.error:
            return
        self.iseq += 1
        # Replaceable: the newest one wins.
        self.latest_input = protocol.make_input(self.iseq, players, seqs)
        self.inputs_sent += 1

    # ------------------------------------------------------------ simulation
    def poll(self):
        """Advances the simulation until now; returns (events, state)."""
        sim = self.core
        if sim is None or self.error:
            return [], None
        try:
            self._feed(sim)
            self._advance()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Shown on the error screen, as in the desktop version.
            log.exception("simulation error")
            self.fail("La simulación informó un error: " + str(exc),
                      traceback.format_exc())
        events, state = sim.take()
        return self._received(events, state), state

    def _feed(self, sim):
        """Hands the pending commands and the latest controls to the core."""
        commands, self.commands = self.commands, []
        for cmd in commands:
            sim.handle_command(cmd)
        if self.latest_input is not None:
            sim.apply_inputs(self.latest_input)
            self.latest_input = None

    def _received(self, events, state):
        out = []
        for msg in events:
            self.events_received += 1
            if not self._handle_control(msg):
                out.append(msg)
        if state is not None:
            self.states_received += 1
        return out

    def _advance(self):
        sim = self.core
        now = self.clock()
        if not sim.match_running():
            self.next_tick = now    # no match or paused: no delay to recover
            return
        self.next_tick = core.catch_up(sim, now, self.next_tick)

    def _handle_control(self, msg):
        kind = msg.get("type")
        if kind == protocol.EV_READY:
            self.ready = True
            self.ready_info = dict(msg, inline=True)
        elif kind == protocol.EV_ACK:
            sent = self.pending.pop(msg.get("cid"), None)
            rtt = (self.clock() - sent[1]) if sent else None
            self.last_confirmed = {"cmd": msg.get("cmd"),
                                   "cid": msg.get("cid"), "ok": msg.get("ok"),
                                   "rtt": rtt, "at": self.clock()}
        return False

    # ---------------------------------------------------------------- health
    def fail(self, message, detail=""):
        """Records the first failure (shown to the player)."""
        if self.error is None:
            self.error = message
            self.error_detail = detail or ""

    def check_health(self):
        return self.error

    def debug_lines(self):
        """Lines of the F3 panel about the link (shown in Spanish)."""
        return {
            "sim_pid": "mismo hilo", "alive": self.alive,
            "confirmed": self._confirmed_text(),
            "pending": len(self.pending),
            "inputs": f"{self.inputs_sent} enviados "
                      "(se aplica la última por cuadro)",
            "received": f"{self.states_received} estados, "
                        f"{self.events_received} eventos",
        }

    def _confirmed_text(self):
        confirmed = self.last_confirmed
        if not confirmed:
            return "-"
        result = "ok" if confirmed["ok"] else "rechazada"
        rtt = ""
        if confirmed["rtt"] is not None:
            rtt = f", {confirmed['rtt'] * config.MS_PER_SECOND:.0f} ms"
        age = self.clock() - confirmed["at"]
        return (f"{confirmed['cmd']} #{confirmed['cid']} ({result}{rtt}) "
                f"hace {age:.1f} s")
