"""Replay of the goal: the simulation decides when it starts and how long.

The match stays frozen for the party and then for the replay, but the clients
are not told "play the clip now and take your time": the simulation sends
EV_REPLAY when the window opens and resumes by itself when it closes. These
tests check that window, the frozen goal, the resume and the skip.

The real two-client run is `tools/replay_check.py`: it starts the server and
two clients (one in FULL and one in the mode "SIN EFECTOS") and saves what each
one saw.
"""
import unittest

import helpers
from fdc import config
from fdc import protocol
from fdc.sim import match

RULES = config.MatchRules
ARENA = config.Arena
DT = config.PHYSICS_DT
LEFT = 0                # the left goal: the ball goes in from the right
TOLERANCE = 2 * DT      # s: the event leaves a step after the boundary


def scored_match(presentation=True):
  """Match in play with the ball going into the left goal."""
  m = match.Match(1, seed=3, presentation=presentation)
  m.phase, m.phase_left = protocol.PHASE_PLAYING, 0.0
  m.powers.spawn_timer = helpers.NO_SPAWN
  m.players[0].x, m.players[1].x = 500.0, 780.0
  m.ball.x = m.goals[LEFT].mouth_x + 60
  m.ball.y = ARENA.FLOOR_Y - 60
  m.ball.vx, m.ball.vy = -700, 0
  return m


def step_until(m, predicate, limit):
  """Steps the match until `predicate(m)`, at most `limit` seconds."""
  events = []
  for _ in range(int(limit / DT)):
    events += m.step(DT)
    if predicate(m):
      return events
  return events


def of_type(events, etype):
  """The payloads of the events of that type."""
  return [data for kind, data in events if kind == etype]


class ReplayWindowTest(unittest.TestCase):
  """The frozen goal: the party, the replay and the resume."""

  def goal(self):
    """A match with a goal just scored."""
    m = scored_match()
    events = step_until(m, lambda mm: mm.phase == protocol.PHASE_GOAL, 1.0)
    self.assertEqual(len(of_type(events, protocol.EV_GOAL)), 1)
    return m

  def test_replay_is_announced_with_the_hold_left(self):
    m = self.goal()
    events = step_until(m, lambda mm: mm.phase_left <= RULES.GOAL_REPLAY,
                        RULES.GOAL_HOLD)
    replays = of_type(events, protocol.EV_REPLAY)
    self.assertEqual(len(replays), 1)
    self.assertEqual(replays[0]["seconds"], RULES.GOAL_REPLAY)
    self.assertAlmostEqual(m.phase_left, RULES.GOAL_REPLAY,
                           delta=TOLERANCE)
    self.assertEqual(m.phase, protocol.PHASE_GOAL)   # still frozen

  def test_play_comes_back_only_after_the_hold(self):
    m = self.goal()
    step_until(m, lambda mm: mm.phase_left <= RULES.GOAL_REPLAY,
               RULES.GOAL_HOLD)
    events = step_until(m, lambda mm: mm.phase != protocol.PHASE_GOAL,
                        RULES.GOAL_HOLD)
    self.assertEqual(of_type(events, protocol.EV_REPLAY), [])
    self.assertEqual(m.phase, protocol.PHASE_COUNTDOWN)
    self.assertAlmostEqual(m.phase_left, RULES.GOAL_COUNTDOWN,
                           delta=TOLERANCE)
    events = step_until(m, lambda mm: mm.phase == protocol.PHASE_PLAYING,
                        RULES.GOAL_COUNTDOWN + 2 * DT)
    self.assertEqual(len(of_type(events, protocol.EV_KICKOFF)), 1)

  def test_without_effects_there_is_no_replay_at_all(self):
    m = scored_match(presentation=False)
    events = step_until(m, lambda mm: mm.phase == protocol.PHASE_GOAL, 1.0)
    self.assertEqual(len(of_type(events, protocol.EV_GOAL)), 1)
    events = step_until(m, lambda mm: mm.phase != protocol.PHASE_GOAL,
                        RULES.GOAL_HOLD + 1.0)
    self.assertEqual(of_type(events, protocol.EV_REPLAY), [])
    self.assertAlmostEqual(m.goal_hold, RULES.GOAL_CELEBRATION, delta=DT)

  def test_nobody_moves_while_the_replay_runs(self):
    m = self.goal()
    step_until(m, lambda mm: mm.phase_left <= RULES.GOAL_REPLAY,
               RULES.GOAL_HOLD)
    before = [(p.x, p.y) for p in m.players] + [(m.ball.x, m.ball.y)]
    for _ in range(int(RULES.GOAL_REPLAY / DT) - 1):
      m.set_input(0, False, True, 1, 1)   # both players try to move
      m.set_input(1, True, False, 1, 1)
      m.step(DT)
    after = [(p.x, p.y) for p in m.players] + [(m.ball.x, m.ball.y)]
    self.assertEqual(before, after)
    self.assertEqual(m.phase, protocol.PHASE_GOAL)

  def test_skipping_the_replay_cancels_the_rest_of_it(self):
    m = self.goal()
    step_until(m, lambda mm: mm.phase_left <= RULES.GOAL_REPLAY,
               RULES.GOAL_HOLD)
    ok, _ = m.skip_goal()
    self.assertTrue(ok)
    self.assertEqual(m.phase, protocol.PHASE_COUNTDOWN)
    events = []
    for _ in range(int(RULES.GOAL_COUNTDOWN / DT) + 1):
      events += m.step(DT)
    self.assertEqual(of_type(events, protocol.EV_REPLAY), [])

  def test_a_golden_goal_has_its_replay_and_ends_the_match(self):
    m = scored_match()
    m.golden, m.score = True, [1, 1]
    events = step_until(m, lambda mm: mm.phase == protocol.PHASE_GOAL, 1.0)
    self.assertEqual(len(of_type(events, protocol.EV_GOAL)), 1)
    events = step_until(m, lambda mm: mm.phase != protocol.PHASE_GOAL,
                        RULES.GOAL_HOLD + 1.0)
    self.assertEqual(len(of_type(events, protocol.EV_REPLAY)), 1)
    self.assertEqual(m.phase, protocol.PHASE_FINISHED)


if __name__ == "__main__":
  unittest.main()
