"""Replay and VAR of the goals (fdc.gpu.replay).

No window and no CUDA: the rules of F5 are pure functions of the saved
states and the clock, so they are checked here frame by frame.
"""
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc import config
from fdc import protocol
from fdc.gpu import replay

G = config.Gpu
ARENA = config.Arena
STEP = 0.05          # s between the states of these tests
START = 100.0        # clock of the tests (s)
BALL_R = 18.0        # px: radius of the ball in these states
MOUTH = ARENA.GOAL_DEPTH          # x of the mouth of the left goal
BAR_Y = ARENA.FLOOR_Y - ARENA.GOAL_HEIGHT   # y of the crossbar


def state(x=600.0, y=400.0, height=ARENA.GOAL_HEIGHT, playing=True):
  """Match state with two players and the ball at (x, y)."""
  return {"phase": (protocol.PHASE_PLAYING if playing
                    else protocol.PHASE_COUNTDOWN),
          "paused": False, "score": [0, 0], "goals": [height, height],
          "ball": {"x": x, "y": y, "r": BALL_R, "vx": 0.0, "vy": 0.0},
          "players": [{"x": 300.0, "y": 600.0},
                      {"x": 900.0, "y": 600.0}]}


class HistoryTest(unittest.TestCase):
  """The ring saves one state every step and drops the old ones."""

  def setUp(self):
    self.history = replay.StateHistory(seconds=1.0, step=STEP)

  def test_saves_one_state_every_step(self):
    for index in range(10):
      self.history.feed(state(x=index * 10.0), index * STEP)
    self.assertEqual(len(self.history.saved), 10)

  def test_ignores_states_inside_the_step(self):
    self.history.feed(state(), 0.0)
    self.history.feed(state(), STEP / 2)
    self.assertEqual(len(self.history.saved), 1)

  def test_drops_the_states_out_of_the_window(self):
    for index in range(30):
      self.history.feed(state(), index * STEP)
    self.assertLessEqual(len(self.history.saved),
                         int(1.0 / STEP) + 1)

  def test_saves_a_copy_of_the_state(self):
    live = state()
    self.history.feed(live, 0.0)
    live["ball"]["x"] = 1.0
    self.assertEqual(self.history.saved[0][1]["ball"]["x"], 600.0)

  def test_empty_state_is_ignored(self):
    self.history.feed({}, 0.0)
    self.assertEqual(self.history.frames(), [])

  def test_frames_returns_the_tail(self):
    for index in range(20):
      self.history.feed(state(), index * STEP)
    frames = self.history.frames(0.2)
    self.assertGreaterEqual(len(frames), 2)
    self.assertLess(len(frames), len(self.history.saved))

  def test_clear_forgets_everything(self):
    self.history.feed(state(), 0.0)
    self.history.clear()
    self.assertEqual(self.history.saved, [])
    self.assertIsNone(self.history.last_t)


class IsCloseTest(unittest.TestCase):
  """A goal is close when the ball went in grazing the crossbar."""

  def test_grazing_the_bar(self):
    self.assertTrue(replay.near_bar(state(), 0, 300.0, BAR_Y + 5.0))

  def test_touching_the_bar(self):
    self.assertTrue(replay.near_bar(state(), 0, 300.0, BAR_Y))

  def test_completely_under_the_bar(self):
    self.assertFalse(replay.near_bar(state(), 0, 300.0, 600.0))

  def test_above_the_bar_is_not_a_goal(self):
    self.assertFalse(replay.near_bar(state(), 0, 300.0, BAR_Y - 5.0))

  def test_short_goal_is_not_close(self):
    low = state(height=ARENA.GOAL_MIN_HEIGHT)
    self.assertFalse(replay.near_bar(low, 0, 300.0, BAR_Y + 5.0))

  def test_unknown_side_is_never_close(self):
    self.assertFalse(replay.near_bar(state(), None, MOUTH, BAR_Y))
    self.assertFalse(replay.near_bar({}, 0, MOUTH, BAR_Y))

  def test_history_uses_the_ball_of_the_event(self):
    history = replay.StateHistory(seconds=1.0, step=STEP)
    for index in range(4):
      history.feed(state(), index * STEP)
    self.assertTrue(history.is_close(0, (300.0, BAR_Y + 5.0)))
    self.assertFalse(history.is_close(0, (300.0, 600.0)))

  def test_history_without_ball_uses_the_saved_state(self):
    history = replay.StateHistory(seconds=1.0, step=STEP)
    history.feed(state(y=BAR_Y + 5.0), 0.0)
    self.assertTrue(history.is_close(0))
    self.assertFalse(history.is_close(None))

  def test_empty_history_is_not_close(self):
    self.assertFalse(replay.StateHistory().is_close(0, (MOUTH, BAR_Y)))


class ReplayPlayerTest(unittest.TestCase):
  """The replay walks the saved states in REPLAY_DURATION seconds."""

  def setUp(self):
    self.frames = [(START + index * STEP, state(x=index * 10.0))
                   for index in range(5)]
    self.player = replay.ReplayPlayer(self.frames, START, duration=1.0)

  def test_starts_at_the_oldest_state(self):
    self.assertEqual(self.player.state_at(START)["ball"]["x"], 0.0)

  def test_ends_at_the_newest_state(self):
    self.assertEqual(self.player.state_at(START + 1.0)["ball"]["x"], 40.0)

  def test_interpolates_the_positions(self):
    middle = self.player.state_at(START + 0.5)["ball"]["x"]
    self.assertAlmostEqual(middle, 20.0, places=3)

  def test_players_move_too(self):
    frames = [(START, state()), (START + STEP, state())]
    frames[1][1]["players"][0]["x"] = 400.0
    player = replay.ReplayPlayer(frames, START, duration=1.0)
    middle = player.state_at(START + 0.5)["players"][0]["x"]
    self.assertAlmostEqual(middle, 350.0, places=3)

  def test_progress_and_end(self):
    self.assertAlmostEqual(self.player.progress(START + 0.25), 0.25)
    self.assertFalse(self.player.finished(START + 0.99))
    self.assertTrue(self.player.finished(START + 1.0))
    self.assertEqual(self.player.progress(START + 5.0), 1.0)

  def test_one_state_is_played_without_interpolation(self):
    player = replay.ReplayPlayer([(START, state(x=70.0))], START)
    self.assertEqual(player.state_at(START + 0.5)["ball"]["x"], 70.0)

  def test_a_replay_has_no_stage(self):
    self.assertIsNone(self.player.stage(START))
    self.assertEqual(self.player.kind, replay.REPLAY_KIND)


class VarPlayerTest(unittest.TestCase):
  """The VAR freezes the frame: reviewing, then the goal stands."""

  def setUp(self):
    self.frozen = state(x=MOUTH + 2.0, y=500.0)
    self.player = replay.VarPlayer(self.frozen, START, review=1.0,
                                   confirm=0.5)

  def test_the_two_stages(self):
    self.assertEqual(self.player.stage(START), replay.REVIEW)
    self.assertEqual(self.player.stage(START + 1.0), replay.CONFIRMED)

  def test_it_ends_after_both(self):
    self.assertFalse(self.player.finished(START + 1.4))
    self.assertTrue(self.player.finished(START + 1.5))

  def test_the_frame_is_frozen(self):
    self.frozen["ball"]["x"] = 1.0
    self.assertEqual(self.player.state_at(START)["ball"]["x"], MOUTH + 2.0)

  def test_kind(self):
    self.assertEqual(self.player.kind, replay.VAR_KIND)


class GoalClipTest(unittest.TestCase):
  """F10: the clip is short, it ends at the goal and the match waits."""

  SAVED = 200              # states fed to the history
  GOAL_BEFORE_END = 1.5    # s between the goal and the newest state

  def test_the_clip_lasts_three_seconds(self):
    self.assertAlmostEqual(G.REPLAY_CLIP, 3.0)
    self.assertAlmostEqual(G.REPLAY_CLIP,
                           G.REPLAY_DURATION + G.REPLAY_AFTER_GOAL)

  def test_the_clip_is_the_last_seconds_before_the_goal(self):
    history = replay.StateHistory(seconds=G.REPLAY_SECONDS,
                                  step=G.REPLAY_STEP)
    for index in range(self.SAVED):
      history.feed(state(), START + index * G.REPLAY_STEP)
    goal = START + (self.SAVED - 1) * G.REPLAY_STEP - self.GOAL_BEFORE_END
    frames = history.window(goal)
    span = frames[-1][0] - frames[0][0]
    self.assertAlmostEqual(span, G.REPLAY_CLIP, delta=G.REPLAY_STEP)
    self.assertAlmostEqual(frames[-1][0], goal + G.REPLAY_AFTER_GOAL)
    self.assertGreaterEqual(frames[0][0],
                            goal - G.REPLAY_DURATION - G.REPLAY_STEP)

  def test_the_frozen_goal_covers_the_party_and_the_clip(self):
    rules = config.MatchRules
    self.assertGreaterEqual(rules.GOAL_HOLD,
                            G.GOAL_CELEBRATION + G.REPLAY_CLIP)
    self.assertGreaterEqual(rules.GOAL_REPLAY,
                            G.VAR_DURATION + G.VAR_CONFIRM)


if __name__ == "__main__":
  unittest.main()
