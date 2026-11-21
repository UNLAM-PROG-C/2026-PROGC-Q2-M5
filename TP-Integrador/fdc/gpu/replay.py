"""Replay of the goals (F5).

The chain keeps the last `config.Gpu.REPLAY_SECONDS` seconds of match states,
so the play leading to a goal can be shown again.
Everything here is plain Python (no pygame, no numpy): the rules are tested
without a window.

Two pieces:
  - `StateHistory`: the ring of saved states (one every `REPLAY_STEP` s).
  - `ReplayPlayer`: plays those states again in `REPLAY_DURATION` s,
    interpolating the positions so the movement does not look chopped.
"""
import copy

from fdc import config

G = config.Gpu
PENULTIMATE = -2           # second to last recorded frame
REPLAY_KIND = "replay"      # the chain draws this as an old television
MIN_FRAMES = 2              # states needed to interpolate the positions
MIN_DURATION = 0.001        # s: a replay never lasts zero
STEP_TOLERANCE = 1e-9       # s: the step is never exact in float sums
FULL = 1.0                  # end of the progress
POSITION_KEYS = ("x", "y")  # fields interpolated between two states


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
    return self.frames[PENULTIMATE], self.frames[-1]


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
