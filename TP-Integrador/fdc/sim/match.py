"""Authoritative state of one match.

This class knows nothing about processes or queues: it receives controls,
advances with a fixed step and returns events. So it can be tested directly
and runs the same in the local process and in the online room processes.

Phases:  countdown -> playing -> goal -> countdown -> playing ... -> finished
Pausing is a separate flag: it freezes any phase.
The clock only runs in "playing" and when not paused.
The goal phase is frozen: the interface shows the party and then the replay
of the goal on a still match, and play comes back from the centre.
"""
import random

from fdc import config
from fdc import protocol
from fdc.sim import physics
from fdc.sim import powers

# Priority to resolve simultaneous contacts (see README):
# kick > head > body; then the higher impact speed; exact tie -> the
# previous last touch is kept.
TOUCH_PRIORITY = {"kick": 3, "head": 2, "body": 1}
# s: shortest time between two sounds of the same kind (bounce series).
SOUND_COOLDOWN = 0.07
# s without collisions between the ball and whoever just kicked it.
KICK_BALL_IGNORE = 0.12
# The random seed is a 31-bit integer (fits on any platform).
SEED_BITS = 31


def _goal_hold(presentation):
    """s the goal stays frozen: the party and, with a replay, the clip."""
    if presentation:
        return config.MatchRules.GOAL_HOLD
    return config.MatchRules.GOAL_CELEBRATION


class Match:
    """Players, ball, goals, powers, score, clock and phases of a match."""

    def __init__(self, match_id, seed=None, characters=("?", "?"),
                 duration=None, golden_goal=False, presentation=True):
        self.id = match_id
        # Golden goal: if time ends in a draw, the next goal wins.
        self.golden_goal, self.golden = golden_goal, False
        self._set_presentation(presentation)
        self._set_seed(seed)
        # Only kept for the log: physics uses the same base abilities.
        self.characters = tuple(characters)
        self._create_entities()
        self.clock = (float(duration) if duration
                      else config.MatchRules.DURATION)
        self._reset_flow()

    def _set_presentation(self, presentation):
        """If the goal is presented (party and replay) and for how long."""
        self.presentation = bool(presentation)
        self.goal_hold = _goal_hold(presentation)

    def _set_seed(self, seed):
        """Random seed of the match and its generator."""
        self.seed = (seed if seed is not None
                     else random.getrandbits(SEED_BITS))
        self.rng = random.Random(self.seed)

    def _create_entities(self):
        self.players = [physics.Player(0), physics.Player(1)]
        self.ball = physics.Ball()
        self.goals = [physics.Goal(0), physics.Goal(1)]
        self.powers = powers.PowerManager(self.rng)
        self.score = [0, 0]
        self.tick = 0

    def _reset_flow(self):
        """Phase, pause and per-step input state at the start."""
        self.phase = protocol.PHASE_COUNTDOWN
        self.phase_left = config.MatchRules.KICKOFF_COUNTDOWN
        self.paused, self.pause_reason = False, None
        # Online: side that asked for a pause (it starts after the next
        # goal) and side that asked for the active pause.
        self.pause_pending = self.pause_by = None
        self.last_touch = self.scorer = self.winner = None
        # The replay of a goal still has to be announced to the clients.
        self.goal_latched = self.replay_pending = False
        self.move = [0, 0]
        self.pending_jump = [False, False]
        self.pending_kick = [False, False]
        self._sound_cd, self._events = {}, []

    # ----------------------------------------------------------------- input
    def set_input(self, idx, left, right, new_jumps, new_kicks):
        """Stores the controls of player `idx` for the next step."""
        self.move[idx] = (1 if right else 0) - (1 if left else 0)
        # Presses only count in effective play; those arriving during
        # countdowns or pauses are dropped on purpose.
        if self.phase == protocol.PHASE_PLAYING and not self.paused:
            if new_jumps > 0:
                self.pending_jump[idx] = True
            if new_kicks > 0:
                self.pending_kick[idx] = True

    def pause(self, reason=protocol.PAUSE_REASON_USER):
        """Pauses the match (not after it ended). Returns True if paused."""
        if self.phase == protocol.PHASE_FINISHED:
            return False
        self.paused = True
        self.pause_reason = reason
        self.move = [0, 0]
        self.pending_jump = [False, False]
        self.pending_kick = [False, False]
        return True

    def request_pause_after_goal(self, by):
        """Online: a requested pause does not cut a play; it starts when,
        after the next goal (for or against), play goes back to the
        centre."""
        if self.phase == protocol.PHASE_FINISHED:
            return False
        if self.pause_pending is None:
            self.pause_pending = by
        return True

    def resume(self):
        """Ends the pause with a short countdown. True if it was paused."""
        if not self.paused:
            return False
        self.paused = False
        self.pause_reason = None
        self.pause_by = None
        if self.phase == protocol.PHASE_PLAYING:
            self.phase = protocol.PHASE_COUNTDOWN
            self.phase_left = config.MatchRules.RESUME_COUNTDOWN
        return True

    # ------------------------------------------------------------------ step
    def step(self, dt):
        """Advances one fixed step and returns the events (type, data)."""
        self._events = []
        if self.paused or self.phase == protocol.PHASE_FINISHED:
            return self._events
        self.tick += 1
        for kind in list(self._sound_cd):
            self._sound_cd[kind] -= dt
        if self.phase == protocol.PHASE_COUNTDOWN:
            self._countdown(dt)
        elif self.phase == protocol.PHASE_GOAL:
            self._celebration(dt)
        else:
            self._play(dt)
        return self._events

    def _countdown(self, dt):
        self.phase_left -= dt
        if self.phase_left <= 0:
            self.phase = protocol.PHASE_PLAYING
            self.phase_left = 0.0
            self._events.append((protocol.EV_KICKOFF, {}))

    def _celebration(self, dt):
        """Frozen goal: the interface shows the party and then the replay."""
        self.phase_left -= dt
        if self.phase_left > 0:
            self._announce_replay()
            return
        self._after_goal_hold()

    def _announce_replay(self):
        """Tells the clients that the replay starts (once, when due)."""
        if not self.replay_pending:
            return
        if self.phase_left > config.MatchRules.GOAL_REPLAY:
            return
        self.replay_pending = False
        self._events.append((protocol.EV_REPLAY, {
            "seconds": config.MatchRules.GOAL_REPLAY,
            "score": list(self.score)}))

    def _after_goal_hold(self):
        """End of the frozen goal: play comes back from the centre."""
        self.replay_pending = False
        if self.golden:
            self._finish()          # golden goal: ends after the celebration
            return
        self._reset_after_goal()
        if self.pause_pending is not None:
            self._start_requested_pause()

    def skip_goal(self):
        """The interface skipped the party and the replay: straight to the
        kickoff (or to the end, on a golden goal). Returns (ok, events)."""
        if self.phase != protocol.PHASE_GOAL:
            return False, []
        self._events = []
        self.phase_left = 0.0
        self._after_goal_hold()
        return True, self._events

    def _start_requested_pause(self):
        by, self.pause_pending = self.pause_pending, None
        self.pause(protocol.PAUSE_REASON_REQUEST)
        self.pause_by = by
        self._events.append((protocol.EV_PAUSED,
                             {"reason": protocol.PAUSE_REASON_REQUEST,
                              "by": by}))

    def _play(self, dt):
        """Effective play: powers, physics, pickups, goals and the clock."""
        self.powers.update(dt, self, self._events)
        self.powers.apply_modifiers(self)
        prev_x = self.ball.x
        self._physics(dt, controls=True)
        self.powers.check_pickup(self, self._events)
        self._check_goals(prev_x)
        if self.phase == protocol.PHASE_PLAYING and not self.golden:
            self.clock = max(0.0, self.clock - dt)
            if self.clock <= 0:
                if self.golden_goal and self.score[0] == self.score[1]:
                    self._start_golden_goal()
                else:
                    self._finish()

    def _start_golden_goal(self):
        """Draw at the end: kickoff from the centre, the first goal wins."""
        self._reset_after_goal()
        self.golden = True
        self.phase_left = config.MatchRules.GOLDEN_GOAL_COUNTDOWN
        self._events.append((protocol.EV_GOLDEN_GOAL,
                             {"score": list(self.score)}))

    def _physics(self, dt, controls):
        self._move_players(dt, controls)
        for goal in self.goals:
            goal.update(dt)
        self.ball.update_size(dt)
        contacts, touches = [], []
        self._kicks(contacts)
        physics.step_ball(self.ball, self.players, self.goals, dt, contacts,
                          touches)
        self._resolve_last_touch(contacts)
        self._burn(contacts)
        self._sound_events(contacts, touches)

    def _burn(self, contacts):
        """The fire power of the ball burns the player who touches it."""
        if not contacts:
            return
        user = self.last_touch
        if user is None:
            user = contacts[0][0]
        self.powers.check_burn(self, user, self._events)

    def _move_players(self, dt, controls):
        self._control_players(dt, controls)
        for player in self.players:
            physics.integrate_player(player, dt, self.goals)
        physics.land_on_heads(self.players)
        physics.collide_players(self.players[0], self.players[1])

    def _control_players(self, dt, controls):
        """Applies the controls (or none) and reports kick attempts."""
        actions = []
        for player in self.players:
            i = player.idx
            intent = ((self.move[i], self.pending_jump[i],
                       self.pending_kick[i]) if controls else (0, False, False))
            physics.control_player(player, dt, *intent, actions)
            self.pending_jump[i] = self.pending_kick[i] = False
            player.update_size(dt)
        for kind, idx in actions:
            self._events.append((protocol.EV_KICK if kind == "kick"
                                 else protocol.EV_KICK_BLOCKED,
                                 {"player": idx}))

    def _kicks(self, contacts):
        """Kicks that hit the ball this step (both kicking = average)."""
        ball = self.ball
        kickers = [p for p in self.players if p.kick_active()
                   and not p.kick_hit and physics.ball_hits_foot(ball, p)]
        if not kickers:
            return
        velocities = [physics.apply_kick(ball, p) for p in kickers]
        ball.vx = sum(v[0] for v in velocities) / len(velocities)
        ball.vy = sum(v[1] for v in velocities) / len(velocities)
        ball.clamp_speed()
        for player in kickers:
            self._register_kick(player, contacts)

    def _register_kick(self, player, contacts):
        power = config.PlayerSpec.KICK_POWER
        player.kick_hit = True
        player.ball_ignore = KICK_BALL_IGNORE
        contacts.append((player.idx, "kick", power))
        self._events.append((protocol.EV_TOUCH, {
            "kind": "kick", "player": player.idx, "x": self.ball.x,
            "y": self.ball.y, "speed": power}))

    def _resolve_last_touch(self, contacts):
        if not contacts:
            return
        best = {}
        for idx, kind, impact in contacts:
            key = (TOUCH_PRIORITY[kind], impact)
            if idx not in best or key > best[idx]:
                best[idx] = key
        if len(best) == 1:
            self.last_touch = next(iter(best))
        elif best[0] != best[1]:
            self.last_touch = 0 if best[0] > best[1] else 1
        # Exact tie: the previous last touch is kept.

    def _sound_events(self, contacts, touches):
        """Touch events (sounds), at most one per kind and cooldown."""
        seen = set()
        for idx, kind, impact in contacts:
            if kind != "kick":
                self._touch_sound(kind, idx, impact, seen)
        for kind, impact in touches:
            self._touch_sound(kind, None, impact, seen)

    def _touch_sound(self, kind, player, impact, seen):
        if (impact < config.BallSpec.SOUND_MIN_IMPACT or kind in seen
                or self._sound_cd.get(kind, 0) > 0):
            return
        seen.add(kind)
        self._sound_cd[kind] = SOUND_COOLDOWN
        self._events.append((protocol.EV_TOUCH, {
            "kind": kind, "player": player, "x": self.ball.x,
            "y": self.ball.y, "speed": impact}))

    # ----------------------------------------------------------------- goals
    def _check_goals(self, prev_x):
        if self.goal_latched or self.phase != protocol.PHASE_PLAYING:
            return
        ball = self.ball
        for goal in self.goals:
            moving_in = ball.x < prev_x if goal.side == 0 else ball.x > prev_x
            if goal.ball_inside(ball) and moving_in:
                self._score_goal(goal)
                return

    def _score_goal(self, goal):
        scorer = 1 - goal.side
        self.goal_latched = True   # the same entry gives no more goals
        self.score[scorer] += 1
        self.scorer = scorer
        self.players[scorer].celebrating = True
        own_goal = self.last_touch == goal.side
        self.phase = protocol.PHASE_GOAL
        self.phase_left = self.goal_hold
        self.replay_pending = self.presentation   # announced when due
        self.powers.clear()
        self.powers.apply_modifiers(self)
        event = self._goal_event(goal, scorer, own_goal)
        self._events.append((protocol.EV_GOAL, event))

    def _goal_event(self, goal, scorer, own_goal):
        """Payload of the goal: who scored and where the ball went in."""
        return {"scorer": scorer, "side": goal.side, "score": list(self.score),
                "own_goal": own_goal, "x": self.ball.x, "y": self.ball.y}

    def _reset_after_goal(self):
        for player in self.players:
            player.reset()
        self.ball.reset()
        for goal in self.goals:
            goal.reset()
        self.powers.clear()
        self.powers.apply_modifiers(self)
        self.last_touch = None
        self.scorer = None
        self.goal_latched = False
        self.phase = protocol.PHASE_COUNTDOWN
        self.phase_left = config.MatchRules.GOAL_COUNTDOWN

    def _finish(self):
        self.phase = protocol.PHASE_FINISHED
        self.powers.clear()
        home, away = self.score
        self.winner = None if home == away else (0 if home > away else 1)
        if self.winner is not None:
            self.players[self.winner].celebrating = True
        self._events.append((protocol.EV_MATCH_END,
                             {"score": list(self.score),
                              "winner": self.winner}))

    # ------------------------------------------------------------- test mode
    def debug_power(self, power, mode):
        """Test mode: 'spawn' creates the pickup; 'p0'/'p1' activate it
        directly. Returns (ok, detail, events); details are shown."""
        events = []
        if power not in config.POWERS_BY_ID:
            return False, f"poder desconocido: {power}", events
        if self.phase == protocol.PHASE_FINISHED:
            return False, "el partido terminó", events
        if mode == "spawn":
            self.powers.place_pickup(power, powers.default_test_spawn(self),
                                     events)
        else:
            receiver = 0 if mode == "p0" else 1
            self.powers.activate(power, receiver, self, self.ball.x,
                                 self.ball.y, events)
        return True, "", events

    # ----------------------------------------------------------------- state
    def snapshot(self, seq):
        """Serializable state of the match (what the screens draw)."""
        state = {"type": protocol.MSG_STATE, "match": self.id, "seq": seq,
                 "tick": self.tick}
        state.update(self._flow_snapshot())
        state.update(players=[_player_snapshot(p) for p in self.players],
                     ball=_ball_snapshot(self.ball),
                     goals=[g.height for g in self.goals])
        state.update(self.powers.snapshot())
        return state

    def _flow_snapshot(self):
        """Phase, pause, clock and score part of the state."""
        return {
            "phase": self.phase, "paused": self.paused,
            "pause_reason": self.pause_reason,
            "pause_pending": self.pause_pending, "pause_by": self.pause_by,
            "phase_left": self.phase_left, "clock": self.clock,
            "score": list(self.score), "golden": self.golden,
            "last_touch": self.last_touch, "scorer": self.scorer,
            "winner": self.winner}


def _ball_snapshot(ball):
    return {"x": ball.x, "y": ball.y, "r": ball.radius, "angle": ball.angle,
            "vx": ball.vx, "vy": ball.vy}


def _player_snapshot(player):
    return {
        "x": player.x, "y": player.y, "vx": player.vx, "vy": player.vy,
        "facing": player.facing, "ground": player.on_ground,
        "kick": player.kick_progress(), "scale": player.scale,
        "frozen": player.frozen, "no_kick": player.no_kick,
        "burned": player.burned, "burned_left": player.burned_left,
        "stride": player.stride, "knock": player.knockback > 0,
        "celebrate": player.celebrating, "on_head": player.on_head,
        # Power modifiers: the client needs them to predict with the same
        # physics (see fdc/online/prediction.py).
        "speed": player.speed_mult, "jump": player.jump_mult,
    }
