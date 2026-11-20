"""Replay and VAR of the goals (F5).

The chain keeps the last `config.Gpu.REPLAY_SECONDS` seconds of match states,
so a goal can be shown again and a close one can be reviewed by the VAR.
Everything here is plain Python (no pygame, no numpy): the rules are tested
without a window.

Three pieces:
  - `StateHistory`: the ring of saved states (one every `REPLAY_STEP` s).
  - `ReplayPlayer`: plays those states again in `REPLAY_DURATION` s,
    interpolating the positions so the movement does not look chopped.
  - `VarPlayer`: freezes the last frame, says "reviewing" and then confirms.
"""
import copy

from fdc import config

G = config.Gpu
ARENA = config.Arena
REPLAY_KIND = "replay"      # the chain draws this as an old television
VAR_KIND = "var"            # the chain draws this as a review
REVIEW = "review"           # VAR stage: the referee is looking at the play
CONFIRMED = "confirmed"     # VAR stage: the goal stands
MIN_FRAMES = 2              # states needed to interpolate the positions
MIN_DURATION = 0.001        # s: a replay never lasts zero
STEP_TOLERANCE = 1e-9       # s: the step is never exact in float sums
FULL = 1.0                  # end of the progress
SIDES = (0, 1)              # left and right goal
POSITION_KEYS = ("x", "y")  # fields interpolated between two states
NO_GAP = 0.0                # px: the ball touched the bar but went in


class StateHistory:
  """Ring with the last states of the match, one every `step` seconds."""

  def __init__(self, seconds=G.REPLAY_SECONDS, step=G.REPLAY_STEP):
    self.seconds = seconds
    self.step = step
    self.saved = []         # [(t, state)] from the oldest to the newest
    self.last_t = None      # time of the last saved state

  def feed(self, state, now):
    """Saves a copy of `state` if `step` seconds passed since the last."""
    if not state:
      return
    if self.last_t is not None and now - self.last_t < self._step_limit():
      return
    self.last_t = now
    self.saved.append((now, copy.deepcopy(state)))
    self._prune(now)

  def _step_limit(self):
    """The step, less the rounding error of the sums of time."""
    return self.step - STEP_TOLERANCE

  def _prune(self, now):
    """Drops the states that fell out of the window."""
    limit = now - self.seconds
    self.saved = [item for item in self.saved if item[0] >= limit]

  def clear(self):
    """New match: no history at all."""
    self.saved = []
    self.last_t = None

  def frames(self, duration=G.REPLAY_DURATION):
    """States of the last `duration` seconds (newest last)."""
    if not self.saved:
      return []
    limit = self.saved[-1][0] - duration
    picked = [item for item in self.saved if item[0] >= limit]
    return picked or self.saved[-1:]

  def window(self, center, back=G.REPLAY_DURATION,
             forward=G.REPLAY_AFTER_GOAL):
    """States from `back` s before `center` to `forward` s after it.

        It is the window of a goal: the replay has to show the goal and a
        little of the net, so the last state is built at exactly
        `center + forward` (the saved ones are a step apart).
        """
    if not self.saved:
      return []
    picked = _window_states(self.saved, center - back, center + forward)
    return picked or self.frames(back)

  def last_state(self):
    """Newest saved state ({} if there is none)."""
    return self.saved[-1][1] if self.saved else {}

  def is_close(self, side, ball=None, frames=G.VAR_FRAMES):
    """True if the goal was doubtful: the ball passed just under the bar.

        The last `frames` states are checked (or the ball of the event, which
        is the one that went in): close means the ball crossed grazing the
        crossbar (less than the bar plus the ball under it). The distance to
        the goal line is not a clue here: at `EV_GOAL` the ball is always on
        it, so that clause of the spec would flag every goal.
        """
    if side not in SIDES:
      return False
    recent = self.saved[-frames:]
    if ball is not None:
      state = recent[-1][1] if recent else {}
      return near_bar(state, side, ball[0], ball[1])
    return any(near_bar(state, side, *ball_xy(state))
               for _, state in recent)


def near_bar(state, side, x, y):
  """True if the ball went in grazing the crossbar.

    `y` grows downwards: the gap under the bar is `bar_y - y`, and the goal
    is close when that gap is smaller than the bar plus the ball (the ball
    touched the bar and went in). The goal line is not a clue: at `EV_GOAL`
    the ball is always on it.
    """
  del x  # the goal line is not a clue (the ball is always on it)
  height = goal_height(state, side) if side in SIDES else None
  if height is None:
    return False
  radius = float((state.get("ball") or {}).get("r") or 0.0)
  gap = y - (ARENA.FLOOR_Y - height)      # px under the bar (0 = touching)
  return NO_GAP <= gap <= ARENA.BAR_THICKNESS + radius


def goal_height(state, side):
  """Height of the crossbar of that goal, or None."""
  goals = state.get("goals") or ()
  if side < 0 or side >= len(goals):
    return None
  return float(goals[side])


def ball_xy(state):
  """(x, y) of the ball of a state (0, 0 if there is none)."""
  ball = state.get("ball") or {}
  return float(ball.get("x") or 0.0), float(ball.get("y") or 0.0)


class ReplayPlayer:
  """Plays the saved states again, interpolating the positions."""

  kind = REPLAY_KIND
  from_goal = False      # the screen closes it when the window is over

  def __init__(self, frames, now, duration=G.REPLAY_DURATION):
    self.frames = list(frames)
    self.start = now
    self.duration = max(duration, MIN_DURATION)
    self.span = (self.frames[-1][0] - self.frames[0][0]
                 if len(self.frames) > 1 else 0.0)

  def progress(self, now):
    """0 at the start, 1 at the end (clamped)."""
    return min(FULL, max(0.0, (now - self.start) / self.duration))

  def finished(self, now):
    """True when the replay is over."""
    return self.progress(now) >= FULL

  def stage(self, now):
    """A plain replay has no stage (the VAR has two)."""
    del now
    return None

  def state_at(self, now):
    """State of the replay at `now` (positions interpolated)."""
    return self.state_at_progress(self.progress(now))

  def state_at_progress(self, progress):
    """State at `progress` (0..1) of the clip (positions interpolated).

        The screen drives it with the clock of the simulation, so every
        client shows the same frame of the replay at the same moment.
        """
    if len(self.frames) < MIN_FRAMES:
      return self.frames[-1][1] if self.frames else {}
    mix = min(FULL, max(0.0, progress))
    target = self.frames[0][0] + mix * self.span
    older, newer = self._pair(target)
    gap = newer[0] - older[0]
    part = 0.0 if gap <= 0 else min(FULL, (target - older[0]) / gap)
    return _mix(older[1], newer[1], part)

  def _pair(self, target):
    """The two saved states around `target`."""
    for index in range(len(self.frames) - 1):
      if self.frames[index + 1][0] >= target:
        return self.frames[index], self.frames[index + 1]
    return self.frames[-2], self.frames[-1]


class VarPlayer:
  """Freeze frame of the goal: "reviewing" and then the confirmation."""

  kind = VAR_KIND
  from_goal = False      # the screen closes it when the window is over

  def __init__(self, state, now, review=G.VAR_DURATION,
               confirm=G.VAR_CONFIRM):
    self.state = copy.deepcopy(state) if state else {}
    self.start = now
    self.review = review
    self.confirm = confirm
    self.duration = review + confirm   # s: the two signs together

  def stage(self, now):
    """REVIEW while the referee looks, CONFIRMED after that."""
    return REVIEW if now - self.start < self.review else CONFIRMED

  def finished(self, now):
    """True when the two signs have been shown."""
    return now - self.start >= self.review + self.confirm

  def state_at(self, now):
    """The frozen state (the match clock does not move)."""
    del now  # the whole idea of the VAR is that time stands still
    return self.state


def _window_states(saved, start, end):
  """Saved states between `start` and `end`, the last one exactly at `end`.

    If no state was saved after `end` yet, the window ends at the last one
    (the goal arrived at the very end of the ring).
    """
  picked = [item for item in saved if start <= item[0] <= end]
  if not picked or picked[-1][0] >= end - STEP_TOLERANCE:
    return picked
  later = [item for item in saved if item[0] > end]
  if not later:
    return picked
  gap = later[0][0] - picked[-1][0]
  mix = 1.0 if gap <= STEP_TOLERANCE else (end - picked[-1][0]) / gap
  return picked + [(end, _mix(picked[-1][1], later[0][1], min(1.0, mix)))]


def _mix(first, second, mix):
  """Copy of `second` with the ball and the players moved towards `first`."""
  state = copy.deepcopy(second)
  _blend(first.get("ball"), state.get("ball"), mix)
  before = first.get("players") or ()
  for index, player in enumerate(state.get("players") or ()):
    if index < len(before):
      _blend(before[index], player, mix)
  return state


def _blend(before, now, mix):
  """Interpolates the position of one object (0 keeps `before`)."""
  if not before or not now:
    return
  for key in POSITION_KEYS:
    now[key] = _between(before.get(key), now.get(key), mix)


def _between(before, now, mix):
  """Value `mix` of the way from `before` to `now`."""
  start = float(before or 0.0)
  end = float(now or 0.0)
  return start + (end - start) * mix
