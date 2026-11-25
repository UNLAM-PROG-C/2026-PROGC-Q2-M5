"""The interface tells the simulation when the goal presentation is over.

The simulation keeps the match frozen from the goal until the party and the
replay are done (`config.MatchRules.GOAL_HOLD`); the screen has to ask for
that freeze when it starts the match and has to cut it when the player skips
the replay with S. These tests check just that, without a window.
"""
import types
import unittest

import driver  # sets the dummy SDL before pygame is imported

import helpers  # noqa: F401  pylint: disable=unused-import
from fdc import protocol
from fdc.ui import match_screens


class FakeLink:
  """Keeps the commands the screen sends (like the real link)."""

  def __init__(self):
    self.sent = []

  def send_command(self, ctype, **payload):
    self.sent.append((ctype, payload))
    return len(self.sent)


class FakePostFx:
  """Effects stand-in: `skip` says if something was on screen."""

  def __init__(self, playing=True):
    self.enabled = True
    self.playing = playing
    self.skips = 0

  def skip(self):
    self.skips += 1
    return self.playing


class FakeAudio:
  """Audio stand-in: it only has to accept the sounds."""

  def play(self, name):
    del name


def screen(postfx, seed=None):
  """MatchScreen with only what these hooks touch (no renderer)."""
  app = types.SimpleNamespace(postfx=postfx, link=FakeLink(),
                              audio=FakeAudio(),
                              options=types.SimpleNamespace(seed=seed))
  ms = object.__new__(match_screens.MatchScreen)
  ms.app = app
  ms.match_id = 4
  ms.chars = ["messi", "pele"]
  ms.expected_cid = {}
  return ms


class SkipCommandTest(unittest.TestCase):
  """The two commands of the frozen goal (F10)."""

  def test_s_tells_the_simulation_the_replay_is_over(self):
    # pylint: disable-next=protected-access
    ms = screen(FakePostFx(playing=True))
    # pylint: disable-next=protected-access
    self.assertTrue(ms._skip())
    self.assertEqual(ms.app.link.sent, [(protocol.CMD_SKIP_GOAL, {})])

  def test_s_without_a_replay_sends_nothing(self):
    # pylint: disable-next=protected-access
    ms = screen(FakePostFx(playing=False))
    # pylint: disable-next=protected-access
    self.assertFalse(ms._skip())
    self.assertEqual(ms.app.link.sent, [])

  def test_the_start_asks_for_the_presentation_when_there_are_effects(self):
    # pylint: disable-next=protected-access
    payload = screen(FakePostFx())._start_payload()
    self.assertTrue(payload["presentation"])

  def test_without_effects_the_start_does_not_ask_for_it(self):
    # pylint: disable-next=protected-access
    ms = screen(FakePostFx())
    ms.app.postfx.enabled = False
    # pylint: disable-next=protected-access
    self.assertFalse(ms._start_payload()["presentation"])


if __name__ == "__main__":
  unittest.main()
