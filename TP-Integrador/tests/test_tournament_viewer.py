"""The effects of the post-processing follow the person in the tournament."""
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc import tournament
from fdc.gpu import effects_state
from fdc.ui import tournament_screens

FULL_LEFT = 5.5         # s left of the power: full strength
DURATION = 6.0          # s of the power
PLAYERS = tuple({"x": 200.0 + 600.0 * slot, "y": 600.0, "scale": 1.0,
                 "frozen": True} for slot in (0, 1))


def effect(prop, slot):
  """One power of the state, on the player of `slot`."""
  return {"power": prop, "prop": prop, "target": f"p{slot}",
          "left": FULL_LEFT, "dur": DURATION}


def frame(prop, slot):
  return {"players": PLAYERS, "effects": [effect(prop, slot)],
          "ball": {"x": 640.0, "y": 400.0}}


class TournamentViewerTest(unittest.TestCase):
  """The person plays the right side: the screen is hers (1.0.9)."""
  VIEWER = tournament_screens.TournamentMatchScreen.VIEWER

  def test_the_screen_is_the_one_of_the_person(self):
    self.assertEqual(self.VIEWER, tournament.HUMAN_SLOT)

  def test_the_person_sees_the_ice_that_hits_her(self):
    fx = effects_state.derive(frame("frozen", tournament.HUMAN_SLOT),
                              self.VIEWER)
    self.assertGreater(fx.ice, 0.0)

  def test_the_person_does_not_see_the_ice_of_the_bot(self):
    fx = effects_state.derive(frame("frozen", tournament.BOT_SLOT),
                              self.VIEWER)
    self.assertEqual(fx.ice, 0.0)

  def test_the_person_is_twisted_when_the_bot_confuses_her(self):
    fx = effects_state.derive(frame("confusion", tournament.HUMAN_SLOT),
                              self.VIEWER)
    self.assertGreater(fx.confusion, 0.0)


if __name__ == "__main__":
  unittest.main()
