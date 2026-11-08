"""The rules that derive the effects of a frame (fdc.gpu.effects_state).

These tests need no window and no CUDA: `derive` is a pure function of the
state, the viewer and the clock, so the F3 powers and the F4 night, shock
wave and trail are checked here frame by frame.
"""
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc import config
from fdc import protocol
from fdc.gpu import effects_state
from fdc.gpu import exposure
from fdc.sim import match

G = config.Gpu
NOW = 10.0              # clock of the tests (s)
DURATION = 6.0          # s of a power in the state
START = 9.5             # when the effect started (0.5 s ago)
FULL_LEFT = DURATION - 0.5   # s left: the effect is at full strength
PLAYERS = ({"x": 200.0, "y": 600.0}, {"x": 900.0, "y": 600.0})


def effect(prop, target, left=FULL_LEFT, dur=DURATION, power=""):
    """One effect as the simulation writes it in the state."""
    return {"power": power or prop, "prop": prop, "target": target,
            "left": left, "dur": dur}


def state(effects=(), vx=0.0, vy=0.0):
    """Match state with the effects and the speed of the ball."""
    return {"players": PLAYERS, "effects": list(effects),
            "ball": {"x": 640.0, "y": 400.0, "vx": vx, "vy": vy}}


class DeriveTest(unittest.TestCase):
    """Power -> parameter of the chain, with the perspective of the viewer."""

    def derive(self, effects=(), viewer=None, **extra):
        return effects_state.derive(state(effects, **extra), viewer, NOW)

    def test_empty_state(self):
        fx = effects_state.derive({}, None, NOW)
        self.assertEqual(fx.ice, 0.0)
        self.assertFalse(fx.blackout)
        self.assertIsNone(fx.fire)
        self.assertIsNone(fx.shock)
        self.assertFalse(fx.night)

    def test_ice_shared_screen(self):
        fx = self.derive([effect("frozen", "p0", power="freeze_rival")])
        self.assertAlmostEqual(fx.ice, 1.0)
        self.assertEqual(len(fx.blackout), 0)

    def test_ice_only_for_the_affected_player(self):
        effects = [effect("frozen", "p0", power="freeze_self")]
        self.assertAlmostEqual(self.derive(effects, viewer=0).ice, 1.0)
        self.assertEqual(self.derive(effects, viewer=1).ice, 0.0)

    def test_blackout_keeps_the_light_on_the_players(self):
        fx = self.derive([effect("blackout", "p0")])
        self.assertEqual(len(fx.blackout), len(PLAYERS))
        head = PLAYERS[0]["y"] - G.HEAD_ABOVE
        self.assertAlmostEqual(fx.blackout[0][1], head)

    def test_blackout_is_dark_for_the_other_player(self):
        effects = [effect("blackout", "p0")]
        self.assertFalse(self.derive(effects, viewer=1).blackout)
        self.assertEqual(len(self.derive(effects, viewer=0).blackout), 1)

    def test_confusion(self):
        effects = [effect("confusion", "p1")]
        self.assertAlmostEqual(self.derive(effects, viewer=1).confusion, 1.0)
        self.assertEqual(self.derive(effects, viewer=0).confusion, 0.0)

    def test_fire_goes_around_the_ball(self):
        fx = self.derive([effect("fire", "ball")])
        self.assertEqual(fx.fire, (640.0, 400.0, G.FIRE_RADIUS))

    def test_unknown_power_does_nothing(self):
        fx = self.derive([effect("speed", "p1")])
        self.assertEqual(fx.ice, 0.0)
        self.assertFalse(fx.blackout)
        self.assertIsNone(fx.fire)

    def test_fade_in_and_out(self):
        start = self.derive([effect("blackout", "p0", left=DURATION)])
        end = self.derive([effect("blackout", "p0", left=0.0)])
        self.assertEqual(start.blackout, ())
        self.assertEqual(end.blackout, ())

    def test_trail_needs_a_fast_ball(self):
        self.assertEqual(self.derive(vx=900.0).trail, 1.0)
        self.assertEqual(self.derive(vx=100.0).trail, 0.0)


class EventTest(unittest.TestCase):
    """The goal shock wave is an event with its own clock."""

    def test_age_and_intensity(self):
        fx = effects_state.EventFx(effects_state.SHOCK_KIND, 10.0, 20.0,
                                   NOW, 1.0)
        self.assertEqual(fx.age(NOW), 0.0)
        self.assertAlmostEqual(fx.intensity(NOW + 0.5), 0.5)
        self.assertTrue(fx.alive(NOW + 0.9))
        self.assertFalse(fx.alive(NOW + 1.0))

    def test_derive_returns_the_newest_wave(self):
        old = effects_state.EventFx("shock", 1.0, 2.0, NOW - 1.0, 2.0)
        new = effects_state.EventFx("shock", 3.0, 4.0, NOW - 0.2, 2.0)
        x, y, age = effects_state.derive({"players": []}, None, NOW,
                                         [old, new]).shock
        self.assertEqual((x, y), (3.0, 4.0))
        self.assertAlmostEqual(age, 0.2)

    def test_dead_wave_is_ignored(self):
        dead = effects_state.EventFx("shock", 1.0, 2.0, NOW - 5.0, 1.0)
        fx = effects_state.derive({"players": []}, None, NOW, [dead])
        self.assertIsNone(fx.shock)

    def test_other_kinds_are_ignored(self):
        other = effects_state.EventFx("crt", 1.0, 2.0, NOW, 1.0)
        fx = effects_state.derive({"players": []}, None, NOW, [other])
        self.assertIsNone(fx.shock)


class TrailGateTest(unittest.TestCase):
    """Hysteresis of the trail: 800 px/s on, 0.25 s off."""

    def test_turns_on_at_the_threshold(self):
        gate = effects_state.TrailGate()
        self.assertTrue(gate.update(G.TRAIL_MIN_SPEED, 1 / 60))
        self.assertTrue(gate.active)

    def test_stays_on_for_the_delay(self):
        gate = effects_state.TrailGate()
        gate.update(G.TRAIL_MIN_SPEED, 1 / 60)
        self.assertTrue(gate.update(10.0, G.TRAIL_OFF_DELAY / 2))
        self.assertFalse(gate.update(10.0, G.TRAIL_OFF_DELAY))

    def test_off_when_the_ball_is_slow_from_the_start(self):
        gate = effects_state.TrailGate()
        self.assertFalse(gate.update(10.0, 1 / 60))

    def test_reset(self):
        gate = effects_state.TrailGate()
        gate.update(G.TRAIL_MIN_SPEED, 1 / 60)
        gate.reset()
        self.assertFalse(gate.active)


class ExposureTest(unittest.TestCase):
    """Auto exposure: EMA towards target / mean, with limits."""

    def test_grows_towards_the_target(self):
        auto = exposure.AutoExposure()
        for _ in range(200):
            auto.update(40.0)       # 110 / 40 = 2.75, clamped to the top
        self.assertAlmostEqual(auto.gain, G.AUTOEXPOSURE_MAX, delta=0.01)

    def test_reaches_the_target_inside_the_limits(self):
        auto = exposure.AutoExposure()
        for _ in range(400):
            auto.update(100.0)
        self.assertAlmostEqual(auto.gain, G.AUTOEXPOSURE_TARGET / 100.0,
                               delta=0.01)

    def test_limits(self):
        auto = exposure.AutoExposure()
        auto.update(1.0)
        self.assertLessEqual(auto.gain, G.AUTOEXPOSURE_MAX)
        auto = exposure.AutoExposure()
        for _ in range(50):
            auto.update(255.0)
        self.assertGreaterEqual(auto.gain, G.AUTOEXPOSURE_MIN)

    def test_black_frame_keeps_the_gain(self):
        auto = exposure.AutoExposure(1.3)
        self.assertEqual(auto.update(0.0), 1.3)

    def test_one_step_only(self):
        auto = exposure.AutoExposure(1.0)
        self.assertAlmostEqual(auto.update(40.0), 1.0 + 0.1 * (
            G.AUTOEXPOSURE_MAX - 1.0))

    def test_reset(self):
        auto = exposure.AutoExposure(2.0)
        auto.reset()
        self.assertEqual(auto.gain, 1.0)


class NightTest(unittest.TestCase):
    """The six warm spotlights of the night mode."""

    def test_six_lights_over_the_pitch(self):
        lights = effects_state.night_lights()
        self.assertEqual(len(lights), G.NIGHT_LIGHTS)
        self.assertEqual(lights[0], (G.NIGHT_FIRST_X, G.NIGHT_Y,
                                     G.NIGHT_RADIUS, G.NIGHT_POWER))
        self.assertAlmostEqual(lights[1][0] - lights[0][0], G.NIGHT_STEP_X)

    def test_light_array_keeps_the_points(self):
        lights = effects_state.light_array([(1.0, 2.0)], 30.0, 0.9)
        self.assertEqual(lights, [(1.0, 2.0, 30.0, 0.9)])

    def test_night_is_a_parameter(self):
        fx = effects_state.derive({}, None, NOW, night=True)
        self.assertTrue(fx.night)
        self.assertEqual(fx, effects_state.derive({}, None, NOW, night=True))


class BurnedEffectsTest(unittest.TestCase):
    """1.0.2: the burnt player of the fire power reaches the chain."""

    def test_the_burnt_player_is_a_point_of_the_pitch(self):
        fx = effects_state.derive(
            state([effect("burned", "p0", power="fire")]), None, NOW)
        self.assertEqual(fx.burned, ((PLAYERS[0]["x"], PLAYERS[0]["y"]),))

    def test_the_match_snapshot_carries_the_property(self):
        """The chain reads the property of each effect: it travels."""
        m = match.Match(1, seed=1)
        m.powers.activate("freeze_self", 0, m, 0, 0, [])
        effect = m.snapshot(1)["effects"][0]
        self.assertEqual(effect["prop"], "frozen")

    def test_the_ball_on_fire_is_not_a_burnt_player(self):
        fx = effects_state.derive(
            state([effect("fire", "ball", power="fire")]), None, NOW)
        self.assertEqual(fx.burned, ())
        self.assertIsNotNone(fx.fire)


class ProtocolTest(unittest.TestCase):
    """The goal event that starts the shock wave still exists."""

    def test_goal_event(self):
        self.assertEqual(effects_state.SHOCK_EVENT, protocol.EV_GOAL)


if __name__ == "__main__":
    unittest.main()
