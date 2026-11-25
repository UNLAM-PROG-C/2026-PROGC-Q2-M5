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
from fdc.gpu import replay

W, H = 64, 48           # size of the test surface
FRAMES = 3              # frames of the chain in each test
DT = 1 / 60.0           # s between frames
SEED = 3                # fixed random surface
NIGHT_FRAMES = 12       # frames with the night mode on
# Night rules (`docs/guia-visual.md`): below the day, above the black, no burns.
NIGHT_SETTLE = 40       # frames until the gain of the night stops moving
WHITE_LEVEL = 255       # a frame as bright as it gets
NIGHT_TOP = 250         # from here a pixel would look burnt
NIGHT_WHITE_FLOOR = 100   # even a white frame keeps some light at night
NIGHT_SHARE = 0.85      # the grass of the night, as a share of the day
NIGHT_FLOOR = 0.45      # ... and its floor: the pitch is never lost
NIGHT_BAND = 24         # rows compared to see the fall of the light
NIGHT_GRADIENT = 6      # gray levels the light falls from the stands down
NIGHT_GAIN_DELTA = 0.005   # the meter must not see the sky
FAST_BALL = {"x": 30.0, "y": 20.0, "vx": 900.0, "vy": 0.0}
SLOW_BALL = {"x": 30.0, "y": 20.0, "vx": 30.0, "vy": 0.0}
# Art rules: the effects are checked on the size of the real screen.
PIXEL_W, PIXEL_H = 1280, 720    # px: the screen the player sees
FLAT = 130                      # byte of the flat frame of the art tests
FLAT_GAIN = int(FLAT * config.Gpu.FREEZE_GAIN) + 1   # most the ice may add
ICE_STATE = {
    "players": [{"x": 400.0, "y": 640.0, "frozen": True},
                {"x": 880.0, "y": 640.0}],
    "ball": SLOW_BALL,
    "effects": [{"power": "freeze_self", "prop": "frozen", "target": "p0",
                 "left": 1.8, "dur": 2.0}],
}
# Frames needed to save two states (one every REPLAY_STEP s) and to end the
# the standalone replay.
SAVE_FRAMES = int(config.Gpu.REPLAY_STEP / DT) + 2
REPLAY_FRAMES = int(config.Gpu.REPLAY_DURATION / DT) + 2
# F10: the goal celebrates first and only then the replay starts, so these
# tests draw the celebration before looking at the replay (and the replay
# itself lasts REPLAY_AFTER_GOAL s more).
CELEBRATION_FRAMES = int(config.Gpu.GOAL_CELEBRATION / DT) + 2
REPLAY_SECONDS = config.Gpu.REPLAY_DURATION + config.Gpu.REPLAY_AFTER_GOAL
FULL_REPLAY_FRAMES = int(REPLAY_SECONDS / DT) + 4
MOUTH = config.Arena.GOAL_DEPTH              # x of the mouth of the left goal
BAR_Y = config.Arena.FLOOR_Y - config.Arena.GOAL_HEIGHT
GOAL = {"type": protocol.EV_GOAL, "x": 600.0, "y": 300.0, "side": 0}
CLOSE_GOAL = {"type": protocol.EV_GOAL, "x": MOUTH - 2.0, "y": BAR_Y + 18.0,
              "side": 0}
# A match state for the replay history.
PLAY_STATE = {
    "phase": protocol.PHASE_PLAYING, "paused": False, "score": [0, 0],
    "goals": [config.Arena.GOAL_HEIGHT] * 2, "effects": [],
    "ball": {"x": 600.0, "y": 300.0, "r": 18.0, "vx": 0.0, "vy": 0.0},
    "players": [{"x": 10.0, "y": 40.0}, {"x": 50.0, "y": 40.0}],
}
# The four F3 powers at once, at full strength, on a shared screen.
POWER_STATE = {
    "players": [{"x": 10.0, "y": 40.0, "frozen": True},
                {"x": 50.0, "y": 40.0}],
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
  base = {"no_gpu": False, "quality_mode": "full", "web": False}
  base.update(extra)
  return types.SimpleNamespace(**base)


def surface(colour=(40, 60, 90)):
  """Small surface to push through the chain."""
  surf = pygame.Surface((W, H)).convert()
  surf.fill(colour)
  pygame.draw.rect(surf, (240, 240, 220), (8, 6, 30, 20))
  return surf


def _mean(block):
  """Mean gray level of a block of pixels."""
  return float(block.astype(np.float32).mean())


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


class PowerChainTest(unittest.TestCase):
  """F3/F4 through the whole chain, on the numpy backend."""

  def setUp(self):
    pygame.init()
    pygame.display.set_mode((W, H))
    self.fx = postfx.PostFx(options(), (W, H))
    self.fx.ops = cpu_ref.Cpu()
    self.fx.enabled = True
    self.fx.mode = "cpu"
    self.screen = pygame.Surface((W, H))

  def run_chain(self, state, frames=FRAMES):
    for _ in range(frames):
      target = self.fx.begin(self.screen, state)
      target.fill((20, 30, 40))
      pygame.draw.rect(target, (240, 240, 220), (8, 6, 20, 14))
      self.fx.finish(self.screen, DT)
    return self.fx.summary()

  def test_every_power_draws(self):
    data = self.run_chain(POWER_STATE)
    self.assertGreater(data["ice"], 0.0)
    self.assertGreater(data["blackout"], 0.0)
    self.assertGreater(data["confusion"], 0.0)
    self.assertGreater(data["fire"], 0.0)

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
    self.assertEqual(self.fx._derive().ice, 0.0)

  def test_shared_ice_only_changes_the_clipped_box(self):
    self.fx.state = POWER_STATE
    self.fx.fx = self.fx._derive()
    original = np.full((H, W, 3), FLAT, np.uint8)
    out = self.fx._ice(original.copy())
    assert not np.array_equal(out[:44, :62], original[:44, :62])
    assert np.array_equal(out[44:], original[44:])
    assert np.array_equal(out[:, 62:], original[:, 62:])


class ReplayChainTest(unittest.TestCase):
  """Replay inside the chain."""

  def setUp(self):
    pygame.init()
    pygame.display.set_mode((W, H))
    self.fx = postfx.PostFx(options(), (W, H))
    self.fx.ops = cpu_ref.Cpu()
    self.fx.enabled = True
    self.fx.mode = "cpu"
    self.screen = pygame.Surface((W, H))

  def play(self, frames, state=PLAY_STATE):
    """Draws `frames` frames of the chain with that state."""
    for _ in range(frames):
      target = self.fx.begin(self.screen, state)
      target.fill((20, 30, 40))
      self.fx.finish(self.screen, DT)

  def test_goal_starts_the_replay(self):
    self.play(SAVE_FRAMES)
    self.fx.event(GOAL)
    self.play(CELEBRATION_FRAMES)
    self.assertEqual(self.fx.replay_mode(), replay.REPLAY_KIND)
    self.assertIsNot(self.fx.view_state(PLAY_STATE), PLAY_STATE)
    self.assertFalse(self.fx.confetti.alive())   # the replay took over
    self.play(2)
    self.assertTrue(self.fx.metrics.stage["crt"])

  def test_scheduled_goal_waits_for_the_simulation_window(self):
    self.play(SAVE_FRAMES)
    self.fx.event(dict(GOAL, replay=True))
    self.play(CELEBRATION_FRAMES)
    self.assertIsNone(self.fx.replay_mode())
    self.assertFalse(self.fx.metrics.stage["crt"])

  def test_the_goal_celebrates_before_the_replay(self):
    """F10: first the confetti and the sign, then the replay."""
    self.play(SAVE_FRAMES)
    self.fx.event(GOAL)
    self.assertIsNone(self.fx.replay_mode())
    self.assertIs(self.fx.view_state(PLAY_STATE), PLAY_STATE)
    self.assertIn(postfx._CELEBRATION_NAME, self.fx.active_effects())
    self.play(4)
    self.assertTrue(self.fx.confetti.alive())
    self.assertTrue(self.fx.metrics.stage["confetti"])

  def test_the_replay_follows_the_goal_half_a_second_later(self):
    """F10: the replay ends REPLAY_AFTER_GOAL s after the goal."""
    self.play(REPLAY_FRAMES)
    goal_time = self.fx.clock
    self.fx.event(GOAL)
    self.play(CELEBRATION_FRAMES)
    frames = self.fx.player.frames
    self.assertAlmostEqual(frames[-1][0],
                           goal_time + config.Gpu.REPLAY_AFTER_GOAL,
                           places=6)
    self.assertLessEqual(frames[0][0],
                         goal_time - config.Gpu.REPLAY_DURATION
                         + config.Gpu.REPLAY_STEP + DT)
    self.play(FULL_REPLAY_FRAMES)
    self.assertIsNone(self.fx.replay_mode())

  def test_the_confetti_is_gone_when_the_replay_ends(self):
    self.play(SAVE_FRAMES)
    self.fx.event(GOAL)
    self.play(CELEBRATION_FRAMES + FULL_REPLAY_FRAMES)
    self.assertFalse(self.fx.confetti.alive())

  def test_replay_ends_and_the_live_state_comes_back(self):
    self.play(SAVE_FRAMES)
    self.fx.event(GOAL)
    self.play(CELEBRATION_FRAMES + FULL_REPLAY_FRAMES)
    self.assertIsNone(self.fx.replay_mode())
    self.assertIs(self.fx.view_state(PLAY_STATE), PLAY_STATE)

  def test_close_goal_uses_the_same_crt_replay(self):
    self.play(SAVE_FRAMES)
    self.fx.event(CLOSE_GOAL)
    self.play(CELEBRATION_FRAMES)
    self.assertEqual(self.fx.replay_mode(), replay.REPLAY_KIND)
    self.play(2)
    self.assertTrue(self.fx.metrics.stage["crt"])

  def test_the_s_key_leaves_the_party_and_then_the_replay(self):
    """F10: one key skips the celebration and the replay."""
    self.play(SAVE_FRAMES)
    self.fx.event(GOAL)
    self.play(4)
    self.assertTrue(self.fx.skip())
    self.assertFalse(self.fx.confetti.alive())
    self.assertIsNone(self.fx.replay_mode())
    self.fx.event(GOAL)
    self.play(CELEBRATION_FRAMES)
    self.assertEqual(self.fx.replay_mode(), replay.REPLAY_KIND)
    self.assertTrue(self.fx.skip())
    self.assertIsNone(self.fx.replay_mode())
    self.assertIs(self.fx.view_state(PLAY_STATE), PLAY_STATE)
    self.assertFalse(self.fx.skip())

  def test_clear_forgets_the_replay(self):
    self.play(SAVE_FRAMES)
    self.fx.event(GOAL)
    self.fx.clear()
    self.assertIsNone(self.fx.replay_mode())
    self.assertEqual(self.fx.history.saved, [])


class ArtRulesTest(unittest.TestCase):
  """Rules of `docs/guia-visual.md`: no effect touches the stands."""

  def setUp(self):
    pygame.init()
    pygame.display.set_mode((W, H))
    self.fx = postfx.PostFx(options(), (PIXEL_W, PIXEL_H))
    self.fx.ops = cpu_ref.Cpu()
    self.fx.enabled = True
    self.fx.state = ICE_STATE
    self.image = np.full((PIXEL_H, PIXEL_W, 3), FLAT, np.uint8)

  def test_ice_focus_keeps_the_stands(self):
    out = self.fx._lights(self.image.copy())
    top = config.Gpu.PITCH_TOP
    self.assertTrue(np.array_equal(out[:top], self.image[:top]))
    self.assertLessEqual(int(out.max()), FLAT + FLAT_GAIN)
    self.assertGreater(int(out[600:680, 380:420].max()), FLAT)

  def test_night_sky_stays_dark(self):
    out = self.fx._night_sky(self.image.copy())
    top = config.Gpu.CROWD_TOP
    self.assertLess(int(out[:top].max()), FLAT)
    self.assertTrue(np.array_equal(out[top:], self.image[top:]))

  def night(self, image, frames=NIGHT_SETTLE):
    """The night over `image`, with the auto exposure already settled."""
    self.fx.fx.night = True
    for _ in range(frames):
      out = self.fx._night(image.copy())
    return out

  def test_night_never_reaches_white(self):
    """Six lamps and the gain together stay below the white: no burns."""
    white = np.full_like(self.image, WHITE_LEVEL)
    out = self.night(white)
    self.assertLessEqual(int(out.max()), NIGHT_TOP)
    self.assertGreater(int(out.max()), NIGHT_WHITE_FLOOR)

  def test_night_is_darker_than_the_day(self):
    """The grass of the night stays well below the level of the day."""
    out = self.night(self.image)
    pitch = _mean(out[config.Gpu.PITCH_TOP:])
    self.assertLess(pitch, FLAT * NIGHT_SHARE)
    self.assertGreater(pitch, FLAT * NIGHT_FLOOR)

  def test_night_lights_the_pitch_from_the_stands(self):
    """The light of the lamps falls from the stands to the near line."""
    out = self.night(self.image)
    top = config.Gpu.PITCH_TOP
    near_stands = _mean(out[top:top + NIGHT_BAND])
    near_line = _mean(out[-NIGHT_BAND:])
    self.assertGreater(near_stands, near_line + NIGHT_GRADIENT)

  def test_night_meter_reads_only_the_grass(self):
    """A white sky does not ask the night for more gain than a black one."""
    dark = postfx.PostFx(options(), (PIXEL_W, PIXEL_H))
    dark.ops = cpu_ref.Cpu()
    dark.enabled = True
    dark.state = ICE_STATE
    black = self.image.copy()
    black[:config.Gpu.CROWD_TOP] = 0
    self.night(self.image)
    dark.fx.night = True
    for _ in range(NIGHT_SETTLE):
      dark._night(black)
    self.assertAlmostEqual(self.fx.exposure.gain, dark.exposure.gain,
                           delta=NIGHT_GAIN_DELTA)


if __name__ == "__main__":
  unittest.main()
