"""Prediction of the own player in the online mode.

The server keeps deciding everything (it is authoritative), but waiting a
whole round trip before moving the own player feels like walking in syrup.
So the client moves ITS OWN player here, with the same fixed step and the
same physics the simulation uses (fdc/sim/physics.py):
`control_player` + `integrate_player` + the collision with the rival.

Every state from the server carries "ack": the last controls sequence
number the simulation applied for each player. With it, and a short history
of predicted positions, the client knows where it was when the server
produced that state (one-way latency back) and measures the error there:

  * small error: the prediction is nudged towards the server (soft fix);
  * big error (goal, push, collision): the server wins, the prediction
    snaps to its player.

The ball and the rival are NOT predicted: they are drawn as the server
says (the screen interpolates them). Nothing is predicted while the match
is paused, in the goal hold or in the replay: there the screen keeps
drawing the server state.

It imports neither pygame nor network libraries: the tests and the
measurement scripts use it as is.
"""
import collections
import math
import time

from fdc import config
from fdc import protocol
from fdc.sim import physics

ONLINE = config.Online
DT = config.PHYSICS_DT          # s: the same fixed step as the server
STEPS_PER_FRAME = config.MAX_CATCHUP_STEPS
# Fields of a controls snapshot (see wire.clean_input).
LEFT, RIGHT, JUMPS, KICKS = 0, 1, 2, 3


class Prediction:
    """Local copy of the own player, corrected with the server states."""

    def __init__(self, side):
        self.side = side
        self.other = 1 - side
        self.enabled = ONLINE.PREDICT_ENABLED
        self.ready = self.active = False    # in sync / in effective play
        self.unsupported = False    # the server does not send "ack"
        self.clock = time.monotonic
        self.player = physics.Player(side)
        self.rival = physics.Player(self.other)
        self.goals = (physics.Goal(0), physics.Goal(1))
        self.rival_state = None
        self._reset_counters()
        self.history = collections.deque(
            maxlen=int(ONLINE.PREDICT_HISTORY * config.PHYSICS_HZ))

    def _reset_counters(self):
        """Presses, controls and error counters."""
        self.jump = protocol.PressCounter()
        self.kick = protocol.PressCounter()
        self.snapshot = [False, False, 0, 0]
        self.seq = 0                # last controls snapshot sent
        self.ack = -1               # last one the server applied
        self.acc = 0.0              # s owed to the fixed step
        self.rewind = ONLINE.PREDICT_REWIND
        self.error = 0.0            # px of the last measured error
        self.snaps = 0              # big errors: jumped to the server
        self.fixes = 0              # small errors: nudged
        self.stale = 0              # states older than the one before

    # ------------------------------------------------------------- controls
    def push_input(self, snapshot):
        """New controls: they reach the prediction at once. Returns its seq."""
        self.snapshot = list(snapshot)
        self.seq += 1
        return self.seq

    def set_latency(self, rtt):
        """How far back a state sits in our timeline: the round trip.

        The state was produced one trip ago and it carries the controls we
        had sent another trip before that, so our position "at that moment"
        is the one we had one ROUND TRIP ago.
        """
        if rtt is None:
            return
        self.rewind = min(ONLINE.PREDICT_MAX_REWIND, max(0.0, rtt))

    # ---------------------------------------------------------------- steps
    def play(self):
        """Effective play started: from here the prediction moves."""
        self.active = True

    def step(self, dt):
        """Advances the prediction with the server's fixed step."""
        if not self.enabled or not self.ready or not self.active:
            return
        self.acc += min(dt, ONLINE.PREDICT_MAX_FRAME)
        steps = 0
        while self.acc >= DT and steps < STEPS_PER_FRAME:
            self._one_step()
            self.acc -= DT
            steps += 1
        if steps >= STEPS_PER_FRAME:    # a long stall is not paid later
            self.acc = 0.0

    def _one_step(self):
        """One physics step of the own player, exactly like the server."""
        player, snapshot = self.player, self.snapshot
        jumps = self.jump.update(snapshot[JUMPS])
        kicks = self.kick.update(snapshot[KICKS])
        move = (1 if snapshot[RIGHT] else 0) - (1 if snapshot[LEFT] else 0)
        physics.control_player(player, DT, move, jumps > 0, kicks > 0, [])
        player.update_size(DT)
        physics.integrate_player(player, DT, self.goals)
        self._collide_rival()
        self.history.append((self.clock(), player.x, player.y, self.seq))

    def _collide_rival(self):
        """The rival is a solid body, at the position the server last sent."""
        if self.rival_state is None:
            return
        self._load(self.rival, self.rival_state, self.other)
        physics.land_on_heads((self.player, self.rival))
        physics.collide_players(self.player, self.rival)

    # -------------------------------------------------------- reconciliation
    def reconcile(self, state, now):
        """Corrects the prediction with a state from the server."""
        mine = self._acked(state)
        if mine is None:
            return
        own = state["players"][self.side]
        self.ack = mine
        self.rival_state = state["players"][self.other]
        self._load_goals(state.get("goals"))
        if not self.ready:
            self.snap(own, count=False)
            return
        self._copy_modifiers(own)
        self._fix(own, now)

    def _acked(self, state):
        """Sequence number of MY controls applied in that state (or None)."""
        ack = state.get("ack")
        if not self._valid_ack(ack):
            self.unsupported = True
            self.enabled = False
            return None
        if ack[self.side] < self.ack:   # repeated or reordered state
            self.stale += 1
            return None
        return ack[self.side]

    def _valid_ack(self, ack):
        """True if the state tells which controls were applied."""
        if not isinstance(ack, list) or len(ack) < 2:
            return False
        return all(isinstance(n, int) for n in ack[:2])

    def _fix(self, own, now):
        """Soft fix for a small error; snap to the server for a big one."""
        anchor = self._anchor(now)
        if anchor is None:
            self.snap(own)
            return
        dx, dy = own["x"] - anchor[1], own["y"] - anchor[2]
        self.error = math.hypot(dx, dy)
        lost = self.seq - self.ack > ONLINE.PREDICT_MAX_PENDING
        if self.error > ONLINE.PREDICT_SOFT_PX or lost:
            self.snap(own)
            return
        self._shift(dx * ONLINE.PREDICT_GAIN, dy * ONLINE.PREDICT_GAIN)
        self.fixes += 1

    def _anchor(self, now):
        """Predicted position when the server produced this state."""
        target = now - self.rewind
        for entry in reversed(self.history):
            if entry[0] <= target:
                return entry
        if self.history:
            return self.history[0]
        # Right after a snap there is no history yet: the current position
        # (the server's) is the best reference we have.
        return (now, self.player.x, self.player.y, self.seq)

    def _shift(self, dx, dy):
        """Moves the prediction (and its history) a bit towards the server."""
        if not dx and not dy:
            return
        self.player.x += dx
        self.player.y += dy
        shifted = collections.deque(maxlen=self.history.maxlen)
        for stamp, x, y, seq in self.history:
            shifted.append((stamp, x + dx, y + dy, seq))
        self.history = shifted

    def snap(self, own, count=True):
        """The server wins: the prediction starts again from its player."""
        self._load(self.player, own, self.side)
        self.history.clear()
        self.acc = 0.0
        self._baseline_presses()
        self.ready = True
        if count:
            self.snaps += 1

    def _baseline_presses(self):
        """The counters of the snapshot are the starting point: only the
        presses that come later are new."""
        self.jump = protocol.PressCounter()
        self.kick = protocol.PressCounter()
        self.jump.update(self.snapshot[JUMPS])
        self.kick.update(self.snapshot[KICKS])

    # ---------------------------------------------------------------- pauses
    def hold(self, state):
        """Paused, goal or replay: no prediction, just follow the server."""
        self.active = False
        if state is None:
            self.ready = False
            return
        self.rival_state = state["players"][self.other]
        self._load_goals(state.get("goals"))
        self.snap(state["players"][self.side], count=False)

    # ------------------------------------------------------------------ view
    def apply(self, view):
        """The view to draw: the server's, with the own player predicted."""
        if not self.enabled or not self.ready or view is None:
            return view
        players = list(view["players"])
        own = dict(players[self.side])
        player = self.player
        own.update(x=player.x, y=player.y, vx=player.vx, vy=player.vy,
                   facing=player.facing, ground=player.on_ground,
                   scale=player.scale, kick=player.kick_progress())
        players[self.side] = own
        out = dict(view)
        out["players"] = players
        return out

    def debug_text(self):
        """One line for the F3 panel."""
        if not self.enabled:
            return "no" if not self.unsupported else "no (servidor viejo)"
        if not self.ready:
            return "esperando"
        return (f"{self.error:.0f} px  {self.fixes} suaves / "
                f"{self.snaps} saltos / {self.stale} viejos")

    # --------------------------------------------------------------- helpers
    def _load_goals(self, heights):
        """Crossbar heights (a power raises or lowers them)."""
        if not heights or len(heights) < 2:
            return
        for goal, height in zip(self.goals, heights):
            goal.height = goal.target_height = float(height)

    def _copy_modifiers(self, own):
        """Power modifiers: size, speed, jump, frozen, no kick, knockback."""
        player = self.player
        player.scale = player.target_scale = float(own.get("scale", 1.0))
        player.speed_mult = float(own.get("speed", 1.0))
        player.jump_mult = float(own.get("jump", 1.0))
        player.frozen = bool(own.get("frozen"))
        player.no_kick = bool(own.get("no_kick"))
        player.knockback = 1.0 if own.get("knock") else 0.0

    def _load(self, target, source, idx):
        """Copies the serializable player of a state into a physics player."""
        target.idx = idx
        target.x = float(source["x"])
        target.y = float(source["y"])
        target.prev_y = target.y
        self._load_motion(target, source)
        self._load_timers(target, source)

    @staticmethod
    def _load_motion(target, source):
        """Speed, facing, size, power modifiers and state of the body."""
        target.vx = float(source.get("vx", 0.0))
        target.vy = float(source.get("vy", 0.0))
        target.facing = int(source.get("facing", 1)) or 1
        target.on_ground = bool(source.get("ground"))
        target.scale = target.target_scale = float(source.get("scale", 1.0))
        target.speed_mult = float(source.get("speed", 1.0))
        target.jump_mult = float(source.get("jump", 1.0))
        target.frozen = bool(source.get("frozen"))
        target.no_kick = bool(source.get("no_kick"))
        target.knockback = 1.0 if source.get("knock") else 0.0
        target.on_head = source.get("on_head")
        target.celebrating = bool(source.get("celebrate"))

    def _load_timers(self, target, source):
        """Kick and press timers: only the kick progress comes in the state."""
        target.kick_t = self._kick_time(source.get("kick"))
        target.kick_cooldown = 0.0
        target.jump_buffer = target.kick_buffer = 0.0
        target.coyote = 0.0
        target.ball_ignore = 0.0
        target.kick_hit = False

    @staticmethod
    def _kick_time(progress):
        """Seconds since the kick started (-1: not kicking)."""
        if progress is None or progress < 0:
            return -1.0
        return float(progress) * config.PlayerSpec.KICK_DURATION
