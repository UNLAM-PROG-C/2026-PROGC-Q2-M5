"""The chain of effects (fdc.gpu.postfx) on the CPU backend.

These tests do not need CUDA: they use the numpy version so they run
everywhere (and they are the safety net when the kernels change).
"""
import types
import unittest

import numpy as np

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
import pygame

from fdc import config
from fdc import protocol
from fdc.gpu import cpu_ref
from fdc.gpu import metrics
from fdc.gpu import particles
from fdc.gpu import postfx
from fdc.gpu import quality

W, H = 64, 48           # size of the test surface
FRAMES = 3              # frames of the chain in each test
DT = 1 / 60.0           # s between frames
SEED = 3                # fixed random surface
NIGHT_FRAMES = 12       # frames with the night mode on
FAST_BALL = {"x": 30.0, "y": 20.0, "vx": 900.0, "vy": 0.0}
SLOW_BALL = {"x": 30.0, "y": 20.0, "vx": 30.0, "vy": 0.0}
# The four F3 powers at once, at full strength, on a shared screen.
POWER_STATE = {
    "players": [{"x": 10.0, "y": 40.0}, {"x": 50.0, "y": 40.0}],
    "ball": FAST_BALL,
    "effects": [
        {"power": "freeze_self", "prop": "frozen", "target": "p0",
         "left": 1.8, "dur": 2.0},
        {"power": "blackout", "prop": "blackout", "target": "p1",
         "left": 5.0, "dur": 6.0},
        {"power": "confusion", "prop": "confusion", "target": "p0",
         "left": 4.0, "dur": 5.0},
        {"power": "fire", "prop": "fire", "target": "ball",
         "left": 5.0, "dur": 6.0},
    ],
}


def options(**extra):
    """The attributes the interface reads from the command line."""
    base = {"no_gpu": False, "gpu_quality": "media", "web": False}
    base.update(extra)
    return types.SimpleNamespace(**base)


def surface(colour=(40, 60, 90)):
    """Small surface to push through the chain."""
    surf = pygame.Surface((W, H)).convert()
    surf.fill(colour)
    pygame.draw.rect(surf, (240, 240, 220), (8, 6, 30, 20))
    return surf


class ChainTest(unittest.TestCase):
    """The chain runs, returns the same size and measures itself."""

    def setUp(self):
        pygame.init()
        pygame.display.set_mode((W, H))
        self.fx = postfx.PostFx(options(), (W, H))
        self.fx.ops = cpu_ref.Cpu()
        self.fx.enabled = True
        self.fx.mode = "cpu"

    def run_chain(self, frames=FRAMES):
        screen = pygame.Surface((W, H))
        for _ in range(frames):
            target = self.fx.begin(screen, {})
            target.fill((20, 30, 40))
            self.fx.finish(screen, DT)
        return screen

    def test_same_size_and_metrics(self):
        screen = self.run_chain()
        self.assertEqual(screen.get_size(), (W, H))
        data = self.fx.summary()
        self.assertEqual(data["mode"], "cpu")
        self.assertEqual(data["frames"], FRAMES)
        self.assertGreater(data["frame"], 0.0)

    def test_every_quality_level_runs(self):
        for level in config.Gpu.QUALITIES:
            self.fx.level = level
            self.run_chain(1)
        self.assertTrue(self.fx.metrics.frames)

    def test_events_make_particles(self):
        msg = {"type": protocol.EV_TOUCH, "x": 20.0, "y": 20.0,
               "speed": 400.0}
        self.fx.event(msg)
        self.fx.particles.update(DT)
        pos, _ = self.fx.particles.live()
        self.assertGreater(len(pos), 0)

    def test_slow_touch_does_not_spark(self):
        self.fx.event({"type": protocol.EV_TOUCH, "x": 1.0, "y": 1.0,
                       "speed": 1.0})
        pos, _ = self.fx.particles.live()
        self.assertEqual(len(pos), 0)

    def test_clear_empties_the_chain(self):
        self.fx.event({"type": protocol.EV_GOAL, "x": 10.0, "y": 10.0})
        self.fx.clear()
        pos, _ = self.fx.particles.live()
        self.assertEqual(len(pos), 0)
        self.assertIsNone(self.fx.trail)

    def test_disabled_chain_draws_nothing(self):
        self.fx.enabled = False
        screen = pygame.Surface((W, H))
        self.assertIs(self.fx.begin(screen, {}), screen)
        self.fx.finish(screen, DT)
        self.assertEqual(self.fx.metrics.skipped, 1)

    def test_toggle_switches_backend(self):
        first = self.fx.toggle()
        second = self.fx.toggle()
        self.assertIn(first, ("gpu", "cpu"))
        self.assertIn(second, ("gpu", "cpu"))
        self.assertEqual(self.fx.metrics.summary()["frames"], 0)


class ParticleTest(unittest.TestCase):
    """The pool of sparks recycles rows and never grows."""

    def test_spawn_and_expire(self):
        field = particles.Field(50)
        field.spawn(10.0, 10.0, (1.0, 1.0, 1.0), 10)
        self.assertEqual(len(field.live()[0]), 10)
        field.update(config.Gpu.PARTICLE_LIFE[1] + 1.0)
        self.assertEqual(len(field.live()[0]), 0)

    def test_full_pool_recycles(self):
        field = particles.Field(20)
        for _ in range(5):
            field.spawn(1.0, 1.0, (1.0, 0.0, 0.0), 20)
        self.assertLessEqual(len(field.live()[0]), field.count)


class MetricsTest(unittest.TestCase):
    """Means and fps of the timing buffer."""

    def test_average_and_fps(self):
        data = metrics.Metrics(frames=4)
        data.add("glow", 2.0)
        data.add("glow", 4.0)
        data.frame(10.0)
        self.assertAlmostEqual(data.average("glow"), 3.0)
        self.assertAlmostEqual(data.average("lights"), 0.0)
        self.assertAlmostEqual(data.fps(), 100.0)


class QualityTest(unittest.TestCase):
    """Levels and their stages."""

    def test_stages_grow_with_the_level(self):
        low = quality.stages("baja")
        high = quality.stages("alta")
        self.assertLess(len(low), len(high))
        self.assertIn(quality.GLOW, high)

    def test_unknown_level_is_media(self):
        self.assertEqual(quality.stages("inexistente"),
                         quality.stages("media"))

    def test_downgrade(self):
        self.assertEqual(quality.downgrade("alta"), "media")
        self.assertEqual(quality.downgrade("baja"), "baja")


class PowerChainTest(unittest.TestCase):
    """F3/F4 through the whole chain, on the numpy backend."""

    def setUp(self):
        pygame.init()
        pygame.display.set_mode((W, H))
        self.fx = postfx.PostFx(options(), (W, H))
        self.fx.ops = cpu_ref.Cpu()
        self.fx.enabled = True
        self.fx.mode = "cpu"
        self.fx.level = "alta"
        self.screen = pygame.Surface((W, H))

    def run_chain(self, state, frames=FRAMES):
        for _ in range(frames):
            target = self.fx.begin(self.screen, state)
            target.fill((20, 30, 40))
            pygame.draw.rect(target, (240, 240, 220), (8, 6, 20, 14))
            self.fx.finish(self.screen, DT)
        return self.fx.summary()

    def test_every_power_draws(self):
        self.fx.event({"type": protocol.EV_GOAL, "x": 30.0, "y": 20.0})
        data = self.run_chain(POWER_STATE)
        self.assertGreater(data["shock"], 0.0)
        self.assertGreater(data["ice_tint"], 0.0)
        self.assertGreater(data["blackout"], 0.0)
        self.assertGreater(data["confusion"], 0.0)
        self.assertGreater(data["fire"], 0.0)

    def test_trail_needs_a_fast_ball(self):
        fast = dict(POWER_STATE, effects=[], ball=FAST_BALL)
        self.assertGreater(self.run_chain(fast)["trail"], 0.0)
        slow_fx = self._fresh()
        slow = dict(POWER_STATE, effects=[], ball=SLOW_BALL)
        self.assertEqual(slow_fx.summary()["trail"], 0.0)
        slow_fx.state = slow
        slow_fx.finish(self.screen, DT)
        self.assertFalse(slow_fx.trail_gate.active)

    def _fresh(self):
        """A second chain for the tests that need clean timings."""
        fx = postfx.PostFx(options(), (W, H))
        fx.ops = cpu_ref.Cpu()
        fx.enabled = True
        fx.mode = "cpu"
        fx.level = "alta"
        return fx

    def test_goal_event_starts_the_wave(self):
        self.fx.event({"type": protocol.EV_GOAL, "x": 30.0, "y": 20.0})
        self.assertEqual(len(self.fx.events), 1)
        self.run_chain(POWER_STATE, 1)
        self.assertGreater(self.fx.summary()["shock"], 0.0)

    def test_night_and_auto_exposure(self):
        self.fx.night = True
        data = self.run_chain(POWER_STATE, NIGHT_FRAMES)
        self.assertGreater(data["night"], 0.0)
        self.assertNotEqual(self.fx.exposure.gain, 1.0)

    def test_night_off_resets_the_gain(self):
        self.fx.night = True
        self.run_chain(POWER_STATE, 2)
        self.fx.night = False
        self.run_chain(POWER_STATE, 1)
        self.assertFalse(self.fx.fx.night)
        self.assertEqual(self.fx.exposure.gain, 1.0)

    def test_viewer_limits_the_powers(self):
        self.fx.state = POWER_STATE
        self.fx.viewer = 1
        self.assertEqual(self.fx._derive().ice, 0.0)
        self.fx.viewer = 0
        self.assertEqual(self.fx._derive().ice, 1.0)
        self.fx.viewer = None
        self.assertEqual(self.fx._derive().ice, 1.0)


if __name__ == "__main__":
    unittest.main()
