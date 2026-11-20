"""The match loop with the effects, headless (fdc.gpu.demo).

It is the end-to-end check: a real match runs a few frames with the chain
on and off, and both have to finish with the same screen size. The GPU run
is skipped when there is no CUDA; the "off" run always happens.
"""
import functools
import unittest
from unittest import mock

import pygame

import helpers  # pylint: disable=unused-import
from fdc import config
from fdc.gpu import backend
from fdc.gpu import demo
from fdc.gpu import env
from fdc.ui import assets
from fdc.ui import layout
from fdc.ui import render

FRAMES = 40             # frames of each run (short: it is a test)
STAGES = ("glow", "particles", "frame", "fps")
HAVE_GPU = config.Gpu.ENABLED and env.setup() and backend.available()
GOAL_WINDOW = (0, 3)    # replay progress and seconds left during a goal


def _record_row(draw, rows, *args, **kwargs):
  rect = draw(*args, **kwargs)
  rows.append(rect)
  return rect


def _demo_signs(surf):
  screen = demo.DemoScreen.__new__(demo.DemoScreen)
  screen.director = demo.DemoDirector()
  screen.director.index = demo.SEGMENTS.index(("hielo", "ice"))
  rows = []
  draw = assets.draw_text
  with mock.patch.object(screen, "_replay_key", return_value="replay"), \
       mock.patch.object(assets, "draw_text", side_effect=functools.partial(
           _record_row, draw, rows)):
    screen._draw_replay_sign(surf, GOAL_WINDOW)
    screen._draw_label(surf)
  return rows


class DemoSignsTest(unittest.TestCase):
  def test_demo_signs_have_separate_rows_during_goal_replay(self):
    surf = pygame.Surface((layout.SCREEN_W, layout.SCREEN_H))
    replay_title, replay_hint, title, controls = _demo_signs(surf)
    board_bottom = render.BOARD_TOP + render.BOARD[1]
    goal_band = pygame.Rect(0, render.GOAL_BAND_TOP, surf.get_width(),
                            render.GOAL_BAND_H)
    rows = (replay_title, replay_hint, title, controls)
    for row in rows:
      self.assertTrue(surf.get_rect().contains(row))
      self.assertGreaterEqual(row.top, board_bottom)
      self.assertFalse(row.colliderect(goal_band), row)
    for upper, lower in zip(rows, rows[1:]):
      self.assertLess(upper.bottom, lower.top)


class DemoOffTest(unittest.TestCase):
  """Without the effects the loop has to run as before."""

  @classmethod
  def setUpClass(cls):
    demo.headless()
    cls.data = demo.run(FRAMES, ["--no-gpu"])

  def test_loop_runs(self):
    self.assertEqual(self.data["mode"], "off")
    self.assertGreaterEqual(self.data["frames"], 1)

  def test_frame_time(self):
    self.assertGreater(self.data["ms_frame"], 0.0)


@unittest.skipUnless(HAVE_GPU, "no CUDA here (see INSTALACION.md)")
class DemoGpuTest(unittest.TestCase):
  """With CUDA the chain runs inside the loop and reports its cost."""

  @classmethod
  def setUpClass(cls):
    demo.headless()
    cls.data = demo.run(FRAMES, ["--gpu-quality", "media"])

  def test_gpu_mode(self):
    self.assertEqual(self.data["mode"], "gpu")
    self.assertIn("NVIDIA", self.data["gpu"])

  def test_stages_reported(self):
    for key in STAGES:
      self.assertIn(key, self.data)
    self.assertGreater(self.data["frame"], 0.0)
    self.assertGreater(self.data["ms_frame"], 0.0)


if __name__ == "__main__":
  unittest.main()
