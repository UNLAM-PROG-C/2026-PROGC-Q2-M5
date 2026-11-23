"""The blackout of the plain mode: one dark surface with holes of light."""
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
import pygame

from fdc import config
from fdc.ui import blackout

SIZE = (1280, 720)      # px: the default window
BRIGHT = (200, 200, 200)
BRIGHT_SUM = sum(BRIGHT)
DARK_SHARE = 0.3        # a darkened pixel keeps less than this of its light
DURATION = 6.0          # s of the test effect
LEFT = 3.0              # s left: past the fade-in, before the fade-out
PLAYERS = ({"x": 300.0, "y": 500.0}, {"x": 900.0, "y": 500.0})
BALL = {"x": 640.0, "y": 200.0, "r": 20.0}
FAR_FROM_LIGHTS = (640, 650)    # px: between the players, below the ball
FRAMES = 5
RULES = config.SimpleBlackout


def make_state(active=True, left=LEFT):
  effects = []
  if active:
    effects.append({"power": "blackout", "prop": "blackout", "target": "p0",
                    "left": left, "dur": DURATION})
  return {"players": [dict(p) for p in PLAYERS], "ball": dict(BALL),
          "effects": effects}


def head_of(player):
  return (int(player["x"]), int(player["y"] - config.Gpu.HEAD_ABOVE))


def bright_screen():
  screen = pygame.Surface(SIZE)
  screen.fill(BRIGHT)
  return screen


def light_of(screen, pos):
  return sum(screen.get_at(pos)[:3])


class SimpleBlackoutTest(unittest.TestCase):
  """Pixels outside the circles go dark and the ones inside stay lit."""

  def test_dark_outside_the_circles(self):
    screen = bright_screen()
    blackout.SimpleBlackout().draw(screen, make_state(), None)
    self.assertLess(light_of(screen, FAR_FROM_LIGHTS),
                    BRIGHT_SUM * DARK_SHARE)
    self.assertLess(light_of(screen, (0, 0)), BRIGHT_SUM * DARK_SHARE)

  def test_light_inside_every_player_circle(self):
    screen = bright_screen()
    blackout.SimpleBlackout().draw(screen, make_state(), None)
    for player in PLAYERS:
      self.assertEqual(light_of(screen, head_of(player)), BRIGHT_SUM)

  def test_light_around_the_ball(self):
    screen = bright_screen()
    blackout.SimpleBlackout().draw(screen, make_state(), None)
    self.assertEqual(light_of(screen, (int(BALL["x"]), int(BALL["y"]))),
                     BRIGHT_SUM)

  def test_single_viewer_only_sees_its_own_light(self):
    screen = bright_screen()
    blackout.SimpleBlackout().draw(screen, make_state(), 0)
    self.assertEqual(light_of(screen, head_of(PLAYERS[0])), BRIGHT_SUM)
    self.assertLess(light_of(screen, head_of(PLAYERS[1])),
                    BRIGHT_SUM * DARK_SHARE)

  def test_the_other_viewer_sees_no_blackout(self):
    screen = bright_screen()
    blackout.SimpleBlackout().draw(screen, make_state(), 1)
    self.assertEqual(light_of(screen, FAR_FROM_LIGHTS), BRIGHT_SUM)

  def test_without_the_effect_nothing_changes(self):
    screen = bright_screen()
    sample = SimpleBlackoutSpy()
    sample.draw(screen, make_state(active=False), None)
    self.assertEqual(light_of(screen, FAR_FROM_LIGHTS), BRIGHT_SUM)
    self.assertEqual(sample.builds, 0)

  def test_it_has_not_started_yet_at_the_first_instant(self):
    screen = bright_screen()
    blackout.SimpleBlackout().draw(screen, make_state(left=DURATION), None)
    self.assertEqual(light_of(screen, FAR_FROM_LIGHTS), BRIGHT_SUM)

  def test_the_surface_is_built_once_and_reused(self):
    strategy = blackout.SimpleBlackout()
    for _ in range(FRAMES):
      strategy.draw(bright_screen(), make_state(), None)
    self.assertEqual(strategy.builds, 1)
    first = strategy.veil
    strategy.draw(bright_screen(), make_state(), None)
    self.assertIs(strategy.veil, first)

  def test_the_surface_follows_a_new_window_size(self):
    strategy = blackout.SimpleBlackout()
    strategy.draw(bright_screen(), make_state(), None)
    small = pygame.Surface((SIZE[0] // 2, SIZE[1] // 2))
    strategy.draw(small, make_state(), None)
    self.assertEqual(strategy.builds, 2)

  def test_veil_is_translucent_not_black(self):
    screen = bright_screen()
    blackout.SimpleBlackout().draw(screen, make_state(), None)
    self.assertGreater(light_of(screen, FAR_FROM_LIGHTS), 0)
    self.assertEqual(RULES.CLEAR[-1], 0)

  def test_full_chain_strategy_leaves_the_frame_alone(self):
    screen = bright_screen()
    blackout.ChainBlackout().draw(screen, make_state(), None)
    self.assertEqual(light_of(screen, FAR_FROM_LIGHTS), BRIGHT_SUM)
    self.assertEqual(light_of(screen, head_of(PLAYERS[0])), BRIGHT_SUM)


class SimpleBlackoutSpy(blackout.SimpleBlackout):
  """The real strategy, only to read `builds` in a test."""


if __name__ == "__main__":
  unittest.main()
