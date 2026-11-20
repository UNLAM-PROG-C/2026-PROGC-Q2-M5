"""Bridge between one online room and its simulation process.

Each room in play has its own simulation PROCESS (the same of the local
version, through SimLink: bounded queues, ACKs, match numbers and shutdown
Event) and a bridge TASK of the server loop at 60 Hz that:
  * takes the controls of the two browsers to the process;
  * forwards events and about 30 states per second to the players;
  * runs the online rules: requested pause, "ready", 30 s limits,
    disconnections and forfeits.
Launching or closing the process may block, so it runs in an executor
thread and does not slow down the server loop.
"""
import asyncio
import collections
import logging
import math
import os
import time

from fdc import config
from fdc import ipc
from fdc import protocol
from fdc.online import lobby
from fdc.online import wire

log = logging.getLogger("fdc.server")
ONLINE = config.Online
# Score when the match ended before the first state.
NO_SCORE = [0, 0]


class RoomRunner:
  """Bridge task of one room and its simulation process."""

  def __init__(self, server, room_id):
    self.server = server
    self.room_id = room_id
    self.link = ipc.SimLink(log_to_file=server.sim_logs,
                            duration=server.duration, seed=server.seed)
    self.link_started = self.ready_logged = self.closed = False
    self.task = None
    self.created_at = time.monotonic()
    # States, events and controls since the last report...
    self.counts = collections.Counter()
    self.rates = {}         # ...and the same per second (panel and F3)
    self.last_info = self.created_at
    self._reset_match()

  def _reset_match(self):
    self.match = None   # {"id", "sids", "names", "chars", "start_msgs"}
    self.start_pending = False
    self.inputs = [[False, False, 0, 0] for _ in range(lobby.MAX_PLAYERS)]
    self.input_seqs = [0] * lobby.MAX_PLAYERS   # for the prediction ack
    self.last_state = None
    self.sent_seq = -1
    self.sent_at = -math.inf    # last state forwarded (s, monotonic)
    self.hold = set()   # reasons why the simulation must stay paused
    self.pause = None   # {"status", "by", "deadline", "ready"}
    self.away = {}      # side -> deadline to come back

  # ------------------------------------------------------------ lifecycle
  async def begin(self, match_id, sids, names, chars, start_msgs):
    """Starts a match (launches the process the first time)."""
    self._reset_match()
    self.match = {"id": match_id, "sids": sids, "names": names,
                  "chars": chars, "start_msgs": start_msgs}
    # The command leaves when the simulation confirms READY.
    self.start_pending = True
    if not self.link_started:
      await self._launch()
    log.info("room %s: match #%s %s (%s) vs %s (%s)", self.room_id,
             match_id, names[0], chars[0], names[1], chars[1])

  async def _launch(self):
    self.link_started = True
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, self.link.start)
    self.server.log_process(self.room_id, "proceso de simulación lanzado",
                            self.link.proc.pid)
    self.task = asyncio.create_task(self._pump())

  async def close(self):
    """Stops the bridge and closes the process in an executor thread."""
    self.closed = True
    if self.task is not None:
      self.task.cancel()
    if not self.link_started:
      return
    pid = self.link.sim_pid or (self.link.proc.pid if self.link.proc
                                else None)
    loop = asyncio.get_running_loop()
    report = await loop.run_in_executor(None, self.link.stop)
    self._log_closed(pid, report)

  def _log_closed(self, pid, report):
    log.info("room %s: simulation process closed %s", self.room_id,
             report)
    if report:
      detail = (f"cierre {report['method']}, "
                f"BYE {'sí' if report['bye'] else 'no'}")
      self.server.log_process(self.room_id,
                              "proceso de simulación cerrado", pid,
                              detail)

  async def _pump(self):
    """Bridge task: one tick every 1/PUMP_HZ s on a clock (not a sleep:
        a late tick neither accumulates delay nor sends a burst)."""
    period = 1.0 / ONLINE.PUMP_HZ
    next_tick = time.monotonic() + period
    while not self.closed:
      try:
        self.tick(time.monotonic())
      except Exception:  # pylint: disable=broad-exception-caught
        log.exception("room %s: bridge error", self.room_id)
        self._fail("error interno de la sala")
        return
      now = time.monotonic()
      next_tick = max(next_tick, now)     # late: back on the clock
      await asyncio.sleep(max(0.0, next_tick - now))
      next_tick += period

  # --------------------------------------------------------------- bridge
  def tick(self, now):
    """One turn of the bridge (it never blocks)."""
    self.counts["ticks"] += 1
    msgs, state = self.link.poll()
    if not self._link_healthy() or self.match is None:
      return
    self._send_start()
    if self._forward_events(msgs, now):
      return
    self._forward_state(state, now)
    # Controls go every turn: they are also the watchdog "heartbeat".
    self.link.send_input(self.inputs, self.input_seqs)
    self._housekeeping(now)

  def _housekeeping(self, now):
    """Pause check and the information each player sees in the F3 panel."""
    self._check_pause_end(now)
    if now - self.last_info >= ONLINE.ROOM_INFO_EVERY:
      self._update_rates(now)
      self.broadcast(self.room_info())

  def _send_start(self):
    """The start command leaves once the simulation is READY.

        The room always presents the goal (party and replay): the hold is
        the same for the two players, whatever effects each one has.
        """
    if self.start_pending and self.link.ready:
      self.start_pending = False
      self.link.send_command(protocol.CMD_START, match=self.match["id"],
                             characters=self.match["chars"],
                             presentation=True)

  def _link_healthy(self):
    if self.link.ready and not self.ready_logged:
      self.ready_logged = True
      self.server.log_process(self.room_id, "simulación lista (READY)",
                              self.link.sim_pid)
    error = self.link.check_health()
    if error:
      self._fail(error)
      return False
    return True

  def _forward_events(self, msgs, now):
    """Sends the match events. Returns True if the match ended."""
    for event in msgs:
      kind = event.get("type")
      if (kind in (protocol.EV_READY, protocol.EV_ACK)
              or event.get("match") != self.match["id"]):
        continue
      if kind == protocol.EV_MATCH_END:
        self._finish(wire.END_TIME, event["winner"], event["score"])
        return True
      self._forward_event(event, now)
    return False

  def _forward_event(self, event, now):
    if (event.get("type") == protocol.EV_PAUSED
            and event.get("reason") == protocol.PAUSE_REASON_REQUEST):
      self._pause_started(event.get("by"), now)
    self.counts["events"] += 1
    self.broadcast({"type": wire.EVENT, "e": event})

  def _forward_state(self, state, now):
    """Sends the newest state: one per simulation step, never a burst.

        The simulation publishes STATE_HZ states per second (one every
        STATE_EVERY_TICKS physics steps), so forwarding each new one gives
        the even cadence of the physics itself. The half period cap only
        matters if the source ever goes faster than STATE_HZ: it keeps the
        browser at two states per period instead of a flood.
        """
    if state is not None and state.get("match") == self.match["id"]:
      self.last_state = state
    latest = self.last_state
    if latest is None or latest["seq"] == self.sent_seq:
      return
    if now - self.sent_at < 0.5 / ONLINE.STATE_HZ:
      return
    self.sent_seq = latest["seq"]
    self.sent_at = now
    self.counts["states"] += 1
    self.broadcast_text(wire.encode(wire.compact_state(latest)),
                        replaceable=True)

  def _check_pause_end(self, now):
    pause = self.pause
    if (pause and pause["status"] == wire.PAUSE_ACTIVE
            and (all(pause["ready"]) or now >= pause["deadline"])):
      self._end_pause()

  def _update_rates(self, now):
    elapsed = max(now - self.last_info, ONLINE.STATE_SEND_SLACK)
    self.rates = {k: v / elapsed for k, v in self.counts.items()}
    self.counts.clear()
    self.last_info = now

  def side_of(self, sid):
    if self.match is None or sid not in self.match["sids"]:
      return None
    return self.match["sids"].index(sid)

  def broadcast(self, msg):
    self.broadcast_text(wire.encode(msg))

  def broadcast_text(self, text, replaceable=False):
    for sid in self.match["sids"] if self.match else ():
      session = self.server.sessions.get(sid)
      if session is not None:
        session.send_text(text, replaceable)

  # ---------------------------------------------------- info (panel, F3)
  def _ack_ms(self):
    confirmed = self.link.last_confirmed
    if not confirmed or confirmed.get("rtt") is None:
      return None
    return confirmed["rtt"] * config.MS_PER_SECOND

  def room_info(self):
    """What each player sees in the F3 panel: the room seen from the
        server."""
    return {"type": wire.ROOM_INFO, "room": self.room_id,
            "server_pid": os.getpid(), "sim_pid": self.link.sim_pid,
            "sim_alive": self.link.alive,
            "match": self.match["id"] if self.match else None,
            "states_per_s": self.rates.get("states", 0.0),
            "states_in": self.link.states_received,
            "ticks_per_s": self.rates.get("ticks", 0.0),
            "inputs_per_s": self.rates.get("inputs", 0.0),
            "ack_ms": self._ack_ms(),
            "pending_acks": len(self.link.pending),
            "hold": sorted(self.hold)}

  def panel_info(self, now):
    """Row of the server panel for this room (no player names)."""
    latest = self.last_state or {}
    info = {"pid": self.link.sim_pid, "alive": self.link.alive,
            "ready": self.link.ready,
            "match": self.match["id"] if self.match else None}
    info.update({k: latest.get(k) for k in ("phase", "clock", "score",
                                             "seq")})
    info.update({f"{k}_per_s": self.rates.get(k, 0.0)
                 for k in ("states", "events", "inputs")})
    info.update(ack_ms=self._ack_ms(),
                pending_commands=len(self.link.pending),
                pause=self._pause_reasons(), disconnected=len(self.away),
                uptime=now - self.created_at)
    return info

  def _pause_reasons(self):
    """Why the simulation is held (or the state of a pending pause)."""
    if self.hold:
      return sorted(self.hold)
    return [self.pause["status"]] if self.pause else []

  # -------------------------------------------------------------- players
  def set_input(self, side, p, seq=0):
    """Controls of a player; `seq` is the client's sequence number."""
    self.inputs[side] = p
    self.input_seqs[side] = seq
    self.counts["inputs"] += 1

  def request_pause(self, side):
    """A player asks for a pause: it starts after the next goal."""
    latest = self.last_state
    if (self.match is None or self.pause is not None or latest is None
            or latest["phase"] == protocol.PHASE_FINISHED):
      return
    self.link.send_command(protocol.CMD_PAUSE, after_goal=True, by=side,
                           reason=protocol.PAUSE_REASON_REQUEST)
    self.pause = {"status": wire.PAUSE_PENDING, "by": side,
                  "deadline": None, "ready": [False] * lobby.MAX_PLAYERS}
    self._send_pause_info()

  def pause_ready(self, side):
    pause = self.pause
    if (pause and pause["status"] == wire.PAUSE_ACTIVE
            and not pause["ready"][side]):
      pause["ready"][side] = True
      self._send_pause_info()

  def _pause_started(self, by, now):
    previous = self.pause or {}
    self.pause = {"status": wire.PAUSE_ACTIVE,
                  "by": by if by is not None else previous.get("by"),
                  "deadline": now + self.server.pause_max,
                  "ready": [False] * lobby.MAX_PLAYERS}
    self.hold.add(protocol.PAUSE_REASON_REQUEST)
    self._send_pause_info()

  def _end_pause(self):
    self.pause = None
    self._send_pause_info()
    self._release(protocol.PAUSE_REASON_REQUEST)

  def _release(self, reason):
    """Removes a pause reason; resumes when none is left."""
    if reason in self.hold:
      self.hold.discard(reason)
      if not self.hold and self.match is not None:
        self.link.send_command(protocol.CMD_RESUME)

  def pause_info(self):
    pause = self.pause
    if pause is None:
      return {"type": wire.PAUSE_INFO, "status": wire.PAUSE_NONE}
    left = (None if pause["deadline"] is None
            else max(0.0, pause["deadline"] - time.monotonic()))
    by = pause["by"]
    return {"type": wire.PAUSE_INFO, "status": pause["status"],
            "by": by,
            "by_name": self.match["names"][by] if by is not None else None,
            "left": left, "ready": list(pause["ready"])}

  def _send_pause_info(self):
    self.broadcast(self.pause_info())

  def opponent_msg(self, side):
    """How the connection of the rival of `side` is doing."""
    other = 1 - side
    deadline = self.away.get(other)
    return {"type": wire.OPPONENT, "connected": deadline is None,
            "name": self.match["names"][other],
            "left": (None if deadline is None
                     else max(0.0, deadline - time.monotonic()))}

  def player_away(self, side, deadline):
    """A player dropped: the match pauses until it comes back."""
    if self.match is None:
      return
    self.away[side] = deadline
    if protocol.PAUSE_REASON_DISCONNECT not in self.hold:
      self.hold.add(protocol.PAUSE_REASON_DISCONNECT)
      self.link.send_command(protocol.CMD_PAUSE,
                             reason=protocol.PAUSE_REASON_DISCONNECT)
    self._send_opponent_status()
    log.info("room %s: %s lost the connection", self.room_id,
             self.match["names"][side])

  def player_back(self, side, session):
    """The player came back: it gets the match screen again."""
    if self.match is None:
      return
    self.away.pop(side, None)
    session.send(self.match["start_msgs"][side])
    session.send(self.pause_info())
    if self.last_state is not None:
      session.send_text(wire.encode(wire.compact_state(self.last_state)),
                        replaceable=True)
    self._send_opponent_status()
    if not self.away:
      self._release(protocol.PAUSE_REASON_DISCONNECT)
    log.info("room %s: %s came back", self.room_id,
             self.match["names"][side])

  def _send_opponent_status(self):
    for side, sid in enumerate(self.match["sids"]):
      session = self.server.sessions.get(sid)
      if session is not None:
        session.send(self.opponent_msg(side))

  def forfeit(self, side):
    """Forfeit (button or 30 s away): whoever stayed wins."""
    if self.match is None:
      return
    self.link.send_command(protocol.CMD_END)
    log.info("room %s: %s left match #%s", self.room_id,
             self.match["names"][side], self.match["id"])
    self._finish(wire.END_FORFEIT, 1 - side, self._score(), by=side)

  def _score(self):
    if self.last_state:
      return list(self.last_state["score"])
    return list(NO_SCORE)

  def _finish(self, reason, winner, score, by=None):
    match = self.match
    self.broadcast({
        "type": wire.MATCH_OVER, "match": match["id"], "score": score,
        "winner": winner, "reason": reason, "by": by,
        "by_name": match["names"][by] if by is not None else None})
    self._reset_match()
    self.server.deliver(self.server.lobby.finish_match(self.room_id))

  def _fail(self, error):
    log.error("room %s: the simulation failed: %s", self.room_id, error)
    self.server.log_process(self.room_id, "falló la simulación",
                            self.link.sim_pid, error)
    if self.match is not None:
      self._finish(wire.END_ERROR, None, self._score())
    # The next match uses a new bridge and a new process.
    self.server.drop_runner(self.room_id, self)
