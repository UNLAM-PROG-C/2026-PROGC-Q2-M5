"""Celebration of a goal, the confetti and the longer replay (F10).

No window and no CUDA: the celebration is a pure clock, the confetti is
arithmetic on numpy and the replay window is a slice of the saved states.
The only pixels are the ones of the numpy version of the `confetti` kernel.
"""
import unittest

import numpy as np

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc import config
from fdc import protocol
from fdc.gpu import celebration
from fdc.gpu import cpu_ref
from fdc.gpu import metrics
from fdc.gpu import overlay
from fdc.gpu import replay

G = config.Gpu
ARENA = config.Arena
START = 40.0            # clock of the tests (s)
DT = 1 / 60.0           # s between frames
STEP = 0.05             # s between the saved states of these tests
FRAMES = 40             # frames of the confetti in these tests
W, H = 96, 64           # size of the image of the kernel test
BALL_R = 18.0           # px: radius of the ball in these states


def state(x=600.0, y=300.0):
  """Match state with the ball at (x, y)."""
  return {"phase": protocol.PHASE_PLAYING, "paused": False, "score": [0, 0],
          "goals": [ARENA.GOAL_HEIGHT] * 2, "effects": [],
          "ball": {"x": x, "y": y, "r": BALL_R, "vx": 0.0, "vy": 0.0},
          "players": [{"x": 300.0, "y": 600.0},
                      {"x": 900.0, "y": 600.0}]}


class CelebrationTest(unittest.TestCase):
  """The clock of the party: how long, how hard and when it throws."""

  def setUp(self):
    self.party = celebration.Celebration(START, {"side": 0},
                                         duration=2.0)

  def test_marks_the_second_after_the_goal(self):
    self.assertAlmostEqual(self.party.progress(START + 1.0), 0.5)
    self.assertFalse(self.party.finished(START + 1.0))
    self.assertTrue(self.party.finished(START + 2.0))
    self.assertEqual(self.party.progress(START + 9.0), 1.0)

  def test_the_duration_is_configurable(self):
    short = celebration.Celebration(START, duration=0.5)
    self.assertTrue(short.finished(START + 0.5))
    default = celebration.Celebration(START)
    self.assertEqual(default.duration, G.GOAL_CELEBRATION)

  def test_the_shake_and_the_flash_fade_out(self):
    self.assertGreater(self.party.shake(START), self.party.shake(START + 1))
    self.assertEqual(self.party.flash(START + 5.0), 0.0)
    self.assertGreater(self.party.flash(START), 0.0)
    self.assertGreater(self.party.flash(START),
                       self.party.flash(START + G.CONFETTI_FLASH_TIME / 2))

  def test_the_bursts_fire_once_each(self):
    first = self.party.due_bursts(START)
    self.assertEqual(first, [0])
    self.assertEqual(self.party.due_bursts(START), [])
    self.assertEqual(self.party.due_bursts(START + 10.0),
                     list(range(1, len(celebration.BURSTS))))
    self.assertEqual(self.party.due_bursts(START + 20.0), [])

  def test_the_bursts_do_not_depend_on_the_frames(self):
    """Same clock, same bursts: the demo repeats frame by frame."""
    other = celebration.Celebration(START, {"side": 0})
    mine, theirs = [], []
    for frame in range(130):
      now = START + frame * DT
      mine += self.party.due_bursts(now)
      theirs += other.due_bursts(now)
    self.assertEqual(mine, theirs)
    self.assertEqual(mine, list(range(len(celebration.BURSTS))))

  def test_a_long_frame_throws_the_missed_bursts(self):
    self.assertEqual(self.party.due_bursts(START + 1.9),
                     list(range(len(celebration.BURSTS))))
    self.assertEqual(self.party.due_bursts(START + 1.95), [])

  def test_the_bursts_come_from_inside_the_arena(self):
    for index in range(len(celebration.BURSTS) + 3):
      x, y = self.party.burst_shape(index)
      self.assertGreaterEqual(x, 0.0)
      self.assertLessEqual(x, ARENA.WIDTH)
      self.assertGreaterEqual(y, 0.0)
      self.assertLessEqual(y, ARENA.FLOOR_Y)

  def test_mouth_of_the_scored_goal(self):
    left = celebration.Celebration(START, {"side": 0})
    right = celebration.Celebration(START, {"side": 1})
    middle = celebration.Celebration(START, {})
    self.assertEqual(left.mouth_x(), ARENA.GOAL_DEPTH)
    self.assertEqual(right.mouth_x(), ARENA.WIDTH - ARENA.GOAL_DEPTH)
    self.assertEqual(middle.mouth_x(), ARENA.WIDTH / 2.0)


class ConfettiFieldTest(unittest.TestCase):
  """The pool of paper bits: it throws, moves down and dies."""

  def setUp(self):
    self.field = celebration.ConfettiField()
    self.x, self.y = ARENA.WIDTH / 2.0, 40.0

  def test_a_burst_fills_the_pool(self):
    self.assertFalse(self.field.alive())
    self.field.burst(self.x, self.y)
    self.assertTrue(self.field.alive())
    pos, col = self.field.live()
    self.assertEqual(len(pos), G.CONFETTI_PER_BURST)
    self.assertEqual(col.shape[1], celebration.COL_CHANNELS)
    self.assertTrue(np.allclose(pos, (self.x, self.y)))

  def test_the_bits_fall_and_die(self):
    self.field.burst(self.x, self.y)
    lowest = self.y
    for _ in range(int(max(G.CONFETTI_LIFE) / DT) + 8):
      self.field.update(DT)
      pos, _ = self.field.live()
      if len(pos):
        lowest = max(lowest, float(pos[:, 1].max()))
    self.assertGreater(lowest, self.y)      # gravity pulls them down
    self.assertFalse(self.field.alive())

  def test_the_bits_are_thin_and_turn(self):
    self.field.burst(self.x, self.y)
    for _ in range(FRAMES):
      self.field.update(DT)
    pos, col = self.field.live()
    self.assertTrue(len(pos) > 0)
    widths = col[:, celebration.HW_COLUMN]
    heights = col[:, celebration.HH_COLUMN]
    self.assertTrue(np.all(widths >= celebration.MIN_SIZE))
    self.assertTrue(np.all(heights <= widths))
    self.assertTrue(np.all(widths >= G.CONFETTI_SIZE[0]))
    del pos

  def test_the_same_seed_gives_the_same_confetti(self):
    """The demo needs it: the same burst is the same paper."""
    twin = celebration.ConfettiField()
    for field in (self.field, twin):
      field.burst(self.x, self.y)
      for _ in range(FRAMES):
        field.update(DT)
    first, colour = self.field.live()
    other, other_colour = twin.live()
    self.assertTrue(np.array_equal(first, other))
    self.assertTrue(np.array_equal(colour, other_colour))

  def test_a_full_pool_recycles_the_oldest(self):
    small = celebration.ConfettiField(count=10)
    for _ in range(4):
      small.burst(self.x, self.y)
    self.assertEqual(int((small.life > 0).sum()), 10)
    self.assertTrue(small.alive())

  def test_clear_kills_the_paper(self):
    self.field.burst(self.x, self.y)
    self.field.clear()
    self.assertFalse(self.field.alive())
    pos, _ = self.field.live()
    self.assertEqual(len(pos), 0)


class ConfettiPaintingTest(unittest.TestCase):
  """The numpy version of the kernel paints where the bits are."""

  def test_the_paper_lands_where_the_bit_is(self):
    image = np.zeros((H, W, 3), np.uint8)
    pos = np.array([[20.0, 20.0], [60.0, 40.0]], np.float32)
    col = np.array([[1.0, 1.0, 1.0, 3.0, 2.0],
                    [0.0, 0.0, 1.0, 2.0, 1.0]], np.float32)
    out = cpu_ref.Cpu().confetti(image, pos, col, 1.0)
    self.assertTrue(np.all(out[18:23, 17:24, 0] > 0))
    self.assertEqual(int(out[0, 0, 0]), 0)
    self.assertTrue(np.all(out[39:42, 58:63, 2] > 0))

  def test_the_paper_keeps_its_colour_over_the_grass(self):
    """F10: the paper is opaque, so red reads red on green."""
    image = np.full((H, W, 3), (30, 160, 40), np.uint8)
    pos = np.array([[40.0, 30.0]], np.float32)
    col = np.array([[1.0, 0.2, 0.2, 3.0, 2.0]], np.float32)
    out = cpu_ref.Cpu().confetti(image, pos, col, 1.0)
    patch = out[28:33, 37:44]
    self.assertTrue(np.all(patch[:, :, 0] > 240))
    self.assertTrue(np.all(patch[:, :, 1] < 80))
    untouched = out[0, 0]
    self.assertTrue(np.array_equal(untouched, (30, 160, 40)))

  def test_the_paper_leaves_the_image_alone_when_it_is_out(self):
    image = np.full((H, W, 3), 40, np.uint8)
    pos = np.array([[-40.0, -40.0]], np.float32)
    col = np.array([[1.0, 1.0, 1.0, 3.0, 3.0]], np.float32)
    out = cpu_ref.Cpu().confetti(image, pos, col, 1.0)
    self.assertTrue(np.array_equal(out, image))


class ReplayWindowTest(unittest.TestCase):
  """The window of a goal ends REPLAY_AFTER_GOAL s after the goal."""

  def setUp(self):
    self.history = replay.StateHistory(seconds=20.0, step=STEP)

  def test_the_window_ends_half_a_second_after_the_goal(self):
    for index in range(200):
      self.history.feed(state(x=index * 10.0), START + index * STEP)
    goal = START + 7.0
    frames = self.history.window(goal)
    self.assertAlmostEqual(frames[-1][0], goal + G.REPLAY_AFTER_GOAL)
    self.assertLessEqual(frames[0][0], goal - G.REPLAY_DURATION + STEP)

  def test_the_last_state_is_interpolated_when_missing(self):
    for index in range(60):
      self.history.feed(state(x=index * 10.0), START + index * STEP)
    goal = START + 2.02            # between two saved states
    frames = self.history.window(goal)
    self.assertAlmostEqual(frames[-1][0], goal + G.REPLAY_AFTER_GOAL)
    self.assertIn("ball", frames[-1][1])

  def test_without_a_later_state_the_window_stops_at_the_last(self):
    self.history.feed(state(), START)
    frames = self.history.window(START)
    self.assertEqual(len(frames), 1)
    self.assertEqual(frames[-1][0], START)

  def test_an_empty_history_has_no_window(self):
    self.assertEqual(replay.StateHistory().window(START), [])

  def test_the_replay_lasts_what_the_window_lasts(self):
    for index in range(120):
      self.history.feed(state(), START + index * STEP)
    goal = START + 4.0
    frames = self.history.window(goal)
    span = frames[-1][0] - frames[0][0]
    self.assertAlmostEqual(span, G.REPLAY_DURATION + G.REPLAY_AFTER_GOAL,
                           places=6)


class ReportedStagesTest(unittest.TestCase):
  """The confetti shows up as one more kernel (F10)."""

  def test_the_metrics_have_a_confetti_stage(self):
    self.assertIn("confetti", metrics.STAGES)

  def test_the_overlay_lists_the_confetti(self):
    data = {"confetti": 0.42, "crt": 0.0}
    names = [name for name, _ in overlay._kernels(data)]
    self.assertEqual(names, ["confetti"])


if __name__ == "__main__":
  unittest.main()
