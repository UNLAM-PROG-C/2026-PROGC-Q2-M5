"""Simulation inside the page (browser version) and the app in web mode.

In the browser there are no processes: InlineLink runs the SAME simulation
core as the desktop process, with the same protocol (commands with ACK,
control snapshots with counters, states with match and seq).
"""
import types
import unittest

import driver  # sets the dummy SDL before pygame is imported
import pygame

from fdc import config
from fdc import protocol
from fdc.sim import inline
from fdc.ui import app as game
from fdc.ui import match_screens
from fdc.ui import online_screens
from fdc.ui import screens
from fdc.ui import tournament_screens

FRAME = 1 / 60              # s per frame of the fake page
START_TIME = 100.0          # s: start of the fake clock
STALL = 5.0                 # s the page was frozen
EPSILON = 1e-9
MENU_WAIT = 10              # s to reach the menu
PLAY_WAIT = 8               # s until the match is in play
STEP_WAIT = 5               # s for the other conditions
MIN_MOVE = 40               # px a held key must move a player in 0.5 s
HOLD = 0.5                  # s a key is held
GOAL_TRIES = 40             # polls until the goal of the test counts
GOAL_STEP = 0.05            # s of each of those polls


class FakeClock:
  def __init__(self):
    self.t = START_TIME

  def __call__(self):
    return self.t


class InlineLinkTest(unittest.TestCase):
  def setUp(self):
    self.clock = FakeClock()
    self.link = inline.InlineLink(seed=3, clock=self.clock)
    self.link.start()

  def poll(self, seconds=0.0, frame=FRAME):
    """Moves the clock frame by frame and collects what comes back."""
    msgs, state = self.link.poll()
    left = seconds
    while left > EPSILON:
      self.clock.t += min(frame, left)
      left -= frame
      m, st = self.link.poll()
      msgs += m
      state = st or state
    return msgs, state

  def start_match(self):
    self.link.poll()
    cid = self.link.send_command(protocol.CMD_START, match=7,
                                 characters=["messi", "pele"])
    msgs, state = self.poll()
    ack = [m for m in msgs if m["type"] == protocol.EV_ACK]
    self.assertEqual((ack[0]["cid"], ack[0]["ok"]), (cid, True))
    self.assertEqual((state["match"], state["phase"]),
                     (7, protocol.PHASE_COUNTDOWN))
    _, state = self.poll(config.MatchRules.KICKOFF_COUNTDOWN + 0.1)
    self.assertEqual(state["phase"], protocol.PHASE_PLAYING)
    return state

  def test_ready_ack_states_and_controls(self):
    self.assertFalse(self.link.ready)
    self.link.poll()
    self.assertTrue(self.link.ready)       # READY, like the process
    st = self.start_match()
    x0, seq0 = st["players"][0]["x"], st["seq"]
    self.link.send_input([[False, True, 0, 0], [False, False, 0, 0]])
    _, st = self.poll(HOLD)
    # The simulation moved the player.
    self.assertGreater(st["players"][0]["x"], x0 + MIN_MOVE)
    self.assertGreater(st["seq"], seq0)
    self.check_jump()

  def check_jump(self):
    """One press of jump lifts the player."""
    self.link.send_input([[False, False, 1, 0], [False, False, 0, 0]])
    _, st = self.poll(0.1)
    self.assertFalse(st["players"][0]["ground"])

  def test_pause_freezes_clock_and_resume_counts_down(self):
    self.start_match()
    self.link.send_command(protocol.CMD_PAUSE,
                           reason=protocol.PAUSE_REASON_USER)
    _, st = self.poll()
    self.assertTrue(st["paused"])
    clock = st["clock"]
    self.poll(2.0)
    self.link.send_command(protocol.CMD_RESUME)
    _, st = self.poll()
    self.assertEqual(st["clock"], clock)    # paused, the clock stops
    self.assertEqual(st["phase"], protocol.PHASE_COUNTDOWN)

  def test_long_stall_is_not_recovered_all_at_once(self):
    st = self.start_match()
    tick = st["tick"]
    self.clock.t += STALL
    _, st = self.link.poll()
    self.assertLessEqual(st["tick"] - tick, config.MAX_CATCHUP_STEPS)

  def test_simulation_error_is_reported_not_raised(self):
    link = inline.InlineLink(test_mode=True, clock=self.clock)
    link.start()
    link.poll()
    link.send_command(protocol.CMD_START, match=1)
    link.poll()
    link.send_command(protocol.CMD_DEBUG_CRASH)
    link.poll()                         # it does not break the interface
    self.assertIn("Fallo provocado", link.check_health())
    link.restart()
    link.poll()
    self.assertIsNone(link.check_health())

  def test_states_are_the_same_shape_as_the_process(self):
    st = self.start_match()
    for key in ("match", "seq", "tick", "phase", "clock", "score",
                "players", "ball", "goals", "effects", "dropped_states"):
      self.assertIn(key, st)
    self.assertEqual(config.PHYSICS_DT, 1 / 120)

  # ------------------------------------------------- frozen goal (F10)
  def score_goal(self):
    """Puts the ball into the left goal and polls until it counts."""
    m = self.link.core.match       # pylint: disable=protected-access
    goal = m.goals[0]
    m.ball.x, m.ball.y = goal.mouth_x + 60, config.Arena.FLOOR_Y - 60
    m.ball.vx, m.ball.vy = -700, 0
    for _ in range(GOAL_TRIES):
      msgs, state = self.poll(GOAL_STEP)
      if state and state["phase"] == protocol.PHASE_GOAL:
        return msgs, state
    raise AssertionError("the ball never went in")

  def test_the_goal_is_frozen_for_the_party_and_the_replay(self):
    self.start_match()
    self.assertAlmostEqual(self.link.core.match.goal_hold,
                           config.MatchRules.GOAL_HOLD)
    _, st = self.score_goal()
    frozen = (st["players"], st["ball"], st["clock"], st["score"])
    _, later = self.poll(config.MatchRules.GOAL_REPLAY - 0.2)
    self.assertEqual(later["phase"], protocol.PHASE_GOAL)
    self.assertEqual((later["players"], later["ball"], later["clock"],
                      later["score"]), frozen)
    _, kickoff = self.poll(config.MatchRules.GOAL_REPLAY + 0.3)
    self.assertEqual(kickoff["phase"], protocol.PHASE_COUNTDOWN)

  def test_skipping_the_replay_comes_back_from_the_centre(self):
    self.start_match()
    self.score_goal()
    cid = self.link.send_command(protocol.CMD_SKIP_GOAL)
    msgs, st = self.poll()
    ack = [m for m in msgs if m["type"] == protocol.EV_ACK
           and m.get("cid") == cid]
    self.assertTrue(ack and ack[0]["ok"])
    self.assertEqual(st["phase"], protocol.PHASE_COUNTDOWN)
    self.assertEqual((st["ball"]["x"], st["ball"]["y"]),
                     tuple(map(float, config.BallSpec.SPAWN)))

  def test_without_the_effects_the_goal_is_held_only_for_the_party(self):
    self.link.poll()
    self.link.send_command(protocol.CMD_START, match=9,
                           characters=["messi", "pele"],
                           presentation=False)
    self.poll()
    self.assertAlmostEqual(self.link.core.match.goal_hold,
                           config.MatchRules.GOAL_CELEBRATION)


class WebAppTest(unittest.TestCase):
  """The app as in the browser: whole menu, tournament and local
    multiplayer without processes."""

  def setUp(self):
    opts = types.SimpleNamespace(
        web=True, test_mode=False, seed=4, no_audio=False,
        fullscreen=False, debug_panel=True, duration=None,
        server_url=driver.NO_SERVER,
        quality_mode="auto",      # the same as web/main.py
        profile_path=driver.profile_file("Web"))
    self.app = game.App(opts)
    self.d = driver.Driver(self.app)

  def tearDown(self):
    self.app.running = False
    self.app.shutdown()

  def wait_play(self, ms, what):
    self.d.until(lambda: ms.state is not None
                 and ms.state["phase"] == protocol.PHASE_PLAYING,
                 PLAY_WAIT, what)

  def test_full_game_without_processes(self):
    d = self.d
    self.assertIsInstance(self.app.link, inline.InlineLink)
    d.until(lambda: isinstance(d.screen(), screens.MenuScreen),
            MENU_WAIT, "menu")
    labels = [label for label, _ in d.screen().menu.items]
    # No quit button on the web.
    self.assertEqual(labels, ["Jugar", "Controles", "Poderes", "Opciones"])
    self.check_tournament()
    self.check_local()
    self.check_online_entry()

  def check_tournament(self):
    d = self.d
    d.tap(pygame.K_RETURN)
    self.assertIsInstance(d.screen(), screens.PlayMenuScreen)
    d.tap(pygame.K_RETURN)                       # tournament
    self.assertIsInstance(d.screen(), tournament_screens.PickScreen)
    d.tap(pygame.K_RETURN)
    self.assertIsInstance(d.screen(), tournament_screens.HubScreen)
    d.tap(pygame.K_RETURN)                       # play the stage
    d.until(lambda: isinstance(
        d.screen(), tournament_screens.TournamentMatchScreen),
            STEP_WAIT, "tournament match")
    self.check_tournament_match(d.screen())

  def check_tournament_match(self, ms):
    d = self.d
    self.wait_play(ms, "play")
    x0 = ms.state["players"][1]["x"]
    self.hold(pygame.K_LEFT)
    self.assertLess(ms.state["players"][1]["x"], x0 - MIN_MOVE)
    d.tap(pygame.K_ESCAPE)        # pause confirmed by the simulation
    d.until(lambda: ms.pause_state == "paused", 3, "pause")
    ms.abandon()                  # menu from the pause = quitting
    self.assertIsInstance(d.screen(), screens.MenuScreen)

  def check_local(self):
    d = self.d
    for key in (pygame.K_RETURN, pygame.K_s, pygame.K_RETURN):
      d.tap(key)                               # play -> multiplayer
    self.assertIsInstance(d.screen(), screens.MultiplayerMenuScreen)
    d.tap(pygame.K_RETURN)                       # local
    self.assertIsInstance(d.screen(), match_screens.SelectScreen)
    d.tap(pygame.K_SPACE)
    d.tap(pygame.K_p)
    d.until(lambda: isinstance(d.screen(), match_screens.MatchScreen),
            STEP_WAIT, "local match")
    self.check_local_match(d.screen())

  def check_local_match(self, ms):
    d = self.d
    self.wait_play(ms, "local play")
    x0, x1 = ms.state["players"][0]["x"], ms.state["players"][1]["x"]
    self.hold(pygame.K_d, pygame.K_LEFT)
    # Two people, one keyboard.
    self.assertGreater(ms.state["players"][0]["x"], x0 + MIN_MOVE)
    self.assertLess(ms.state["players"][1]["x"], x1 - MIN_MOVE)
    d.tap(pygame.K_ESCAPE)
    d.until(lambda: ms.pause_state == "paused", 3, "local pause")
    ms.to_menu()

  def hold(self, *keys):
    for key in keys:
      self.d.down(key)
    self.d.seconds(HOLD)
    for key in keys:
      self.d.up(key)

  def check_online_entry(self):
    d = self.d
    for key in (pygame.K_RETURN, pygame.K_s, pygame.K_RETURN, pygame.K_s,
                pygame.K_RETURN):
      d.tap(key)                               # play -> ... -> online
    self.assertIsInstance(d.screen(), online_screens.OnlineHomeScreen)
    self.assertTrue(d.screen().back_button.visible)
    d.tap(pygame.K_ESCAPE)
    self.assertIsInstance(d.screen(), screens.MultiplayerMenuScreen)


if __name__ == "__main__":
  unittest.main()
