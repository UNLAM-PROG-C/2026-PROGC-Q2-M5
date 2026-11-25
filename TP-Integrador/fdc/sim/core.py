"""Simulation core, without transport.

It handles the commands (with their ACK), applies the controls snapshots,
advances the match one fixed step and produces states and events. It does
NOT know how messages travel: each subclass defines that (Template Method).
  * SimulationServer (fdc/sim/process.py): its own process with bounded
    queues. Used by the desktop version and by the online server (one per
    room).
"""
import logging
import os
import sys
import time

from fdc import config
from fdc import protocol
from fdc.sim import match

log = logging.getLogger("fdc.sim")
NO_CHARACTERS = ("?", "?")      # characters when a command did not send them


class SimulationCore:
  """Commands, controls and fixed steps of one match (no transport)."""

  def __init__(self, options):
    self.test_mode = bool(options.get("test_mode"))
    self.seed = options.get("seed")
    # Short matches for tests or demonstrations.
    self.duration = options.get("duration")
    self.untimed = options.get("untimed")
    self.match = None
    self.eid = self.seq = 0
    self.ack = [0, 0]       # online: last controls applied per player
    self.press = [[protocol.PressCounter(), protocol.PressCounter()]
                  for _ in range(2)]
    self.last_input_time = time.monotonic()
    self.running, self.dropped_cosmetic, self.dropped_states = True, 0, 0
    self.handlers = self._command_handlers()

  def _command_handlers(self):
    """Command pattern: each command type has its handler."""
    return {
        protocol.CMD_START: self._start, protocol.CMD_RESTART: self._start,
        protocol.CMD_PAUSE: self._pause, protocol.CMD_RESUME: self._resume,
        protocol.CMD_END: self._end,
        protocol.CMD_SKIP_GOAL: self._skip_goal,
        protocol.CMD_DEBUG_POWER: self._debug_power,
        protocol.CMD_DEBUG_CRASH: self._debug_crash,
        protocol.CMD_SHUTDOWN: self._shutdown,
    }

  # ------------------------------------------------ transport (subclasses)
  def put_reliable(self, msg):
    """Guaranteed delivery (acknowledged commands, goals, powers...)."""
    raise NotImplementedError

  def put_cosmetic(self, msg):
    """Delivers if there is room; returns False if it was dropped."""
    raise NotImplementedError

  def put_state(self, snap):
    """Replaceable state: "the newest wins"."""
    raise NotImplementedError

  # --------------------------------------------------------------- sending
  def ready_event(self):
    """READY message: pid, protocol, rate and whether pygame is loaded."""
    return protocol.make_event(
        protocol.EV_READY, None, None, pid=os.getpid(),
        protocol=config.PROTOCOL_VERSION, hz=config.PHYSICS_HZ,
        test_mode=self.test_mode, seed=self.seed,
        pygame_loaded="pygame" in sys.modules)

  def emit(self, etype, match_id=None, **payload):
    """Sends an event; cosmetic ones may be dropped (and counted)."""
    self.eid += 1
    msg = protocol.make_event(etype, self.eid, match_id, **payload)
    if etype in protocol.COSMETIC_EVENTS:
      if not self.put_cosmetic(msg):
        self.dropped_cosmetic += 1   # explicit policy: cosmetic only
      return
    self.put_reliable(msg)

  def publish_state(self):
    self.seq += 1
    snap = self.match.snapshot(self.seq)
    # What the clients need to reconcile their prediction: the last
    # controls snapshot this simulation applied for each player.
    snap["ack"] = list(self.ack)
    snap["dropped_states"] = self.dropped_states
    snap["dropped_cosmetic"] = self.dropped_cosmetic
    self.put_state(snap)

  def flush_match_events(self, events):
    match_id = self.match.id if self.match else None
    for etype, data in events:
      self.emit(etype, match_id, **data)

  # -------------------------------------------------------------- commands
  def handle_command(self, cmd):
    """Runs the handler of the command and acknowledges it."""
    handler = self.handlers.get(cmd.get("type"))
    if handler is None:
      self._ack(cmd, False, f"orden desconocida {cmd.get('type')!r}")
      return
    handler(cmd)

  def _ack(self, cmd, ok=True, detail=""):
    """ACK of `cmd` with the current match id (texts are shown)."""
    match_id = self.match.id if self.match else None
    self.put_reliable(protocol.make_ack(cmd.get("cid"), cmd.get("type"),
                                        ok, match_id, detail))

  def _start(self, cmd):
    """A new match is a new object: no old effects or state remain."""
    chars = cmd.get("characters") or (
        self.match.characters if self.match else NO_CHARACTERS)
    self.match = match.Match(
        cmd["match"], seed=cmd.get("seed", self.seed), characters=chars,
        duration=self.duration, untimed=self.untimed,
        golden_goal=bool(cmd.get("golden_goal", False)),
        presentation=bool(cmd.get("presentation", True)))
    self.last_input_time = time.monotonic()
    log.info("%s match #%s (%s vs %s, seed %s)", cmd.get("type"),
             self.match.id, chars[0], chars[1], self.match.seed)
    self._ack(cmd, True, f"semilla {self.match.seed}")
    self.publish_state()

  def _pause(self, cmd):
    if self.match is None:
      ok = False
    elif cmd.get("after_goal"):
      # Online: it waits until after the next goal.
      ok = self.match.request_pause_after_goal(cmd.get("by"))
    else:
      ok = self.match.pause(
          cmd.get("reason", protocol.PAUSE_REASON_USER))
    self._ack(cmd, ok, "" if ok else "no hay partido en curso")
    if ok:
      self.publish_state()

  def _resume(self, cmd):
    ok = self.match is not None and self.match.resume()
    self.last_input_time = time.monotonic()
    self._ack(cmd, ok, "" if ok else "no estaba en pausa")
    if ok:
      self.publish_state()

  def _end(self, cmd):
    self.match = None
    self._ack(cmd, True)

  def _skip_goal(self, cmd):
    """The interface is done with the party and the replay of the goal:
        the match comes back from the centre right away."""
    ok, events = (self.match.skip_goal() if self.match is not None
                  else (False, []))
    self._ack(cmd, ok, "" if ok else "no hay gol en pantalla")
    if ok:
      self.flush_match_events(events)
      self.publish_state()

  def _debug_power(self, cmd):
    error = self._power_error(cmd.get("power"))
    if error or self.match is None:
      self._ack(cmd, False, error or "sin partido")
      return
    ok, detail, events = self.match.debug_power(
        cmd.get("power"), cmd.get("mode", "spawn"),
        seconds=cmd.get("seconds"), burn=cmd.get("burn"))
    self._ack(cmd, ok, detail)
    self.flush_match_events(events)

  def _power_error(self, power):
    if not (self.test_mode or self.untimed):
      return "modo de prueba desactivado"
    if not self.test_mode and power not in config.Presentation.SIM_POWERS:
      return "poder no disponible en presentación"
    return ""

  def _debug_crash(self, cmd):
    if not self.test_mode:
      self._ack(cmd, False, "modo de prueba desactivado")
      return
    self._ack(cmd, True, "fallo provocado")
    raise RuntimeError("Fallo provocado desde el modo de prueba (F12)")

  def _shutdown(self, cmd):
    self._ack(cmd, True)
    self.running = False

  # ---------------------------------------------------- controls and steps
  def apply_inputs(self, latest):
    """Latest controls snapshot: counters say how many presses there
        were."""
    self.last_input_time = time.monotonic()
    seqs = latest.get("seqs")
    if isinstance(seqs, list) and len(seqs) == 2:
      self.ack = [int(seqs[0]), int(seqs[1])]
    for idx, (left, right, jumps, kicks) in enumerate(latest["p"][:2]):
      new_jumps = self.press[idx][0].update(jumps)
      new_kicks = self.press[idx][1].update(kicks)
      if self.match is not None:
        self.match.set_input(idx, left, right, new_jumps, new_kicks)

  def match_running(self):
    current = self.match
    return (current is not None and not current.paused
            and current.phase != protocol.PHASE_FINISHED)

  def step_once(self):
    """One fixed physics step; publishes a state every
        STATE_EVERY_TICKS steps."""
    events = self.match.step(config.PHYSICS_DT)
    self.flush_match_events(events)
    if (self.match.tick % config.STATE_EVERY_TICKS == 0
            or self.match.phase == protocol.PHASE_FINISHED):
      self.publish_state()


def catch_up(sim, now, next_tick):
  """Runs the fixed steps due until `now` (at most MAX_CATCHUP_STEPS).
    Returns the time of the next step. Used by the simulation process."""
  steps = 0
  while now >= next_tick and steps < config.MAX_CATCHUP_STEPS:
    sim.step_once()
    next_tick += config.PHYSICS_DT
    steps += 1
    if not sim.match_running():
      break
  if steps >= config.MAX_CATCHUP_STEPS and now >= next_tick:
    next_tick = now   # too late: drop the delay instead of speeding up
  return next_tick
