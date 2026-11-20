"""Heat map of the match (fdc.gpu.heatmap): recorder and overlay.

The recorder is plain Python plus numpy, so the rules of F6 are checked
here without CUDA; the kernels are compared with the GPU in
`test_gpu_kernels.HeatmapKernelTest`.
"""
import unittest

import numpy as np

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc import config
from fdc import protocol
from fdc.gpu import cpu_ref
from fdc.gpu import heatmap

G = config.Gpu
COLS, ROWS = 8, 5          # small grid of these tests
BALL_CELL = (4, 2)         # cell of the ball in `state`
IMAGE_SIZE = (64, 48)      # image of the render tests
SEED = 7                   # fixed random image
FEEDS = 3                  # frames fed in the accumulation tests


def state(x=640.0, y=400.0, phase=protocol.PHASE_PLAYING, paused=False):
  """Match state with the ball and two players."""
  return {"phase": phase, "paused": paused,
          "ball": {"x": x, "y": y, "r": 18.0},
          "players": [{"x": 300.0, "y": 600.0},
                      {"x": 900.0, "y": 600.0}]}


def image():
  """Small random RGB image."""
  rng = np.random.default_rng(SEED)
  return rng.integers(0, 256, (IMAGE_SIZE[1], IMAGE_SIZE[0], 3),
                      dtype=np.uint8)


class RecorderTest(unittest.TestCase):
  """The recorder buffers the points and sends them to the backend."""

  def setUp(self):
    self.rec = heatmap.HeatmapRecorder(COLS, ROWS)
    self.cpu = cpu_ref.Cpu()

  def test_only_playing_states_are_recorded(self):
    self.rec.feed(state(phase=protocol.PHASE_COUNTDOWN))
    self.rec.feed(state(paused=True))
    self.assertEqual(self.rec.recorded, 0)

  def test_playing_state_records_one_point_per_channel(self):
    self.rec.feed(state())
    self.assertEqual([len(cells) for cells in self.rec.pending],
                     [1, 1, 1])

  def test_due_after_the_frames_of_the_config(self):
    for _ in range(G.HEAT_FLUSH_FRAMES):
      self.rec.feed(state())
    self.assertTrue(self.rec.due())
    self.assertFalse(heatmap.HeatmapRecorder(COLS, ROWS).due())

  def test_flush_accumulates_in_the_cells(self):
    self.rec.feed(state())
    self.rec.flush(self.cpu)
    self.rec.snapshot(self.cpu)
    self.assertEqual([len(cells) for cells in self.rec.pending], [0, 0, 0])
    self.assertEqual(self.rec.frames, 0)
    column, row = BALL_CELL
    self.assertEqual(int(self.rec.grids[0][row][column]), 1)
    self.assertEqual(int(self.rec.grids.sum()), 3)

  def test_points_outside_the_pitch_are_dropped(self):
    self.rec.feed(state(x=-500.0))
    self.rec.flush(self.cpu)
    self.rec.snapshot(self.cpu)
    self.assertEqual(int(self.rec.grids[0].sum()), 0)

  def test_flush_without_points_does_nothing(self):
    self.rec.flush(self.cpu)
    self.assertEqual(int(self.rec.grids.sum()), 0)

  def test_grid_and_top_of_a_channel(self):
    self.rec.feed(state())
    self.rec.feed(state())
    self.rec.flush(self.cpu)
    self.rec.snapshot(self.cpu)
    self.assertEqual(self.rec.grid(0).shape, (COLS * ROWS,))
    self.assertEqual(self.rec.top(0), 2)
    self.assertEqual(int(self.rec.maxes[0]), 2)

  def test_clear_empties_the_map(self):
    self.rec.feed(state())
    self.rec.flush(self.cpu)
    self.rec.clear()
    self.assertEqual(int(self.rec.grids.sum()), 0)
    self.assertEqual(int(self.rec.maxes.sum()), 0)
    self.assertEqual(self.rec.recorded, 0)

  def test_render_needs_heat(self):
    img = image()
    self.assertIs(self.rec.render(self.cpu, img, 0), img)

  def test_render_paints_the_hot_cells(self):
    self.rec.feed(state())
    self.rec.flush(self.cpu)
    out = self.rec.render(self.cpu, image(), 0)
    self.assertEqual(out.shape, image().shape)
    self.assertFalse(np.array_equal(out, image()))

  def test_every_frame_counts_once(self):
    for _ in range(FEEDS):
      self.rec.feed(state())
    self.rec.flush(self.cpu)
    self.rec.snapshot(self.cpu)
    self.assertEqual(int(self.rec.grids[0].sum()), FEEDS)


if __name__ == "__main__":
  unittest.main()
