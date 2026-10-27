"""Secondary process: the simulation.

It is the only authority over movements, collisions, clock, goals, powers,
bombs and randomness. It creates no windows and handles no audio: it does
not even import pygame (it reports that in the READY message to prove it).

Loop:
* With no match, paused or with the match over -> BLOCKING wait on the
  command queue with a time limit (no busy waiting).
* With a match in play -> fixed step of 1/120 s. Between steps it sleeps
  with stop_event.wait(rest), which also wakes up at once if the interface
  asks to shut down.
"""
import logging
import multiprocessing
import os
import queue
import signal
import sys
import time
import traceback

from fdc import config
from fdc import protocol
from fdc.sim import core

log = logging.getLogger("fdc.sim")
LOG_FORMAT = ("%(asctime)s [%(processName)s pid=%(process)d] %(levelname)s "
              "%(name)s: %(message)s")


class SimulationServer(core.SimulationCore):
    """The simulation core (fdc/sim/core.py) in its own process, with
    queues."""

    def __init__(self, cmd_q, input_q, state_q, event_q, stop_event,
                 options):
        super().__init__(options)
        self.cmd_q = cmd_q
        self.input_q = input_q
        self.state_q = state_q
        self.event_q = event_q
        self.stop_event = stop_event
        self.last_parent_check = 0.0
        self.last_heartbeat = 0.0

    # ------------------------------------------------------ sending (queues)
    def put_cosmetic(self, msg):
        try:
            self.event_q.put_nowait(msg)
            return True
        except queue.Full:
            return False

    def put_reliable(self, msg):
        """Guaranteed delivery unless everything is shutting down."""
        while True:
            try:
                self.event_q.put(msg, timeout=config.IPC.EVENT_PUT_RETRY)
                return True
            except queue.Full:
                if self.stop_event.is_set() or not parent_alive():
                    log.warning("could not deliver %s: shutting down",
                                msg.get("type"))
                    return False
                log.warning("event queue full; retrying %s", msg.get("type"))

    def put_state(self, snap):
        """Replaceable states: if the queue is full the OLDEST is dropped."""
        try:
            self.state_q.put_nowait(snap)
            return
        except queue.Full:
            self._drop_oldest_state()
        try:
            self.state_q.put_nowait(snap)
        except queue.Full:
            self.dropped_states += 1        # the UI gets the next one instead

    def _drop_oldest_state(self):
        try:
            self.state_q.get_nowait()       # removes an old state
            self.dropped_states += 1
        except queue.Empty:
            pass

    # ---------------------------------------------------- receiving (queues)
    def drain_commands(self):
        while True:
            try:
                cmd = self.cmd_q.get_nowait()
            except queue.Empty:
                return
            self.handle_command(cmd)

    def drain_inputs(self):
        """Compacts: only the latest snapshot matters; the counters lose no
        presses."""
        latest = None
        while True:
            try:
                latest = self.input_q.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            self.apply_inputs(latest)

    # ------------------------------------------------------------------ loop
    def run(self):
        """Main loop of the process (ends on shutdown or if the UI died)."""
        self.put_reliable(self.ready_event())
        next_tick = time.monotonic()
        while self.running and not self.stop_event.is_set():
            if not self._parent_still_alive():
                return
            if not self.match_running():
                self._idle()
                next_tick = time.monotonic()
                continue
            next_tick = self._play(next_tick)

    def _play(self, next_tick):
        """One turn with a match running. Returns the next step time."""
        self.drain_commands()
        self.drain_inputs()
        if not self.match_running() or self._watchdog():
            return next_tick
        return self._advance(next_tick)

    def _parent_still_alive(self):
        """Checks every PARENT_CHECK_EVERY s that the interface is alive."""
        now = time.monotonic()
        if now - self.last_parent_check > config.IPC.PARENT_CHECK_EVERY:
            self.last_parent_check = now
            if not parent_alive():
                log.error("the interface is gone: the simulation ends")
                return False
        return True

    def _watchdog(self):
        """Pauses if the interface stopped sending controls (blocked window,
        etc.). Returns True if it paused."""
        if (time.monotonic() - self.last_input_time
                <= config.MatchRules.INPUT_WATCHDOG):
            return False
        self.match.pause(protocol.PAUSE_REASON_WATCHDOG)
        self.emit(protocol.EV_PAUSED, self.match.id,
                  reason=protocol.PAUSE_REASON_WATCHDOG)
        self.publish_state()
        return True

    def _advance(self, next_tick):
        """Runs the due fixed steps and sleeps until the next one."""
        next_tick = core.catch_up(self, time.monotonic(), next_tick)
        wait = next_tick - time.monotonic()
        if wait > 0:
            self.stop_event.wait(wait)
        return next_tick

    def _idle(self):
        """No match running: blocking wait for a command (bounded)."""
        try:
            cmd = self.cmd_q.get(timeout=config.IPC.IDLE_WAIT)
        except queue.Empty:
            cmd = None
        if cmd is not None:
            self.handle_command(cmd)
        self.drain_inputs()
        if self.match is not None and self.match.paused:
            self._heartbeat()

    def _heartbeat(self):
        """While paused, a state from time to time: the UI sees the SIM is
        alive."""
        now = time.monotonic()
        if now - self.last_heartbeat > config.IPC.PAUSED_HEARTBEAT:
            self.last_heartbeat = now
            self.publish_state()


def parent_alive():
    """True if the process that launched this one is still running."""
    parent = multiprocessing.parent_process()
    return parent is None or parent.is_alive()


def _setup_logging():
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        handlers.append(logging.FileHandler(
            os.path.join(config.LOG_DIR, "fdc.log"), mode="a",
            encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT,
                        handlers=handlers, force=True)


def simulation_main(cmd_q, input_q, state_q, event_q, stop_event, options):
    """Entry point of the process (importable, works with spawn)."""
    # Ctrl+C in the terminal reaches both processes; the UI coordinates the
    # shutdown.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if options.get("log", True):
        _setup_logging()
    server = SimulationServer(cmd_q, input_q, state_q, event_q, stop_event,
                              options)
    sys.exit(_run_server(server))


def _run_server(server):
    """Runs the loop; reports a crash and always says goodbye."""
    exit_code = 0
    try:
        server.run()
        log.info("simulation finished in order")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        exit_code = 1         # any failure is reported to the interface
        _report_crash(server, exc)
    finally:
        _say_goodbye(server, exit_code)
    return exit_code


def _report_crash(server, exc):
    log.exception("simulation error")
    server.put_reliable(protocol.make_event(
        protocol.EV_ERROR, None, None, message=str(exc),
        traceback=traceback.format_exc()))


def _say_goodbye(server, exit_code):
    """Sends BYE and closes the queues without hanging the exit."""
    # Pending states and cosmetic events can be lost without harm: do not
    # block the exit waiting for the UI to read them.
    server.state_q.cancel_join_thread()
    server.put_reliable(protocol.make_event(
        protocol.EV_BYE, None, None, code=exit_code,
        dropped_states=server.dropped_states,
        dropped_cosmetic=server.dropped_cosmetic))
    # BYE must arrive: wait for the feeder thread to flush it, unless the UI
    # no longer exists.
    if not parent_alive():
        server.event_q.cancel_join_thread()
    server.event_q.close()
    server.state_q.close()
