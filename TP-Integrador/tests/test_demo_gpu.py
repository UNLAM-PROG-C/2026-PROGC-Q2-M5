"""The match loop with the effects, headless (fdc.gpu.demo).

It is the end-to-end check: a real match runs a few frames with the chain
on and off, and both have to finish with the same screen size. The GPU run
is skipped when there is no CUDA; the "off" run always happens.
"""
import functools
import unittest
from unittest import mock

import driver
import pygame

import helpers  # pylint: disable=unused-import
from fdc import config
from fdc.gpu import backend
from fdc.gpu import demo
from fdc.gpu import env
from fdc.ui import assets
from fdc.ui import layout
from fdc.ui import render
from fdc.ui import screens

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
  screen.menu_return = False
  screen.director = demo.DemoDirector()
  screen.director.index = demo.SEGMENTS.index(("hielo", "ice"))
  rows = []
  draw = assets.draw_text
  with mock.patch.object(assets, "draw_text", side_effect=functools.partial(
      _record_row, draw, rows)):
    screen._draw_replay_sign(surf, GOAL_WINDOW)
    screen._draw_label(surf)
  return rows


class DemoEffectsTest(unittest.TestCase):
  """Forced effects of the playable demo."""

  def test_fire_adds_embers_at_the_first_players_feet(self):
    player = {"x": 350.0, "y": 640.0}
    params = demo.FORCED["fire"]
    self.assertEqual(params["burned"]({"players": [player]}),
                     ((player["x"], player["y"]),))
    self.assertEqual(params["burned"](None), ())


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


class MenuDemoTest(unittest.TestCase):
  def test_demo_button_keeps_quality_and_escape_returns_home(self):
    game = driver.make_app(test_mode=False, quality_mode="sin-efectos")
    self.addCleanup(game.shutdown)
    d = driver.Driver(game)
    quality = game.postfx.quality_mode_name()
    d.until(lambda: isinstance(d.screen(), screens.MenuScreen))
    self._click_demo(d)
    self.assertIsInstance(d.screen(), demo.DemoScreen)
    self.assertEqual(game.postfx.quality_mode_name(), quality)
    d.tap(pygame.K_ESCAPE)
    self.assertTrue(game.running)
    self.assertIsInstance(d.screen(), screens.MenuScreen)

  def _click_demo(self, d):
    menu = d.screen().menu
    labels = [label for label, _ in menu.items]
    self.assertIn("DEMO", labels)
    rect = menu.rects()[labels.index("DEMO")]
    d.post(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)


@unittest.skipUnless(HAVE_GPU, "no CUDA here (see INSTALACION.md)")
class DemoGpuTest(unittest.TestCase):
  """With CUDA the chain runs inside the loop and reports its cost."""

  @classmethod
  def setUpClass(cls):
    demo.headless()
    cls.data = demo.run(FRAMES, ["--calidad", "full"])

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
