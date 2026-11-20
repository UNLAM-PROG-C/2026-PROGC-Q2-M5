"""The quality modes of F11: FULL, OPTIMIZADO, "SIN EFECTOS" and AUTO.

The demo of the defence needs explicit modes: FULL draws everything at
full resolution and never lowers the quality by itself (it may stutter on a
notebook without NVIDIA), OPTIMIZADO leaves only the cheap stage and runs
smooth on the CPU, "SIN EFECTOS" draws the plain pygame render (the CPU/Mac
case) and AUTO is the adaptive governor of F7.
"""
import types
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
import pygame

import main as main_module
from fdc import config
from fdc.gpu import cpu_ref
from fdc.gpu import postfx
from fdc.gpu import quality

W, H = 64, 48           # size of the test surface
FRAMES = 6              # frames of the chain in each test
DT = 1 / 60.0           # s between frames
SLOW = 900.0            # ms: a frame that would push any governor down
HEAVY = (quality.GLOW, quality.LIGHTS, quality.HEAT, quality.TRAIL,
         quality.HISTOGRAM)
OPTIMIZED_ONLY = (quality.PARTICLES,)   # the only stage of OPTIMIZADO
FULL = quality.FULL
OPTIMIZED = quality.OPTIMIZED
OFF = quality.OFF
AUTO = quality.AUTO


def options(**extra):
  """The attributes the interface reads from the command line."""
  base = {"no_gpu": False, "gpu_quality": "media", "web": False,
          "quality_mode": FULL}
  base.update(extra)
  return types.SimpleNamespace(**base)


class ModesTest(unittest.TestCase):
  """The four modes of the card and FULL as the default."""

  def test_four_modes(self):
    self.assertEqual(config.Gpu.MODES, (FULL, OPTIMIZED, OFF, AUTO))
    self.assertEqual(quality.DEFAULT_MODE, FULL)
    self.assertEqual(config.Gpu.QUALITY_MODE, FULL)

  def test_cycle_order(self):
    self.assertEqual(quality.next_mode(FULL), OPTIMIZED)
    self.assertEqual(quality.next_mode(OPTIMIZED), OFF)
    self.assertEqual(quality.next_mode(OFF), AUTO)
    self.assertEqual(quality.next_mode(AUTO), FULL)

  def test_names_of_the_overlay(self):
    self.assertEqual(quality.name_of(FULL), "FULL")
    self.assertEqual(quality.name_of(OPTIMIZED), "OPTIMIZADO")
    self.assertEqual(quality.name_of(OFF), "SIN EFECTOS")
    self.assertEqual(quality.name_of(AUTO), "AUTO")
    self.assertEqual(config.Gpu.MODE_NAMES[OPTIMIZED], "OPTIMIZADO")

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

  def test_full_never_lowers_the_quality(self):
    for _ in range(FRAMES * 4):        # the governor would drop by now
      self.fx.governor.frame(SLOW, DT)
    self.run_chain()
    self.assertEqual(self.fx.stage_level(), "alta")
    self.assertEqual(self.fx.level_index(), quality.MIN_LEVEL)
    self.assertEqual(self.fx.policy().skips, ())
    self.assertEqual(self.fx.governor.changes, 0)
    self.assertTrue(self.fx.full_quality())

  def test_full_draws_the_heavy_stages(self):
    self.run_chain()
    data = self.fx.summary()
    for stage in (quality.GLOW, quality.LIGHTS):
      self.assertIn(stage, data)
    self.assertEqual(data["quality_name"], "FULL")

  def test_full_draws_the_crowd(self):
    self.assertTrue(self.fx.policy().crowd)
    self.assertTrue(self.fx.standing_crowd())

  def test_full_has_the_extra_strength(self):
    self.assertEqual(self.fx.punch(), config.Gpu.FULL_PUNCH)
    self.assertEqual(self.fx.policy().particles,
                     config.Gpu.FULL_PARTICLES)
    self.assertGreater(self.fx.punch(), 1.0)


class OptimizedTest(unittest.TestCase):
  """OPTIMIZADO leaves only the cheap stage, small and without the crowd."""

  def setUp(self):
    pygame.init()
    pygame.display.set_mode((W, H))
    self.fx = postfx.PostFx(options(quality_mode=OPTIMIZED), (W, H))
    self.fx.ops = cpu_ref.Cpu()
    self.fx.enabled = True
    self.fx.mode = "cpu"

  def test_only_the_cheap_stage(self):
    policy = self.fx.policy()
    self.assertEqual(quality.stages(policy.stage), OPTIMIZED_ONLY)
    for stage in HEAVY + (quality.LIGHTS, "crt", "var", "confetti"):
      self.assertIn(stage, policy.skips)

  def test_sharp_and_no_crowd(self):
    """OPTIMIZADO keeps the full resolution: the crowd is not blocky."""
    self.assertEqual(self.fx.level_index(), config.Gpu.OPTIMIZED_LEVEL)
    self.assertFalse(self.fx.policy().crowd)
    self.assertFalse(self.fx.standing_crowd())
    self.assertEqual(quality.scale(self.fx.level_index()), 1)

  def test_weak_powers(self):
    self.assertLess(self.fx.punch(), 1.0)
    self.assertLess(self.fx.policy().particles, 1.0)

  def test_chain_runs_only_the_cheap_stage(self):
    screen = pygame.Surface((W, H))
    for _ in range(FRAMES):
      target = self.fx.begin(screen, {})
      target.fill((20, 30, 40))
      self.fx.finish(screen, DT)
    data = self.fx.summary()
    for stage in HEAVY:
      self.assertEqual(data[stage], 0.0)
    self.assertGreater(data["particles"], 0.0)
    self.assertEqual(screen.get_size(), (W, H))
    self.assertEqual(data["quality_name"], "OPTIMIZADO")


class AutoTest(unittest.TestCase):
  """AUTO is the governor of F7: on the CPU it drops when it cannot."""

  def setUp(self):
    pygame.init()
    pygame.display.set_mode((W, H))
    self.fx = postfx.PostFx(options(quality_mode=AUTO), (W, H))
    self.fx.ops = cpu_ref.Cpu()
    self.fx.enabled = True
    self.fx.mode = "cpu"

  def test_auto_still_has_the_governor(self):
    self.assertTrue(self.fx.policy().governor)
    self.assertFalse(self.fx.policy().crowd)

  def test_auto_drops_with_slow_frames(self):
    start = self.fx.governor.level
    for _ in range(config.Gpu.QUALITY_AVG_FRAMES * 2):
      self.fx.governor.frame(SLOW, DT)
    self.assertGreater(self.fx.governor.changes, 0)
    self.assertGreater(self.fx.governor.level, start)
    self.assertIn(self.fx.stage_level(), config.Gpu.QUALITIES)


class SwitchTest(unittest.TestCase):
  """The F10 key and the options menu move between the four modes."""

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
    self.assertEqual(self.fx.quality_mode, OPTIMIZED)
    self.fx.cycle_quality_mode()
    self.assertEqual(self.fx.quality_mode, OFF)
    self.fx.cycle_quality_mode()
    self.assertEqual(self.fx.quality_mode, AUTO)
    self.fx.cycle_quality_mode()
    self.assertEqual(self.fx.quality_mode, FULL)

  def test_switching_forgets_the_governor(self):
    self.fx.set_quality_mode(AUTO)
    for _ in range(config.Gpu.QUALITY_AVG_FRAMES * 2):
      self.fx.governor.frame(SLOW, DT)
    self.assertGreater(self.fx.governor.level, quality.MIN_LEVEL)
    self.fx.set_quality_mode(FULL)
    self.assertEqual(self.fx.governor.level, quality.MIN_LEVEL)
    self.assertEqual(self.fx.summary()["quality_mode"], FULL)


class CliTest(unittest.TestCase):
  """`--calidad` chooses the mode (F10 also does it inside a match)."""

  def test_flag_sets_the_mode(self):
    options = main_module.parse_args(["--no-audio", "--calidad",
                                      "optimizado"])
    self.assertEqual(options.quality_mode, "optimizado")

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
    fx = postfx.PostFx(options(quality_mode=mode), (W, H))
    fx.start()
    return fx

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

  def test_a_chosen_mode_survives_the_backend_fallback(self):
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
    fx = postfx.PostFx(options(quality_mode=mode), (W, H))
    fx.start()
    return fx

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

  def test_optimizado_leaves_the_embers_out(self):
    fx = self.chain(OPTIMIZED)
    fx.fx.burned = ((10.0, 20.0),)
    # pylint: disable-next=protected-access
    fx._spawn_embers(postfx.EMBER_EVERY)
    self.assertEqual(self.live(fx), 0)


if __name__ == "__main__":
  unittest.main()
