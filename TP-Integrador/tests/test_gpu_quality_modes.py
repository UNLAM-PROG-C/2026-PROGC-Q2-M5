"""Desktop quality modes: flags, defaults and rendering."""
import types
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
import pygame

import driver
import main as main_module
from fdc import config
from fdc.gpu import cpu_ref
from fdc.gpu import postfx
from fdc.gpu import quality
from fdc.ui import screens

W, H = 64, 48           # size of the test surface
FRAMES = 6              # frames of the chain in each test
DT = 1 / 60.0           # s between frames
FULL = quality.FULL
OFF = quality.OFF


def options(**extra):
  """The attributes the interface reads from the command line."""
  base = {"no_gpu": False, "web": False,
          "quality_mode": FULL}
  base.update(extra)
  return types.SimpleNamespace(**base)


def start_on_cpu(mode):
  pygame.display.init()
  pygame.display.set_mode((W, H))
  fx = postfx.PostFx(options(quality_mode=mode, force_cpu=True), (W, H))
  fx.start()
  return fx


class ModesTest(unittest.TestCase):
  """The two quality modes and their display names."""

  def test_two_modes(self):
    self.assertEqual(config.Gpu.MODES, (FULL, OFF))
    self.assertEqual(quality.DEFAULT_MODE, FULL)

  def test_cycle_order(self):
    self.assertEqual(quality.next_mode(FULL), OFF)
    self.assertEqual(quality.next_mode(OFF), FULL)

  def test_names_of_the_overlay(self):
    self.assertEqual(quality.name_of(FULL), "FULL")
    self.assertEqual(quality.name_of(OFF), "SIN EFECTOS")

  def test_off_aliases(self):
    self.assertEqual(quality.mode_of("off"), OFF)
    self.assertEqual(quality.mode_of("sin efectos"), OFF)
    self.assertEqual(quality.mode_of("sin-efectos"), OFF)

  def test_unknown_mode_falls_back_to_full(self):
    self.assertEqual(quality.mode_of("otro"), FULL)
    self.assertEqual(quality.mode_of(None), FULL)


class OffTest(unittest.TestCase):
  """The "SIN EFECTOS" mode: no chain at all, the plain pygame render."""

  def setUp(self):
    pygame.init()
    pygame.display.set_mode((W, H))
    self.fx = postfx.PostFx(options(quality_mode=OFF), (W, H))

  def test_chain_is_off_from_the_start(self):
    self.assertFalse(self.fx.enabled)
    self.assertIsNone(self.fx.ops)
    self.assertEqual(self.fx.summary()["mode"], "off")
    self.assertEqual(self.fx.summary()["quality_name"], "SIN EFECTOS")

  def test_begin_hands_the_plain_screen(self):
    screen = pygame.Surface((W, H))
    self.assertIs(self.fx.begin(screen, {}), screen)
    self.fx.finish(screen, DT)          # must not touch anything

  def test_off_has_no_crowd_and_no_punch(self):
    self.assertFalse(self.fx.standing_crowd())
    self.assertEqual(self.fx.punch(), 0.0)

  def test_switching_back_turns_the_chain_on(self):
    self.fx.set_quality_mode(FULL)
    self.assertTrue(self.fx.enabled)
    self.fx.set_quality_mode(OFF)
    self.assertFalse(self.fx.enabled)

  def test_turning_off_cancels_a_replay(self):
    self.fx.set_quality_mode(FULL)
    self.fx.history.feed({"ball": {}}, 0.0)
    self.assertTrue(self.fx.begin_replay())
    self.fx.set_quality_mode(OFF)
    self.assertIsNone(self.fx.replay_mode())

  def test_no_gpu_stays_off_even_in_full(self):
    fx = postfx.PostFx(options(no_gpu=True, quality_mode=FULL), (W, H))
    fx.set_quality_mode(FULL)
    self.assertFalse(fx.enabled)


class FullTest(unittest.TestCase):
  """FULL draws everything and never lowers the quality by itself."""

  def setUp(self):
    pygame.init()
    pygame.display.set_mode((W, H))
    self.fx = postfx.PostFx(options(quality_mode=FULL), (W, H))
    self.fx.ops = cpu_ref.Cpu()
    self.fx.enabled = True
    self.fx.mode = "cpu"

  def run_chain(self, frames=FRAMES):
    """Frames of the chain over an empty screen."""
    screen = pygame.Surface((W, H))
    for _ in range(frames):
      target = self.fx.begin(screen, {})
      target.fill((20, 30, 40))
      self.fx.finish(screen, DT)
    return screen

  def test_full_renders_at_full_resolution(self):
    self.run_chain()
    self.assertEqual(self.fx.summary()["quality"], "alta")
    self.assertEqual(self.fx.quality_label(), "Q0")
    self.assertEqual(self.fx.processed_size, (W, H))
    self.assertTrue(self.fx.full_quality())

  def test_full_draws_the_heavy_stages(self):
    self.run_chain()
    data = self.fx.summary()
    for stage in ("glow", "lights", "heat", "histogram", "particles"):
      self.assertIn(stage, data)
    self.assertEqual(data["quality_name"], "FULL")

  def test_full_draws_the_crowd(self):
    self.assertTrue(self.fx.standing_crowd())

  def test_full_has_the_extra_strength(self):
    self.assertEqual(self.fx.punch(), config.Gpu.FULL_PUNCH)
    self.assertGreater(self.fx.punch(), 1.0)


class SwitchTest(unittest.TestCase):
  """The F10 key and the options menu move between the two modes."""

  def setUp(self):
    pygame.init()
    pygame.display.set_mode((W, H))
    self.fx = postfx.PostFx(options(), (W, H))
    self.fx.ops = cpu_ref.Cpu()
    self.fx.enabled = True
    self.fx.mode = "cpu"

  def test_f10_cycles_the_modes(self):
    self.assertEqual(self.fx.quality_mode_name(), "FULL")
    self.fx.cycle_quality_mode()
    self.assertEqual(self.fx.quality_mode, OFF)
    self.fx.cycle_quality_mode()
    self.assertEqual(self.fx.quality_mode, FULL)


class QualityControlsTest(unittest.TestCase):
  def setUp(self):
    self.app = driver.make_app(quality_mode=OFF)
    self.addCleanup(self.app.shutdown)
    self.menu = screens.OptionsScreen(self.app)
    self.app.switch(self.menu)

  def test_f10_announces_the_new_mode(self):
    self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F10))
    self.assertEqual(self.app.postfx.quality_mode, FULL)
    self.assertIn("FULL", self.app.quality_controls.notice())

  def test_menu_announces_the_new_mode(self):
    self.menu.cycle()
    self.assertEqual(self.app.postfx.quality_mode, FULL)
    self.assertIn("FULL", self.app.quality_controls.notice())

  def test_f1_toggles_help(self):
    keydown = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1)
    self.app.handle_event(keydown)
    self.assertTrue(self.app.quality_controls.show_help)
    self.app.handle_event(keydown)
    self.assertFalse(self.app.quality_controls.show_help)


class CliTest(unittest.TestCase):
  """`--calidad` chooses the mode (F10 also does it inside a match)."""

  def test_rejects_invalid_quality_modes(self):
    for value in ("auto", "unknown"):
      with self.subTest(value=value):
        with self.assertRaises(SystemExit) as error:
          main_module.parse_args(["--calidad", value])
        self.assertEqual(error.exception.code, 2)

  def test_flag_sets_the_mode(self):
    options = main_module.parse_args(["--no-audio", "--calidad",
                                      "full"])
    self.assertEqual(options.quality_mode, "full")

  def test_no_effects_flag(self):
    for value in ("sin-efectos", "off"):
      options = main_module.parse_args(["--no-audio", "--calidad",
                                        value])
      self.assertEqual(quality.mode_of(options.quality_mode), OFF)

  def test_the_default_mode_follows_the_backend(self):
    """1.0.2: no --calidad means "decide it with the backend"."""
    options = main_module.parse_args(["--no-audio"])
    self.assertIsNone(options.quality_mode)


class DefaultByBackendTest(unittest.TestCase):
  """1.0.2: on the CPU the game starts without effects; on the GPU it keeps
    starting in FULL. A mode chosen by the player (flag, F10, menu) wins."""

  def chain(self, mode):
    return start_on_cpu(mode)

  def test_the_cpu_without_a_choice_starts_without_effects(self):
    fx = self.chain(None)
    self.assertFalse(fx.chosen_mode)
    self.assertEqual(fx.mode, quality.CPU)
    self.assertEqual(fx.quality_mode, OFF)
    self.assertFalse(fx.enabled)
    self.assertEqual(fx.quality_mode_name(), "SIN EFECTOS")

  def test_the_gpu_without_a_choice_starts_full(self):
    self.assertEqual(quality.default_for(quality.GPU_BACKEND), FULL)
    self.assertEqual(quality.default_for(quality.CPU), OFF)
    fx = self.chain(None)
    fx.mode = quality.GPU_BACKEND
    # pylint: disable-next=protected-access
    fx._apply_default_mode()
    self.assertEqual(fx.quality_mode, FULL)
    self.assertTrue(fx.enabled)

  def test_a_chosen_mode_wins(self):
    fx = self.chain(FULL)
    self.assertTrue(fx.chosen_mode)
    self.assertEqual((fx.quality_mode, fx.enabled), (FULL, True))

  def test_a_chosen_mode_works_on_forced_cpu(self):
    """FULL can still be asked for with the numpy backend."""
    fx = self.chain(FULL)
    self.assertEqual(fx.mode, quality.CPU)
    self.assertEqual(fx.quality_mode, FULL)

  def test_f10_and_the_menu_count_as_a_choice(self):
    """Cycling the mode with F10 marks it as chosen, not as the default."""
    fx = self.chain(None)
    fx.cycle_quality_mode()
    self.assertTrue(fx.chosen_mode)
    self.assertTrue(fx.enabled)


class EmberTest(unittest.TestCase):
  """1.0.2: FULL throws a few embers over the burnt player, and the other
    modes leave them out (there the pygame render shows the burn)."""

  def chain(self, mode):
    return start_on_cpu(mode)

  def live(self, fx):
    """Sparks alive in the pool of the chain."""
    return int((fx.particles.life > 0.0).sum())

  def test_full_spawns_embers_over_the_burnt_player(self):
    fx = self.chain(FULL)
    fx.fx.burned = ((10.0, 20.0),)
    for _ in range(3):
      # pylint: disable-next=protected-access
      fx._spawn_embers(postfx.EMBER_EVERY)
    self.assertEqual(self.live(fx), 3 * postfx.EMBER_COUNT)

  def test_without_a_burnt_player_there_are_no_embers(self):
    fx = self.chain(FULL)
    # pylint: disable-next=protected-access
    fx._spawn_embers(postfx.EMBER_EVERY * 3)
    self.assertEqual(self.live(fx), 0)

  def test_off_leaves_the_embers_out(self):
    fx = self.chain(OFF)
    fx.fx.burned = ((10.0, 20.0),)
    # pylint: disable-next=protected-access
    fx._spawn_embers(postfx.EMBER_EVERY)
    self.assertEqual(self.live(fx), 0)


if __name__ == "__main__":
  unittest.main()
