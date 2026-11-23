"""Exercise presentation mode through the headless desktop driver."""
import math
import unittest

import driver
import pygame

import main
from fdc import config
from fdc import protocol
from fdc.gpu import replay
from fdc.sim import match
from fdc.ui import match_screens
from fdc.ui import presentation
from fdc.ui import screens


class PresentationTest(unittest.TestCase):
  """Use the real simulation process and CPU renderer."""

  def open_game(self, *args):
    options = main.parse_args(["--backend", "cpu", "--no-audio", *args])
    main.apply_gpu_options(options)
    options.profile_path = driver.profile_file()
    options.duration = config.PHYSICS_DT
    self.app = driver._TestApp(options)  # pylint: disable=protected-access
    self.addCleanup(self.app.shutdown)
    return driver.Driver(self.app)

  def wait_for_play(self, drive):
    def playing():
      state = getattr(drive.screen(), "state", None)
      return state and state["phase"] == protocol.PHASE_PLAYING
    drive.until(playing)
    return drive.screen()

  def test_cli_starts_untimed_local_match(self):
    drive = self.open_game("--presentation")
    screen = self.wait_for_play(drive)
    start = screen.state["tick"]
    drive.until(lambda: screen.state["tick"] > start)
    self.assertIsNone(self.app.net)
    self.assertIsNone(screen.state["clock"])
    self.assertEqual(len(screen.state["players"]), len(config.PLAYER_KEYS))

  def test_menu_starts_presentation(self):
    drive = self.open_game()
    drive.until(lambda: isinstance(drive.screen(), screens.MenuScreen))
    menu = drive.screen().menu
    idx = [label for label, _ in menu.items].index("Presentación")
    drive.post(pygame.MOUSEBUTTONDOWN, pos=menu.rects()[idx].center,
               button=pygame.BUTTON_LEFT)
    screen = self.wait_for_play(drive)
    self.assertIsInstance(screen, presentation.PresentationScreen)
    self.assertIsNone(screen.state["clock"])
    screen.to_menu()
    drive.until(lambda: isinstance(drive.screen(), screens.MenuScreen))

  def test_effect_keys_refresh_and_expire_on_cpu(self):
    drive = self.open_game("--presentation", "--calidad", "sin-efectos")
    clock = set_clock(self.wait_for_play(drive))
    cases = ((pygame.K_1, "freeze_rival"), (pygame.K_2, "fire"),
             (pygame.K_4, "confusion"), (pygame.K_5, "blackout"))
    for key, effect in cases:
      self.check_effect(drive, clock, key, effect,
                        config.POWERS_BY_ID[effect].duration)
    self.check_effect(drive, clock, pygame.K_6, "night", 10.0)

  def check_effect(self, drive, clock, key, effect, duration):
    screen = drive.screen()
    drive.down(key)
    self.assertEqual(self.app.postfx.mode, "cpu")
    self.assertEqual(screen.effects.left(effect), duration)
    clock.advance(duration / 2)
    drive.frames()
    self.assertNotEqual(self.app.postfx.active_effects(), "ninguno")
    drive.down(key)
    self.assertEqual(screen.effects.left(effect), duration)
    clock.advance(duration)
    drive.frames()
    self.assertEqual(screen.effects.left(effect), 0)
    self.assertEqual(self.app.postfx.active_effects(), "ninguno")

  def test_replay_has_history_even_when_quality_starts_off(self):
    drive = self.open_game("--presentation", "--calidad", "sin-efectos")
    screen = self.wait_for_play(drive)
    clock = set_clock(screen)
    duration = config.MatchRules.GOAL_REPLAY
    drive.down(pygame.K_3)
    self.assertEqual(self.app.postfx.replay_mode(), replay.REPLAY_KIND)
    self.assertEqual(screen.effects.left("replay"), duration)
    clock.advance(duration / 2)
    drive.down(pygame.K_3)
    self.assertEqual(screen.effects.left("replay"), duration)
    clock.advance(duration)
    drive.frames()
    self.assertIsNone(self.app.postfx.replay_mode())

  def test_zero_cancels_effects_without_losing_the_replay_buffer(self):
    drive = self.open_game("--presentation", "--sin-efectos")
    screen = self.wait_for_play(drive)
    drive.down(pygame.K_0)
    self.assertFalse(self.app.postfx.enabled)
    for key in (pygame.K_6, pygame.K_4, pygame.K_3):
      drive.down(key)
    self.assertTrue(self.app.postfx.enabled)
    drive.down(pygame.K_0)
    self.assertFalse(self.app.postfx.night)
    self.assertIsNone(self.app.postfx.replay_mode())
    self.assertEqual(screen.effects.status(), "Sin efectos activos")
    drive.down(pygame.K_3)
    self.assertEqual(self.app.postfx.replay_mode(), replay.REPLAY_KIND)

  def test_only_player_two_has_reversed_horizontal_controls(self):
    drive = self.open_game("--presentation")
    screen = self.wait_for_play(drive)
    drive.down(pygame.K_d)
    drive.down(pygame.K_RIGHT)
    normal = screen.controls(True)
    drive.down(pygame.K_4)
    changed = screen.controls(True)
    self.assertEqual(changed[0], normal[0])
    self.assertEqual(changed[1][:2], [True, False])
    self.assertEqual(changed[1][2:], normal[1][2:])
    drive.down(pygame.K_0)
    self.assertEqual(screen.controls(True), normal)

  def test_digits_do_not_enable_effects_in_an_ordinary_match(self):
    drive = self.open_game("--calidad", "sin-efectos")
    drive.until(lambda: isinstance(drive.screen(), screens.MenuScreen))
    self.app.switch(match_screens.MatchScreen(
        self.app, config.Presentation.DEFAULT_CHARACTERS))
    for key in (presentation.OFF_KEY, *presentation.SHORTCUTS):
      drive.down(key)
    self.assertFalse(self.app.postfx.enabled)
    self.assertFalse(self.app.postfx.night)
    self.assertIsNone(self.app.postfx.replay_mode())

  def test_number_keys_are_not_player_controls(self):
    drive = self.open_game()
    self.assertTrue(self.app.input.keymap.keys().isdisjoint(
        (presentation.OFF_KEY, *presentation.SHORTCUTS)))
    self.assertIsInstance(drive.screen(), screens.BootScreen)

  def test_night_toggle_is_only_disabled_in_presentation(self):
    drive = self.open_game("--presentation")
    self.wait_for_play(drive)
    drive.down(pygame.K_n)
    self.assertFalse(self.app.postfx.night)
    drive.screen().to_menu()
    drive.until(lambda: isinstance(drive.screen(), screens.MenuScreen))
    self.app.switch(match_screens.MatchScreen(
        self.app, config.Presentation.DEFAULT_CHARACTERS))
    drive.down(pygame.K_n)
    self.assertTrue(self.app.postfx.night)

  def test_no_pickups_spawn_after_the_ordinary_clock_would_end(self):
    game = match.Match(1, duration=config.PHYSICS_DT, untimed=True)
    game.phase = protocol.PHASE_PLAYING
    horizon = config.MatchRules.DURATION + config.PowerRules.SPAWN_MAX
    for _ in range(math.ceil(horizon / config.PHYSICS_DT)):
      events = game.step(config.PHYSICS_DT)
      self.assertNotIn(protocol.EV_POWER_SPAWN, [kind for kind, _ in events])
    self.assertEqual(game.phase, protocol.PHASE_PLAYING)
    self.assertIsNone(game.powers.pickup)


class FakeClock:
  """Advance deadlines without waiting through entire effects."""

  def __init__(self):
    self.seconds = 0.0

  def now(self):
    return self.seconds

  def advance(self, dt):
    self.seconds += dt


def set_clock(screen):
  clock = FakeClock()
  screen.effects.now = clock.now
  return clock
