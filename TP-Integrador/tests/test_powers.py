"""Poderes: activación, receptor, expiración, reemplazo, pausa y limpieza."""
import unittest

from helpers import P, PHYSICS_DT, count, playing_match, run
from fdc.config import Arena, BallSpec, POWERS, POWERS_BY_ID, PowerRules, PlayerSpec
from fdc.sim.powers import Pickup, PowerManager


def put_pickup_on_ball(m, power):
    m.powers.pickup = Pickup(99, power, m.ball.x, m.ball.y)


def quiet(m):
    """Pelota quieta lejos de todo, jugadores apartados."""
    m.players[0].x, m.players[1].x = 250.0, 1030.0
    m.ball.x, m.ball.y = 640.0, Arena.FLOOR_Y - m.ball.radius


class ActivationTest(unittest.TestCase):
    def test_personal_not_consumed_without_last_touch(self):
        m = playing_match()
        quiet(m)
        put_pickup_on_ball(m, "speed_up")
        ev = run(m, 0.2)
        self.assertIsNotNone(m.powers.pickup)
        self.assertEqual(count(ev, P.EV_POWER), 0)

    def test_global_consumed_without_last_touch(self):
        m = playing_match()
        quiet(m)
        put_pickup_on_ball(m, "big_ball")
        ev = run(m, 0.1)
        self.assertIsNone(m.powers.pickup)
        self.assertEqual(count(ev, P.EV_POWER), 1)
        self.assertIn(("ball", "radius"), m.powers.effects)

    def test_receptor_is_last_toucher(self):
        m = playing_match()
        quiet(m)
        m.last_touch = 1
        put_pickup_on_ball(m, "speed_up")
        ev = run(m, 0.1)
        power = [e for e in ev if e[0] == P.EV_POWER][0][1]
        self.assertEqual(power["receptor"], 1)
        self.assertEqual(power["targets"], ["p1"])
        self.assertAlmostEqual(m.players[1].speed_mult, 1.35)
        self.assertEqual(m.players[0].speed_mult, 1.0)

    def test_rival_targets(self):
        m = playing_match()
        m.powers.activate("freeze_rival", 0, m, 0, 0, [])
        self.assertTrue(m.players[1].frozen)
        self.assertFalse(m.players[0].frozen)
        m.powers.activate("injured_rival", 1, m, 0, 0, [])
        self.assertTrue(m.players[0].no_kick)
        m.powers.activate("big_goal", 0, m, 0, 0, [])      # J1 ataca el arco derecho
        self.assertAlmostEqual(m.goals[1].target_height, Arena.GOAL_HEIGHT * 1.35)
        self.assertEqual(m.goals[0].target_height, Arena.GOAL_HEIGHT)
        m.powers.activate("small_goal", 1, m, 0, 0, [])    # J2 ataca el izquierdo
        self.assertAlmostEqual(m.goals[0].target_height, Arena.GOAL_HEIGHT * 0.75)

    def test_all_seventeen_powers(self):
        self.assertEqual(len(POWERS), 17)
        for pdef in POWERS:
            for receptor in (0, 1):
                m = playing_match()
                ev = []
                m.powers.activate(pdef.id, receptor, m, 0, 0, ev)
                self.assertEqual(count(ev, P.EV_POWER), 1, pdef.id)
                if pdef.prop == "bomb":
                    self.assertEqual(len(m.powers.bombs), 1)
                else:
                    self.assertEqual(len(m.powers.effects), 1, pdef.id)
                run(m, 0.5)   # que aplique sin errores


class DurationTest(unittest.TestCase):
    def test_expiration_restores_base(self):
        m = playing_match()
        quiet(m)
        m.powers.activate("speed_up", 0, m, 0, 0, [])
        m.powers.activate("grow", 0, m, 0, 0, [])
        ev = run(m, 6.1)
        self.assertEqual(count(ev, P.EV_POWER_EXPIRED), 2)
        self.assertEqual(m.powers.effects, {})
        self.assertEqual(m.players[0].speed_mult, 1.0)
        run(m, 0.5)
        self.assertEqual(m.players[0].scale, 1.0)

    def test_opposite_effect_replaces(self):
        m = playing_match()
        m.powers.activate("speed_up", 0, m, 0, 0, [])
        m.powers.activate("speed_down", 0, m, 0, 0, [])
        self.assertEqual(len(m.powers.effects), 1)
        self.assertAlmostEqual(m.players[0].speed_mult, 0.65)   # desde la base
        m.powers.activate("big_ball", None, m, 0, 0, [])
        m.powers.activate("small_ball", None, m, 0, 0, [])
        self.assertAlmostEqual(m.ball.target_radius, BallSpec.RADIUS * 0.70)

    def test_repeat_renews_without_stacking(self):
        m = playing_match()
        m.powers.activate("speed_up", 0, m, 0, 0, [])
        run(m, 4.0)
        m.powers.activate("speed_up", 0, m, 0, 0, [])
        eff = m.powers.effects[("p0", "speed")]
        self.assertAlmostEqual(eff.left, 6.0)
        self.assertAlmostEqual(m.players[0].speed_mult, 1.35)

    def test_different_properties_coexist(self):
        m = playing_match()
        m.powers.activate("speed_up", 0, m, 0, 0, [])
        m.powers.activate("jump_down", 0, m, 0, 0, [])
        m.powers.activate("low_bounce", 0, m, 0, 0, [])
        self.assertEqual(len(m.powers.effects), 3)
        self.assertAlmostEqual(m.players[0].jump_mult, 0.75)
        self.assertAlmostEqual(m.ball.bounce_mult, 0.45)

    def test_pause_freezes_timers(self):
        m = playing_match(spawn_powers=True)
        quiet(m)
        m.powers.activate("speed_up", 0, m, 0, 0, [])
        m.powers.activate("bombs", 0, m, 0, 0, [])
        m.powers.pickup = Pickup(5, "grow", 300, 300)
        spawn = m.powers.spawn_timer
        m.pause()
        run(m, 5.0)
        self.assertAlmostEqual(m.powers.effects[("p0", "speed")].left, 6.0)
        self.assertAlmostEqual(m.powers.bombs[0].fuse, PowerRules.BOMB_WARNING)
        self.assertAlmostEqual(m.powers.pickup.ttl, PowerRules.PICKUP_TTL)
        self.assertAlmostEqual(m.powers.spawn_timer, spawn)


class SpawnTest(unittest.TestCase):
    def test_spawn_interval_single_pickup_and_ttl(self):
        m = playing_match(seed=3, spawn_powers=True)
        quiet(m)
        m.ball.y = 120.0   # lejos de cualquier objeto, sin tocarlo
        m.powers.spawn_timer = m.powers._roll_spawn()
        self.assertTrue(PowerRules.SPAWN_MIN <= m.powers.spawn_timer <= PowerRules.SPAWN_MAX)
        seen = 0
        first_at = None
        for i in range(int(20 / PHYSICS_DT)):
            m.ball.x, m.ball.y, m.ball.vx, m.ball.vy = 640.0, 60.0, 0.0, 0.0
            ev = m.step(PHYSICS_DT)
            for e in ev:
                if e[0] == P.EV_POWER_SPAWN:
                    seen += 1
                    first_at = first_at or i * PHYSICS_DT
                    pk = m.powers.pickup
                    self.assertTrue(PowerManager.position_is_free(pk.x, pk.y, m))
            self.assertLessEqual(1 if m.powers.pickup else 0, 1)
        self.assertGreaterEqual(seen, 2)
        self.assertTrue(PowerRules.SPAWN_MIN - 0.1 <= first_at <= PowerRules.SPAWN_MAX + 0.1)

    def test_pickup_expires(self):
        m = playing_match()
        quiet(m)
        m.powers.pickup = Pickup(5, "grow", 300, 300)
        ev = run(m, PowerRules.PICKUP_TTL + 0.1)
        self.assertEqual(count(ev, P.EV_PICKUP_EXPIRED), 1)
        self.assertIsNone(m.powers.pickup)


class EffectBehaviourTest(unittest.TestCase):
    def test_frozen_keeps_gravity_blocks_actions(self):
        m = playing_match()
        p = m.players[0]
        p.y = Arena.FLOOR_Y - 100
        p.on_ground = False
        m.powers.activate("freeze_self", 0, m, 0, 0, [])
        x0 = p.x

        def hold(mm, i):
            mm.set_input(0, False, True, 1 + i, 1 + i)
        ev = run(m, 1.0, hold)
        self.assertTrue(p.on_ground)              # cayó por gravedad
        self.assertAlmostEqual(p.x, x0, delta=0.5)  # no se movió voluntariamente
        self.assertLess(p.kick_t, 0)
        self.assertGreaterEqual(count(ev, P.EV_KICK_BLOCKED), 1)

    def test_injured_can_jump_not_kick(self):
        m = playing_match()
        m.powers.activate("injured_self", 0, m, 0, 0, [])
        m.set_input(0, False, False, 1, 1)
        ev = run(m, 0.1)
        self.assertLess(m.players[0].vy, 0)
        self.assertEqual(count(ev, P.EV_KICK), 0)
        self.assertEqual(count(ev, P.EV_KICK_BLOCKED), 1)

    def test_size_changes_collision_gradually(self):
        m = playing_match()
        quiet(m)
        m.powers.activate("grow", 0, m, 0, 0, [])
        m.step(PHYSICS_DT)
        self.assertLess(m.players[0].scale, 1.05)          # no es un salto brusco
        run(m, PowerRules.SIZE_TRANSITION + 0.05)
        self.assertAlmostEqual(m.players[0].head()[2], PlayerSpec.HEAD_RADIUS * 1.25)

    def test_bomb_pushes_without_changing_last_touch(self):
        m = playing_match()
        quiet(m)
        m.last_touch = 1
        ev = []
        m.powers.activate("bombs", 0, m, 0, 0, ev)
        bomb = m.powers.bombs[0]
        self.assertTrue(PowerRules.BOMB_ZONE_X[0] <= bomb.x <= PowerRules.BOMB_ZONE_X[1])
        m.ball.x = bomb.x + 60
        m.ball.y = Arena.FLOOR_Y - m.ball.radius
        run(m, PowerRules.BOMB_WARNING - 0.05)
        self.assertEqual(len(m.powers.bombs), 1)            # aviso de 1 s
        ev = run(m, 0.1)
        self.assertEqual(count(ev, P.EV_BOMB_EXPLODE), 1)
        self.assertLess(m.ball.vy, -200)
        self.assertEqual(m.last_touch, 1)
        self.assertEqual(m.score, [0, 0])

    def test_grown_player_under_small_goal_is_released(self):
        m = playing_match()
        p = m.players[0]
        p.x = 40.0                              # dentro del arco propio
        m.powers.activate("grow", 0, m, 0, 0, [])
        m.powers.activate("small_goal", 1, m, 0, 0, [])   # achica el arco de J1
        xs = []
        for _ in range(int(1.5 / PHYSICS_DT)):
            m.step(PHYSICS_DT)
            xs.append(p.x)
        jumps = max(abs(b - a) for a, b in zip(xs, xs[1:]))
        self.assertLessEqual(jumps, 8.0 + 1e-6)   # sin teletransportes
        x0, y0, x1, y1 = m.goals[0].bar_rect()
        self.assertTrue(p.x - p.half_width() >= x1 - 0.5 or p.y - p.height() >= y1 - 0.5)

    def test_debug_power_modes(self):
        m = playing_match()
        ok, _, ev = m.debug_power("bombs", "spawn")
        self.assertTrue(ok)
        self.assertEqual(m.powers.pickup.power, "bombs")
        ok, _, ev = m.debug_power("grow", "p1")
        self.assertTrue(ok and ("p1", "size") in m.powers.effects)
        ok, _, _ = m.debug_power("volar", "p0")
        self.assertFalse(ok)
        self.assertIn("freeze_self", POWERS_BY_ID)


if __name__ == "__main__":
    unittest.main()
