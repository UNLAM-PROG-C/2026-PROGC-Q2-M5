"""Link between the interface and the simulation process.

SimLink wraps EVERYTHING the interface knows about multiprocessing (Facade
pattern):
  * it creates the four bounded queues and the shutdown Event with the
    "spawn" context;
  * it launches the process (importable entry point:
    fdc.sim.process.simulation_main);
  * it sends reliable commands (with a cid and an awaited ACK) and
    replaceable controls;
  * it receives without blocking (get_nowait: if nothing came, drawing goes
    on);
  * it detects failures: dead process, error message or missing ACK;
  * it coordinates the shutdown: command + Event, draining until BYE, join
    with a time limit and, only as an exceptional recovery,
    terminate()/kill().
"""
import logging
import multiprocessing
import os
import queue
import time

from fdc import config
from fdc import link
from fdc import protocol
from fdc.sim import process

log = logging.getLogger("fdc.ipc")

# Command names shown to the player in error messages.
COMMAND_NAMES = {
    protocol.CMD_START: "iniciar", protocol.CMD_PAUSE: "pausar",
    protocol.CMD_RESUME: "continuar", protocol.CMD_RESTART: "reiniciar",
    protocol.CMD_END: "terminar", protocol.CMD_SHUTDOWN: "cerrar",
    protocol.CMD_SKIP_GOAL: "saltear el gol",
    protocol.CMD_DEBUG_POWER: "poder de prueba",
    protocol.CMD_DEBUG_CRASH: "fallo de prueba",
}
QUEUE_ERRORS = (queue.Empty, OSError, ValueError)  # empty or closed queue
FORCE_JOIN_WAIT = 1.0       # s: wait after terminate() or kill()


class SimLink(link.MatchLink):
    """Local MatchLink: one simulation process and its queues."""

    def __init__(self, test_mode=False, seed=None, log_to_file=True,
                 duration=None):
        self.ctx = multiprocessing.get_context("spawn")
        self.options = {"test_mode": test_mode, "seed": seed,
                        "log": log_to_file, "duration": duration}
        self.proc = None
        self._reset_state()

    def _reset_state(self):
        self.ready, self.ready_info, self.sim_pid = False, {}, None
        self.error, self.error_detail = None, ""
        self.bye, self.stopping = None, False
        self.pending, self.next_cid = {}, 1
        self.last_confirmed = None
        self.iseq = 0
        self.inputs_sent = self.inputs_dropped = 0
        self.states_received = self.events_received = 0
        self.deduper = protocol.EventDeduper()
        self.shutdown_report = None
        self.started_at = time.monotonic()

    # ------------------------------------------------------------- lifecycle
    def start(self):
        self._reset_state()
        self._create_channels()
        self.proc = self.ctx.Process(
            target=process.simulation_main, name="fdc-simulation",
            args=(self.cmd_q, self.input_q, self.state_q, self.event_q,
                  self.stop_event, self.options),
            daemon=True)   # safety net: it is never left orphaned
        self.proc.start()
        log.info("simulation process launched (pid %s)", self.proc.pid)

    def _create_channels(self):
        """The four bounded queues and the shutdown Event."""
        ctx = self.ctx
        self.cmd_q = ctx.Queue(config.IPC.COMMAND_QUEUE_SIZE)
        self.input_q = ctx.Queue(config.IPC.INPUT_QUEUE_SIZE)
        self.state_q = ctx.Queue(config.IPC.STATE_QUEUE_SIZE)
        self.event_q = ctx.Queue(config.IPC.EVENT_QUEUE_SIZE)
        self.stop_event = ctx.Event()

    @property
    def ui_pid(self):
        return os.getpid()

    # --------------------------------------------------------------- sending
    def send_command(self, ctype, **payload):
        """Reliable command. Returns the cid or None if it was not sent."""
        if self.proc is None or self.error:
            return None
        cid = self.next_cid
        self.next_cid += 1
        if not self._put_command(protocol.make_command(ctype, cid,
                                                       **payload)):
            self.fail(f"No se pudo enviar la orden «{_command_name(ctype)}»: "
                      "la simulación no está leyendo órdenes.")
            return None
        self.pending[cid] = (ctype, time.monotonic())
        return cid

    def _put_command(self, msg):
        """Blocks at most COMMAND_PUT_TIMEOUT: a command is never dropped
        silently; if it does not fit (False), that is a visible failure."""
        try:
            self.cmd_q.put(msg, timeout=config.IPC.COMMAND_PUT_TIMEOUT)
            return True
        except queue.Full:
            return False

    def send_input(self, players):
        """Replaceable controls snapshot: dropped if the queue is full."""
        if self.proc is None or self.error:
            return
        self.iseq += 1
        try:
            self.input_q.put_nowait(protocol.make_input(self.iseq, players))
            self.inputs_sent += 1
        except queue.Full:
            # The next snapshot carries the same counters.
            self.inputs_dropped += 1

    # ------------------------------------------------------------- receiving
    def _handle_control(self, msg):
        """Handles messages of the link itself. True if it consumed it."""
        kind = msg.get("type")
        if kind == protocol.EV_READY:
            self._on_ready(msg)
        elif kind == protocol.EV_ACK:
            self._on_ack(msg)
        elif kind == protocol.EV_ERROR:
            self.fail("La simulación informó un error: "
                      + str(msg.get("message")), msg.get("traceback", ""))
            return True
        elif kind == protocol.EV_BYE:
            self.bye = msg
            return True
        return False

    def _on_ready(self, msg):
        self.ready = True
        self.ready_info = msg
        self.sim_pid = msg.get("pid")
        log.info("simulation ready (pid %s, pygame loaded: %s)",
                 self.sim_pid, msg.get("pygame_loaded"))

    def _on_ack(self, msg):
        sent = self.pending.pop(msg.get("cid"), None)
        rtt = (time.monotonic() - sent[1]) if sent else None
        self.last_confirmed = {
            "cmd": msg.get("cmd"), "cid": msg.get("cid"), "ok": msg.get("ok"),
            "detail": msg.get("detail", ""), "match": msg.get("match"),
            "rtt": rtt, "at": time.monotonic()}

    def poll(self):
        """Reads without blocking. Returns (new messages, latest state)."""
        if self.proc is None:
            return [], None
        return self._read_events(), self._latest_state()

    def _read_events(self):
        out = []
        for _ in range(config.IPC.MAX_EVENTS_PER_FRAME):
            try:
                msg = self.event_q.get_nowait()
            except QUEUE_ERRORS:
                break
            self.events_received += 1
            if not self._handle_control(msg) and self.deduper.fresh(msg):
                out.append(msg)
        return out

    def _latest_state(self):
        state = None
        while True:
            try:
                state = self.state_q.get_nowait()   # the newest wins
                self.states_received += 1
            except QUEUE_ERRORS:
                return state

    # ---------------------------------------------------------------- health
    def fail(self, message, detail=""):
        """Records the first failure (shown to the player)."""
        if self.error is None:
            self.error = message
            self.error_detail = detail or ""
            log.error("%s\n%s", message, detail)

    def check_health(self):
        if self.error or self.proc is None or self.stopping:
            return self.error
        now = time.monotonic()
        if not self.proc.is_alive():
            self.fail("La simulación se detuvo inesperadamente "
                      f"(código de salida {self.proc.exitcode}).")
        elif not self.ready and now - self.started_at > \
                config.IPC.READY_TIMEOUT:
            self.fail("La simulación no confirmó que estaba lista a tiempo.")
        else:
            self._check_acks(now)
        return self.error

    def _check_acks(self, now):
        """Fails if a command waited for its ACK longer than allowed."""
        for cid, (ctype, sent) in self.pending.items():
            if now - sent > config.IPC.ACK_TIMEOUT:
                self.fail("La simulación no confirmó la orden "
                          f"«{_command_name(ctype)}» (#{cid}).")
                break

    @property
    def alive(self):
        return self.proc is not None and self.proc.is_alive()

    # -------------------------------------------------------------- shutdown
    def stop(self):
        """Coordinated shutdown. Returns a report of how it ended."""
        if self.proc is None:
            return self.shutdown_report
        self.stopping = True
        started = time.monotonic()
        self._request_stop()
        discarded = self._drain_until_bye(started) + self._drain_states()
        method = self._join_or_force()
        self._close_queues()
        self.shutdown_report = self._report(method, discarded, started)
        log.info("simulation shutdown: %s", self.shutdown_report)
        self.proc = None
        return self.shutdown_report

    def _report(self, method, discarded, started):
        return {"method": method, "exitcode": self.proc.exitcode,
                "bye": self.bye is not None, "discarded": discarded,
                "elapsed": time.monotonic() - started}

    def _request_stop(self):
        """Asks both ways: the command (part of the protocol, it gets an ACK)
        and the Event (it wakes up any wait at once)."""
        try:
            self.cmd_q.put_nowait(
                protocol.make_command(protocol.CMD_SHUTDOWN, self.next_cid))
        except (queue.Full, ValueError, OSError):
            pass
        self.stop_event.set()

    def _drain_until_bye(self, started):
        """Reads events until BYE: if the SIM has events in flight, its
        feeder thread cannot end until someone reads them."""
        discarded = 0
        deadline = started + config.IPC.SHUTDOWN_BYE_TIMEOUT
        while self.bye is None and time.monotonic() < deadline:
            try:   # bounded blocking wait
                msg = self.event_q.get(timeout=config.IPC.BYE_POLL)
            except queue.Empty:
                if not self.proc.is_alive():
                    break
                continue
            except (OSError, ValueError):
                break
            discarded += not self._handle_control(msg)
        return discarded

    def _drain_states(self):
        discarded = 0
        while True:
            try:
                self.state_q.get_nowait()
                discarded += 1
            except QUEUE_ERRORS:
                return discarded

    def _join_or_force(self):
        """Waits for the process with a time limit; forces it only if it
        does not answer. Returns how it ended."""
        self.proc.join(config.IPC.JOIN_TIMEOUT)
        if not self.proc.is_alive():
            return "orderly"
        log.warning("the simulation did not end in %.1f s: using terminate()",
                    config.IPC.JOIN_TIMEOUT)
        self.proc.terminate()
        self.proc.join(FORCE_JOIN_WAIT)
        if not self.proc.is_alive():
            return "terminate"
        log.error("terminate() was not enough: using kill()")
        self.proc.kill()
        self.proc.join(FORCE_JOIN_WAIT)
        return "kill"

    def _close_queues(self):
        """Nobody will read what the UI left in its queues: cancel_join_thread
        avoids the UI hanging on exit because of that."""
        for q in (self.cmd_q, self.input_q):
            q.cancel_join_thread()
            q.close()
        for q in (self.state_q, self.event_q):
            q.close()

    def restart(self):
        self.stop()
        self.start()

    def debug_lines(self):
        """Lines of the F3 panel about the link (shown in Spanish)."""
        return {
            "sim_pid": self.sim_pid or (self.proc.pid if self.proc else None),
            "alive": self.alive,
            "confirmed": _confirmed_text(self.last_confirmed),
            "pending": len(self.pending),
            "inputs": f"{self.inputs_sent} enviados / "
                      f"{self.inputs_dropped} reemplazados",
            "received": f"{self.states_received} estados, "
                        f"{self.events_received} eventos",
        }


def _command_name(ctype):
    return COMMAND_NAMES.get(ctype, ctype)


def _confirmed_text(confirmed):
    """F3 text of the last acknowledged command."""
    if not confirmed:
        return "—"
    age = time.monotonic() - confirmed["at"]
    result = "ok" if confirmed["ok"] else "rechazada"
    rtt = ""
    if confirmed["rtt"] is not None:
        rtt = f", {confirmed['rtt'] * config.MS_PER_SECOND:.0f} ms"
    return (f"{confirmed['cmd']} #{confirmed['cid']} ({result}{rtt}) "
            f"hace {age:.1f} s")
