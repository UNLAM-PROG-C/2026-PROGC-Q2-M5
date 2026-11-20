"""Interface of the fire power: a flame that reads and a badge the ball
never hides.

The burnt player is drawn in every quality mode (CPU included), so the
flame and the seconds have to be understood as pixel art: fire colours,
no glow, and placed above the head, on the side away from the ball.
"""
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  pylint: disable=wrong-import-position

from fdc import config  # noqa: E402
from fdc.ui import icons  # noqa: E402
from fdc.ui import palette  # noqa: E402
from fdc.ui import render  # noqa: E402

SPEC = config.PlayerSpec
FLOOR = config.Arena.FLOOR_Y
# A 1.5 s burn of an idle player standing on the floor.
PLAYER = {"x": 470.0, "y": float(FLOOR), "scale": 1.0, "burned": True,
          "burned_left": 1.5}
FLAME_SIZE = (24, 30)       # px: the flame of the icon
TEXT_SIZE = (40, 16)        # px: "1.5s" with its outline
BALL_R = 20                 # px: a ball radius for the checks


def ball_at(side):
  """Ball radius and x of a ball touching the boots on that side."""
  x = PLAYER["x"] + side * (SPEC.HALF_WIDTH + BALL_R)
  return {"x": x, "y": FLOOR - BALL_R, "r": BALL_R}


def badge(side):
  """Flame and text boxes for a ball on that side of the player."""
  ball = ball_at(side)
  return render.burn_badge(PLAYER, ball["x"], FLAME_SIZE, TEXT_SIZE)


def opaque_colours(surface):
  """Colours of the opaque pixels of a small surface."""
  found = []
  for y in range(surface.get_height()):
    for x in range(surface.get_width()):
      colour = surface.get_at((x, y))
      if colour.a:
        found.append(tuple(colour)[:palette.RGB_CHANNELS])
  return found


class FlameTest(unittest.TestCase):
  """The flame is pixel art of fire colours, not a purple badge."""

  def test_it_is_drawn_with_fire_colours(self):
    colours = opaque_colours(icons.flame())
    self.assertIn(palette.ORANGE, colours)
    self.assertIn(palette.GOLD, colours)

  def test_it_is_neither_purple_nor_glowing(self):
    flame = icons.flame()
    global_colour = config.CATEGORY_COLORS[config.CATEGORY_GLOBAL]
    colours = opaque_colours(flame)
    self.assertNotIn(global_colour, colours)
    self.assertNotIn(palette.PURPLE, colours)
    # No glow: every pixel is either clear or fully opaque.
    alphas = {flame.get_at((x, y)).a
              for x in range(flame.get_width())
              for y in range(flame.get_height())}
    self.assertLessEqual(alphas, {0, palette.OPAQUE})

  def test_it_is_cached(self):
    self.assertIs(icons.flame(), icons.flame())


class BadgeTest(unittest.TestCase):
  """Flame and seconds over the head, away from the ball."""

  def test_the_badge_is_over_the_head(self):
    flame, text = badge(1)
    head_top = PLAYER["y"] - (SPEC.HEAD_OFFSET_Y + SPEC.HEAD_RADIUS)
    self.assertLessEqual(flame.bottom, head_top)
    self.assertEqual(text.centery, flame.centery)

  def test_the_ball_never_covers_flame_or_seconds(self):
    for side in (-1, 1):
      ball = ball_at(side)
      circle = pygame.Rect(ball["x"] - ball["r"],
                           ball["y"] - ball["r"],
                           2 * ball["r"], 2 * ball["r"])
      flame, text = badge(side)
      self.assertFalse(circle.colliderect(flame), side)
      self.assertFalse(circle.colliderect(text), side)

  def test_the_badge_changes_side_with_the_ball(self):
    left_ball, _ = badge(-1)     # ball on the left: badge on the right
    right_ball, _ = badge(1)     # ball on the right: badge on the left
    self.assertGreater(left_ball.left, PLAYER["x"])
    self.assertLess(right_ball.right, PLAYER["x"])

  def test_the_ball_in_the_middle_keeps_the_badge_on_the_right(self):
    flame, text = badge(0)
    self.assertGreater(flame.left, PLAYER["x"])
    self.assertGreater(text.left, flame.right)


class HudIconTest(unittest.TestCase):
  """The burn shows up in the HUD as a flame, not as a purple badge."""

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
    self.assertNotEqual(render.effect_color(self.SPEED),
                        palette.ORANGE)


if __name__ == "__main__":
  unittest.main()
