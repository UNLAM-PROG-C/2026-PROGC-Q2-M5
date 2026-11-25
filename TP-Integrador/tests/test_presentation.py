"""Exercise presentation mode through the headless desktop driver."""
import math
import unittest

import driver
import pygame

import main
from fdc import config
from fdc import protocol
from fdc.gpu import replay
from fdc.gpu import quality
from fdc.sim import match
from fdc.ui import match_screens
from fdc.ui import presentation
from fdc.ui import screens


FULL_ONLY_KEYS = (pygame.K_3, pygame.K_6)  # replay and night
PLAIN_KEYS = (pygame.K_1, pygame.K_2, pygame.K_4, pygame.K_5)
FRAMES = 3               # frames drawn after a change
DARK_SHARE = 0.4         # a darkened pixel keeps less than this of its light
FIRST_X, STEP_X = 40, 40  # px: where the search for a free pixel starts
SPOT_Y = 600             # px: row of the pitch where that pixel is looked up
FAR = 230                # px: distance from every light to the free pixel
BLACKOUT_EFFECT = {"power": "blackout", "prop": "blackout", "target": "p0",
                   "left": 3.0, "dur": 6.0}


def brightness(surface, pos):
  return sum(surface.get_at(pos)[:3])


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
    drive = self.open_game("--presentation", "--calidad", "full")
    clock = set_clock(self.wait_for_play(drive))
    cases = ((pygame.K_4, "confusion"),)
    for key, effect in cases:
      self.check_effect(drive, clock, key, effect,
                        config.POWERS_BY_ID[effect].duration)
    self.check_effect(drive, clock, pygame.K_6, "night", 10.0)

  def test_full_only_keys_do_nothing_without_effects(self):
    drive = self.open_game("--presentation", "--calidad", "sin-efectos")
    screen = self.wait_for_play(drive)
    before = self.app.postfx.quality_mode
    for key in FULL_ONLY_KEYS:
      drive.down(key)
    drive.frames(FRAMES)
    self.assertEqual(self.app.postfx.quality_mode, before)
    self.assertFalse(self.app.postfx.enabled)
    self.assertFalse(screen.effects.left(presentation.NIGHT))
    self.assertFalse(screen.effects.left(presentation.REPLAY))
    self.assertEqual(screen._effect_status(), "Sin efectos activos")

  def test_legend_lists_only_the_available_keys(self):
    for key in FULL_ONLY_KEYS:
      self.assertNotIn(pygame.key.name(key), presentation.PLAIN_LEGEND)
      self.assertIn(pygame.key.name(key), presentation.LEGEND)
    for key in PLAIN_KEYS:
      self.assertIn(pygame.key.name(key), presentation.PLAIN_LEGEND)
    self.assertIn(presentation.CLEAR_LABEL, presentation.PLAIN_LEGEND)

  def test_confusion_works_without_effects(self):
    drive = self.open_game("--presentation", "--calidad", "sin-efectos")
    screen = self.wait_for_play(drive)
    drive.down(pygame.K_RIGHT)
    drive.down(pygame.K_4)
    self.assertFalse(self.app.postfx.enabled)
    self.assertEqual(screen.controls(True)[1][:2], [True, False])
    self.assertIn("Confusión", screen._effect_status())

  def test_leaving_full_drops_the_full_only_effects(self):
    drive = self.open_game("--presentation", "--calidad", "full")
    screen = self.wait_for_play(drive)
    for key in (pygame.K_6, pygame.K_4, pygame.K_5):
      drive.down(key)
    self.app.postfx.set_quality_mode(quality.OFF)
    drive.frames(FRAMES)
    self.assertFalse(screen.effects.left(presentation.NIGHT))
    self.assertTrue(screen.effects.left("blackout"))
    self.assertNotIn("Noche", screen._effect_status())
    self.assertFalse(self.app.postfx.night)

  def test_blackout_key_without_effects_darkens(self):
    drive = self.open_game("--presentation", "--calidad", "sin-efectos")
    screen = self.wait_for_play(drive)
    clock = set_clock(screen)
    duration = config.POWERS_BY_ID["blackout"].duration
    spot = self.dark_spot(screen.state)
    before = brightness(self.app.screen, spot)
    drive.down(pygame.K_5)
    self.assertEqual(screen.effects.left("blackout"), duration)
    clock.advance(duration / 2)
    drive.frames(FRAMES)
    self.assertLess(brightness(self.app.screen, spot), before * DARK_SHARE)
    self.assertFalse(self.app.postfx.enabled)
    self.check_light_back(drive, screen, clock, spot, before)

  def check_light_back(self, drive, screen, clock, spot, before):
    clock.advance(config.POWERS_BY_ID["blackout"].duration)
    drive.frames(FRAMES)
    self.assertEqual(screen.effects.left("blackout"), 0)
    self.assertGreater(brightness(self.app.screen, spot), before * DARK_SHARE)

  def test_blackout_in_a_plain_match(self):
    drive = self.open_game("--sin-efectos")
    drive.until(lambda: isinstance(drive.screen(), screens.MenuScreen))
    screen = match_screens.MatchScreen(
        self.app, config.Presentation.DEFAULT_CHARACTERS)
    self.app.switch(screen)
    drive.until(lambda: screen.state is not None)
    spot = self.dark_spot(screen.state)
    screen.draw_match(self.app.screen, screen.state, screen.state)
    before = brightness(self.app.screen, spot)
    state = dict(screen.state, effects=[BLACKOUT_EFFECT])
    screen.draw_match(self.app.screen, state, state)
    self.assertLess(brightness(self.app.screen, spot), before * DARK_SHARE)
    self.assertIs(self.app.blackout(), self.app.simple_blackout)

  def test_full_keeps_the_chain_and_no_veil(self):
    drive = self.open_game("--presentation", "--calidad", "full")
    screen = self.wait_for_play(drive)
    drive.down(pygame.K_5)
    drive.frames(FRAMES)
    self.assertTrue(self.app.postfx.enabled)
    self.assertIs(self.app.blackout(), self.app.chain_blackout)
    self.assertEqual(self.app.simple_blackout.builds, 0)
    self.assertIsNotNone(screen.state)

  def dark_spot(self, state):
    """A pixel of the pitch far from every player and from the ball."""
    lights = [(p["x"], p["y"] - config.Gpu.HEAD_ABOVE)
              for p in state["players"]]
    lights.append((state["ball"]["x"], state["ball"]["y"]))
    for x in range(FIRST_X, config.LOGICAL_WIDTH, STEP_X):
      if all(math.hypot(x - lx, SPOT_Y - ly) > FAR for lx, ly in lights):
        return (x, SPOT_Y)
    raise AssertionError("no free pixel on the pitch")

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

  def test_ice_key_freezes_rival_via_ipc_without_postfx(self):
    drive = self.open_game("--presentation", "--sin-efectos")
    screen = self.wait_for_play(drive)
    drive.down(pygame.K_1)
    drive.until(lambda: screen.state["players"][1]["frozen"])
    assert not screen.state["players"][0]["frozen"]
    assert screen.state["effects"][0]["dur"] == 6
    assert "Hielo: 6 s" in screen._effect_status()
    assert screen.postfx_state(screen.state) is screen.state
    assert not self.app.postfx.enabled

  def test_fire_key_ignites_ball_via_ipc(self):
    drive = self.open_game("--presentation", "--sin-efectos")
    screen = self.wait_for_play(drive)
    drive.down(pygame.K_2)
    drive.until(lambda: bool(screen.state["effects"]))
    assert screen.state["effects"][0]["dur"] == 10
    assert "Fuego: pelota encendida" in screen._effect_status()
    assert screen.postfx_state(screen.state) is screen.state

  def test_fire_burns_on_contact_with_countdown(self):
    drive = self.open_game("--presentation", "--sin-efectos")
    screen = self.wait_for_play(drive)
    drive.down(pygame.K_2)
    drive.down(pygame.K_d)
    drive.until(lambda: screen.state["players"][0]["burned"])
    name = screen.renderer.who(0)
    assert f"Fuego: {name} 6 s" in screen._effect_status()
    assert not screen.state["players"][1]["burned"]
    assert "pelota encendida" not in screen._effect_status()

  def test_replay_plays_in_full_with_the_history(self):
    drive = self.open_game("--presentation", "--calidad", "full")
    screen = self.wait_for_play(drive)
    clock = set_clock(screen)
    duration = config.Presentation.REPLAY_DURATION
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
    drive = self.open_game("--presentation", "--calidad", "full")
    screen = self.wait_for_play(drive)
    for key in (pygame.K_6, pygame.K_4, pygame.K_3):
      drive.down(key)
    self.assertTrue(self.app.postfx.enabled)
    drive.down(pygame.K_0)
    self.assertFalse(self.app.postfx.night)
    self.assertIsNone(self.app.postfx.replay_mode())
    self.assertEqual(screen._effect_status(), "Sin efectos activos")
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

  def test_untimed_match_expires_active_powers_without_pickups(self):
    game = match.Match(1, seed=7, untimed=True)
    game.phase = protocol.PHASE_PLAYING
    dt = config.PHYSICS_DT
    game.debug_power("freeze_rival", "p0", seconds=dt)
    game.debug_power("fire", "p0", seconds=dt)
    assert game.players[1].frozen
    events = game.step(dt)
    assert not game.players[1].frozen
    assert not game.powers.effects and game.powers.pickup is None
    assert sum(kind == protocol.EV_POWER_EXPIRED for kind, _ in events) == 2


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
