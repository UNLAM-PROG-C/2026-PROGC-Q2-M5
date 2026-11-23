"""Crisp power art and world-space player overlays."""
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  pylint: disable=wrong-import-position

from fdc import config  # noqa: E402
from fdc.gpu import effects_state  # noqa: E402
from fdc.ui import icons  # noqa: E402
from fdc.ui import palette  # noqa: E402
from fdc.ui import render  # noqa: E402

PLAYER = {"x": 150.0, "y": 150.0, "scale": 1.0, "burned": True,
          "burned_left": 1.5, "frozen": True}
FROZEN = {"power": "freeze_rival", "prop": "frozen", "target": "p0",
          "left": 1.5, "dur": 2.0}


def colours(surface, rect):
  """Read solid and partially transparent art pixels in a rectangle."""
  return {tuple(surface.get_at((x, y)))
          for y in range(rect.top, rect.bottom)
          for x in range(rect.left, rect.right)
          if surface.get_at((x, y)).a}


class FlameTest(unittest.TestCase):
  def test_crown_frames_are_cached_and_animated(self):
    first = icons.flame_crown(0, 1.0)
    second = icons.flame_crown(1, 1.0)
    self.assertIs(first, icons.flame_crown(0, 1.0))
    self.assertNotEqual(pygame.image.tobytes(first[0], "RGBA"),
                        pygame.image.tobytes(second[0], "RGBA"))

  def test_player_flames_have_crisp_bands_inside_the_box(self):
    surface = pygame.Surface((300, 200), pygame.SRCALPHA)
    rect = pygame.Rect(0, 0, 88, 110)
    rect.midbottom = (150, 152)
    back, front = icons.flame_crown(0, PLAYER["scale"])
    surface.blit(back, rect)
    surface.blit(front, rect)
    self.assertIn((*icons.FLAME_RED, 255), colours(surface, rect))
    self.assertIn((*icons.FLAME_YELLOW, 255), colours(front, front.get_rect()))
    self.assertEqual(front.get_alpha(), 200)
    self.assertEqual(surface.get_at((150, 20)).a, 0)


class IceTest(unittest.TestCase):
  def setUp(self):
    pygame.init()
    pygame.display.set_mode((300, 200))

  def test_ice_draws_the_outline_and_edge_over_the_player(self):
    surface = pygame.Surface((300, 200), pygame.SRCALPHA)
    render._draw_ice(surface, PLAYER, FROZEN)
    x0, y0, x1, y1 = effects_state.ice_box(PLAYER, FROZEN)
    pixels = colours(surface, pygame.Rect(x0, y0, x1 - x0, y1 - y0))
    self.assertIn((*palette.INK, 255), pixels)
    self.assertIn(render.ICE_EDGE, pixels)
    self.assertEqual(surface.get_at((x0, y0)).a, 0)

  def test_ice_grows_from_the_feet(self):
    start = effects_state.ice_box(PLAYER, dict(FROZEN, left=2.0))
    middle = effects_state.ice_box(PLAYER, dict(FROZEN, left=1.95))
    full = effects_state.ice_box(PLAYER, FROZEN)
    self.assertEqual(start[1], start[3])
    self.assertLess(full[1], middle[1])
    self.assertLess(middle[1], start[1])
    self.assertEqual(start[3], middle[3])


class HudIconTest(unittest.TestCase):
  BURN = {"power": "fire", "prop": "burned", "target": "p0",
          "left": 2.0, "dur": 2.0}
  SPEED = {"power": "speed_up", "prop": "speed", "target": "p0",
           "left": 4.0, "dur": 6.0}

  def test_a_burn_uses_the_flame_and_the_fire_colour(self):
    self.assertIs(render.effect_icon(self.BURN, 32), icons.flame())
    self.assertEqual(render.effect_color(self.BURN), palette.ORANGE)

  def test_other_effects_keep_their_power_badge(self):
    badge = render.effect_icon(self.SPEED, 32)
    self.assertIs(badge, icons.power_icon("speed_up", 32))
    self.assertNotEqual(render.effect_color(self.SPEED), palette.ORANGE)


if __name__ == "__main__":
  unittest.main()
