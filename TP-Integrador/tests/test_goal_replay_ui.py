"""The screen draws the replay the simulation announced, in any mode.

In an online match the simulation decides: it holds the goal for the party and
then for the replay and it says when the window opens. The screen only has to
draw that window with what it has (the effects of FULL or a plain replay) and
never let the replay leak into the live match, however slow the machine is.
"""
import types
import unittest

import driver  # sets the dummy SDL before pygame is imported
import pygame

import helpers  # noqa: F401  pylint: disable=unused-import
from fdc import config
from fdc import protocol
from fdc.gpu import replay
from fdc.ui import match_screens
from fdc.ui import online_screens

RULES = config.MatchRules
STEPS = 90          # saved states of the fake match
STEP = 0.04         # s between them
GOAL_T = STEPS * STEP
WIDTH, HEIGHT = 1280, 720


class FakePostFx:
  """Effects stand-in: with or without them, and what it reports."""

  def __init__(self, effects=True):
    self.enabled = effects
    self.can_replay = effects
    self.started = self.ended = self.drives = 0
    self.progress = None

  def start_goal_replay(self):
    self.started += 1
    return self.can_replay

  def drive_replay(self, progress):
    self.drives += 1
    self.progress = progress

  def end_goal_replay(self):
    self.ended += 1

  def view_state(self, st):
    del st      # the effects draw their own frame
    return {"from_effects": True, "ball": {"x": -1.0, "y": -1.0},
            "players": []}

  def replay_mode(self):
    return replay.REPLAY_KIND if self.can_replay else None

  def begin(self, surf, st):
    del st      # the chain draws over the screen
    return surf

  def finish(self, surf, dt):
    del surf, dt


class FakeRenderer:
  """Renderer stand-in: it keeps the world it was asked to draw."""

  def __init__(self):
    self.view = None
    self.hud = 0

  def draw_world(self, world, view, off):
    del world, off
    self.view = view

  def draw_hud(self, surf, st):
    del surf, st
    self.hud += 1

  def draw_center_messages(self, surf, st):
    del surf, st


class FakeFx:
  """Particles stand-in: nothing to draw here."""

  def shake_offset(self):
    return (0, 0)

  def draw(self, world, off):
    del world, off


def state(step):
  """State of the fake match: the ball crossing the field."""
  return {"phase": protocol.PHASE_PLAYING, "phase_left": 0.0,
          "ball": {"x": 100.0 + step * 10.0, "y": 600.0},
          "players": [{"x": step * 2.0, "y": 600.0},
                      {"x": 900.0 - step, "y": 600.0}]}


def goal_state(left):
  """State of the frozen goal with that much time left."""
  return {"phase": protocol.PHASE_GOAL, "phase_left": left,
          "ball": {"x": 90.0, "y": 600.0},
          "players": [{"x": 900.0, "y": 600.0},
                      {"x": 980.0, "y": 600.0}]}


def history():
  """Saved states of the last seconds of the fake match."""
  saved = replay.StateHistory()
  for k in range(STEPS):
    saved.feed(state(k), k * STEP)
  return saved


def screen(postfx, cls=match_screens.MatchScreen):
  """Screen with only what the replay needs (no window, no audio)."""
  app = types.SimpleNamespace(postfx=postfx, last_dt=1 / 60.0, fx=FakeFx())
  ms = object.__new__(cls)
  ms.app = app
  ms.renderer = FakeRenderer()
  ms.t = GOAL_T
  ms._init_replay()
  ms.replay_history = history()
  ms.goal_t = GOAL_T
  ms.toasts = []
  return ms


class ReplayWindowScreenTest(unittest.TestCase):
  """The window is the one the simulation announced, not the screen's."""

  def test_window_opens_with_the_event_and_closes_with_the_goal(self):
    ms = screen(FakePostFx())
    self.assertIsNone(ms.goal_window(goal_state(RULES.GOAL_HOLD)))
    ms._goal_replay({"seconds": RULES.GOAL_REPLAY})
    start = ms.goal_window(goal_state(RULES.GOAL_REPLAY))
    self.assertAlmostEqual(start[0], 0.0)          # progress
    self.assertAlmostEqual(start[1], RULES.GOAL_REPLAY)
    half = ms.goal_window(goal_state(RULES.GOAL_REPLAY / 2))
    self.assertAlmostEqual(half[0], 0.5, places=2)
    self.assertIsNone(ms.goal_window(goal_state(0.0)))
    live = dict(goal_state(1.0), phase=protocol.PHASE_PLAYING)
    self.assertIsNone(ms.goal_window(live))        # back to the match

  def test_without_the_event_there_is_no_window(self):
    ms = screen(FakePostFx())
    self.assertIsNone(ms.goal_window(goal_state(RULES.GOAL_REPLAY)))

  def test_online_does_not_let_the_player_skip_the_replay(self):
    local = screen(FakePostFx())
    online = screen(FakePostFx(), online_screens.OnlineMatchScreen)
    self.assertIn("S:", local._replay_note(RULES.GOAL_REPLAY))
    self.assertNotIn("S:", online._replay_note(RULES.GOAL_REPLAY))
    self.assertIn("3 s", online._replay_note(RULES.GOAL_REPLAY))
    self.assertFalse(online_screens.OnlineMatchScreen.REPLAY_CAN_SKIP)


class ReplayDrawingTest(unittest.TestCase):
  """What is drawn inside the window, with and without the effects."""

  def test_without_effects_the_plain_replay_shows_the_past(self):
    postfx = FakePostFx(effects=False)
    ms = screen(postfx)
    ms._goal_replay({"seconds": RULES.GOAL_REPLAY})
    self.assertIsNotNone(ms.plain)
    live = state(STEPS - 1)
    first = ms._replay_view(live, live, (0.0, RULES.GOAL_REPLAY))
    last = ms._replay_view(live, live, (1.0, 0.0))
    self.assertLess(first["ball"]["x"], last["ball"]["x"])
    self.assertLess(last["ball"]["x"], live["ball"]["x"])

  def test_without_effects_and_without_history_the_match_is_drawn(self):
    postfx = FakePostFx(effects=False)
    ms = screen(postfx)
    ms.replay_history = replay.StateHistory()      # nothing saved
    ms._goal_replay({"seconds": RULES.GOAL_REPLAY})
    self.assertIsNone(ms.plain)
    live = state(5)
    self.assertIs(ms._replay_view(live, live, (0.1, 2.0)), live)

  def test_with_effects_the_frame_comes_from_the_chain(self):
    postfx = FakePostFx(effects=True)
    ms = screen(postfx)
    ms._goal_replay({"seconds": RULES.GOAL_REPLAY})
    self.assertIsNone(ms.plain)     # the chain draws it, not a plain clip
    live = state(STEPS - 1)
    view = ms._replay_view(live, live, (0.25, 2.25))
    self.assertTrue(view.get("from_effects"))
    self.assertAlmostEqual(postfx.progress, 0.25)
    self.assertEqual(postfx.started, 1)

  def test_when_the_window_ends_the_replay_is_closed(self):
    postfx = FakePostFx(effects=True)
    ms = screen(postfx)
    ms._goal_replay({"seconds": RULES.GOAL_REPLAY})
    live = state(1)
    self.assertIs(ms._replay_view(live, live, None), live)
    self.assertEqual(postfx.ended, 1)

  def test_without_the_event_the_clip_is_not_cut(self):
    postfx = FakePostFx(effects=True)
    ms = screen(postfx)
    ms._goal_replay({"seconds": RULES.GOAL_REPLAY})
    live = state(1)
    ms._replay_view(live, live, None)      # the window just closed
    self.assertEqual(postfx.ended, 1)
    ms.replay_seconds = None                # no window: an older server
    ms._replay_view(live, live, None)
    self.assertEqual(postfx.ended, 1)       # its own clip is left alone

  def test_online_draws_the_replay_and_not_the_live_match(self):
    postfx = FakePostFx(effects=False)
    ms = screen(postfx, online_screens.OnlineMatchScreen)
    ms._goal_replay({"seconds": RULES.GOAL_REPLAY})
    live = state(STEPS - 1)
    surf = pygame.Surface((WIDTH, HEIGHT))
    pygame.init()
    ms.draw_match(surf, live, goal_state(RULES.GOAL_REPLAY / 2))
    self.assertLess(ms.renderer.view["ball"]["x"], live["ball"]["x"])
    self.assertEqual(ms.renderer.hud, 1)     # the scoreboard is still on


if __name__ == "__main__":
  unittest.main()
