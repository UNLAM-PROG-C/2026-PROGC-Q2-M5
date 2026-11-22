"""Powers: activation, receiver, expiration, replacement, pause, cleanup."""
import random
import unittest

import helpers
from fdc import config
from fdc import protocol
from fdc.sim import powers

ARENA = config.Arena
RULES = config.PowerRules
DT = config.PHYSICS_DT
EPSILON = 1e-6
MAX_STEP_PX = 8.0       # px a player may move in one step (no teleport)
run = helpers.run
count = helpers.count
playing_match = helpers.playing_match


def put_pickup_on_ball(m, power):
  m.powers.pickup = powers.Pickup(99, power, m.ball.x, m.ball.y)


def quiet(m):
  """Ball still and far from everything, players moved aside."""
  m.players[0].x, m.players[1].x = 250.0, 1030.0
  m.ball.x, m.ball.y = 640.0, ARENA.FLOOR_Y - m.ball.radius


def quiet_match(**kw):
  m = playing_match(**kw)
  quiet(m)
  return m


def activate(m, power, receiver, events=None):
  m.powers.activate(power, receiver, m, 0, 0,
                    [] if events is None else events)


class ActivationTest(unittest.TestCase):
  def test_personal_not_consumed_without_last_touch(self):
    m = quiet_match()
    put_pickup_on_ball(m, "speed_up")
    ev = run(m, 0.2)
    self.assertIsNotNone(m.powers.pickup)
    self.assertEqual(count(ev, protocol.EV_POWER), 0)

  def test_global_consumed_without_last_touch(self):
    m = quiet_match()
    put_pickup_on_ball(m, "big_ball")
    ev = run(m, 0.1)
    self.assertIsNone(m.powers.pickup)
    self.assertEqual(count(ev, protocol.EV_POWER), 1)
    self.assertIn(("ball", "radius"), m.powers.effects)

  def test_receptor_is_last_toucher(self):
    m = quiet_match()
    m.last_touch = 1
    put_pickup_on_ball(m, "speed_up")
    ev = run(m, 0.1)
    power = [e for e in ev if e[0] == protocol.EV_POWER][0][1]
    self.assertEqual(power["receptor"], 1)
    self.assertEqual(power["targets"], ["p1"])
    self.assertAlmostEqual(m.players[1].speed_mult, 1.35)
    self.assertEqual(m.players[0].speed_mult, 1.0)

  def test_rival_targets(self):
    m = playing_match()
    activate(m, "freeze_rival", 0)
    self.assertTrue(m.players[1].frozen)
    self.assertFalse(m.players[0].frozen)
    activate(m, "injured_rival", 1)
    self.assertTrue(m.players[0].no_kick)
    activate(m, "big_goal", 0)          # P1 attacks the right goal
    self.assertAlmostEqual(m.goals[1].target_height,
                           ARENA.GOAL_HEIGHT * 1.35)
    self.assertEqual(m.goals[0].target_height, ARENA.GOAL_HEIGHT)
    activate(m, "small_goal", 1)        # P2 attacks the left one
    self.assertAlmostEqual(m.goals[0].target_height,
                           ARENA.GOAL_HEIGHT * 0.75)

  def test_confusion_pickup_reverses_only_the_rivals_walk(self):
    m = quiet_match()
    m.last_touch = 0
    put_pickup_on_ball(m, "confusion")
    self.assertEqual(count(run(m, DT), protocol.EV_POWER), 1)
    for i in range(len(m.players)):
      m.set_input(i, False, True, 0, 0)
    run(m, DT)
    self.assertGreater(m.players[0].vx, 0)
    self.assertLess(m.players[1].vx, 0)

  def test_all_twenty_powers(self):
    self.assertEqual(len(config.POWERS), 20)
    for pdef in config.POWERS:
      for receptor in (0, 1):
        self.check_power(pdef, receptor)

  def check_power(self, pdef, receptor):
    m = playing_match()
    ev = []
    activate(m, pdef.id, receptor, ev)
    self.assertEqual(count(ev, protocol.EV_POWER), 1, pdef.id)
    if pdef.prop == "bomb":
      self.assertEqual(len(m.powers.bombs), 1)
    else:
      self.assertEqual(len(m.powers.effects), 1, pdef.id)
    run(m, 0.5)   # it applies without errors


class DurationTest(unittest.TestCase):
  def test_expiration_restores_base(self):
    m = quiet_match()
    activate(m, "speed_up", 0)
    activate(m, "grow", 0)
    ev = run(m, 6.1)
    self.assertEqual(count(ev, protocol.EV_POWER_EXPIRED), 2)
    self.assertEqual(m.powers.effects, {})
    self.assertEqual(m.players[0].speed_mult, 1.0)
    run(m, 0.5)
    self.assertEqual(m.players[0].scale, 1.0)

  def test_opposite_effect_replaces(self):
    m = playing_match()
    activate(m, "speed_up", 0)
    activate(m, "speed_down", 0)
    self.assertEqual(len(m.powers.effects), 1)
    # From the base value.
    self.assertAlmostEqual(m.players[0].speed_mult, 0.65)
    activate(m, "big_ball", None)
    activate(m, "small_ball", None)
    self.assertAlmostEqual(m.ball.target_radius,
                           config.BallSpec.RADIUS * 0.70)

  def test_repeat_renews_without_stacking(self):
    m = playing_match()
    activate(m, "speed_up", 0)
    run(m, 4.0)
    activate(m, "speed_up", 0)
    eff = m.powers.effects[("p0", "speed")]
    self.assertAlmostEqual(eff.left, 6.0)
    self.assertAlmostEqual(m.players[0].speed_mult, 1.35)

  def test_different_properties_coexist(self):
    m = playing_match()
    for power in ("speed_up", "jump_down", "low_bounce"):
      activate(m, power, 0)
    self.assertEqual(len(m.powers.effects), 3)
    self.assertAlmostEqual(m.players[0].jump_mult, 0.75)
    self.assertAlmostEqual(m.ball.bounce_mult, 0.45)

  def test_pause_freezes_timers(self):
    m = quiet_match(spawn_powers=True)
    activate(m, "speed_up", 0)
    activate(m, "bombs", 0)
    m.powers.pickup = powers.Pickup(5, "grow", 300, 300)
    spawn = m.powers.spawn_timer
    m.pause()
    run(m, 5.0)
    self.assertAlmostEqual(m.powers.effects[("p0", "speed")].left, 6.0)
    self.assertAlmostEqual(m.powers.bombs[0].fuse, RULES.BOMB_WARNING)
    self.assertAlmostEqual(m.powers.pickup.ttl, RULES.PICKUP_TTL)
    self.assertAlmostEqual(m.powers.spawn_timer, spawn)


class SpawnTest(unittest.TestCase):
  def test_spawn_interval_single_pickup_and_ttl(self):
    m = quiet_match(seed=3, spawn_powers=True)
    m.ball.y = 120.0   # far from any object, without touching it
    seen, first_at = self.watch_spawns(m)
    self.assertGreaterEqual(seen, 2)
    assert first_at is not None
    self.assertAlmostEqual(first_at, RULES.SPAWN_INTERVAL, delta=DT)

  def watch_spawns(self, m):
    """20 s with the ball held up high: (spawns, time of the first)."""
    seen, first_at = 0, None
    for i in range(int(20 / DT)):
      m.ball.x, m.ball.y, m.ball.vx, m.ball.vy = 640.0, 60.0, 0.0, 0.0
      for e in m.step(DT):
        if e[0] == protocol.EV_POWER_SPAWN:
          seen += 1
          first_at = first_at or i * DT
          pk = m.powers.pickup
          self.assertTrue(powers.position_is_free(pk.x, pk.y, m))
      self.assertLessEqual(1 if m.powers.pickup else 0, 1)
    return seen, first_at

  def test_pickup_expires(self):
    m = quiet_match()
    m.powers.pickup = powers.Pickup(5, "grow", 300, 300)
    ev = run(m, RULES.PICKUP_TTL + 0.1)
    self.assertEqual(count(ev, protocol.EV_PICKUP_EXPIRED), 1)
    self.assertIsNone(m.powers.pickup)

  def test_the_pickup_lasts_eight_seconds(self):
    """The card asked for 2 s more: it used to last 6 s on the pitch."""
    self.assertAlmostEqual(RULES.PICKUP_TTL, 8.0)

  def test_the_pickup_is_still_there_after_the_extra_time(self):
    m = quiet_match()
    m.powers.pickup = powers.Pickup(5, "grow", 300, 300)
    ev = run(m, RULES.PICKUP_TTL - 0.6)
    self.assertEqual(count(ev, protocol.EV_PICKUP_EXPIRED), 0)
    self.assertIsNotNone(m.powers.pickup)
    ev = run(m, 0.8)
    self.assertEqual(count(ev, protocol.EV_PICKUP_EXPIRED), 1)


def positions(m, p, seconds):
  """x of player p after each step during that many seconds."""
  xs = []
  for _ in range(int(seconds / DT)):
    m.step(DT)
    xs.append(p.x)
  return xs


class SpawnHeightTest(unittest.TestCase):
  """1.0.2: half of the pickups on the floor, half between the floor
    and 180 px, with a named interval between pickups."""

  ROLLS = 4000            # pickups rolled to measure the share
  SHARE_TOL = 0.05        # the share of the floor must be 0.5 more or less

  def test_half_of_the_pickups_appear_on_the_floor(self):
    rng = random.Random(20261108)
    heights = [powers.spawn_height(rng) for _ in range(self.ROLLS)]
    floor = [y for y in heights if y == RULES.SPAWN_FLOOR_Y]
    self.assertAlmostEqual(len(floor) / self.ROLLS,
                           RULES.SPAWN_FLOOR_SHARE, delta=self.SHARE_TOL)

  def test_the_other_half_appears_between_the_floor_and_180_px(self):
    rng = random.Random(20261108)
    low, high = ARENA.FLOOR_Y - 180, ARENA.FLOOR_Y - 60
    air = [powers.spawn_height(rng) for _ in range(self.ROLLS)]
    air = [y for y in air if y != RULES.SPAWN_FLOOR_Y]
    self.assertTrue(air)
    self.assertGreaterEqual(min(air), low - EPSILON)
    self.assertLessEqual(max(air), high + EPSILON)
    self.assertAlmostEqual((min(air) + max(air)) / 2, (low + high) / 2,
                           delta=5.0)

  def test_the_floor_pickup_is_reached_by_the_rolling_ball(self):
    m = quiet_match()
    y = RULES.SPAWN_FLOOR_Y
    m.powers.pickup = powers.Pickup(9, "big_ball", 640.0, y)
    m.ball.x, m.ball.y = 640.0 - 120.0, ARENA.FLOOR_Y - m.ball.radius
    m.ball.vx = 400.0
    ev = run(m, 0.4)
    self.assertIsNone(m.powers.pickup)
    self.assertEqual(count(ev, protocol.EV_POWER), 1)

  def test_the_floor_pickup_is_inside_the_pitch(self):
    self.assertEqual(powers.position_is_free(
        ARENA.WIDTH / 2, RULES.SPAWN_FLOOR_Y, quiet_match()), True)

  def test_spawn_interval_is_clamped_to_four_seconds(self):
    rng = random.Random(7)
    self.assertAlmostEqual(powers.PowerManager(rng).spawn_timer, 4.0)


def hold_right_and_press(m, i):
  """Inputs of run(): P1 holds right and presses jump and kick."""
  m.set_input(0, False, True, 1 + i, 1 + i)


class EffectBehaviourTest(unittest.TestCase):
  def test_confusion_expiration_restores_the_rivals_walk(self):
    m = quiet_match()
    target = m.players[1]
    activate(m, "confusion", 0)
    duration = config.POWERS_BY_ID["confusion"].duration
    run(m, duration + DT)
    m.set_input(target.idx, False, True, 0, 0)
    run(m, DT)
    self.assertGreater(target.vx, 0)

  def test_frozen_keeps_gravity_blocks_actions(self):
    m = playing_match()
    p = m.players[0]
    p.y = ARENA.FLOOR_Y - 100
    p.on_ground = False
    activate(m, "freeze_self", 0)
    x0 = p.x
    ev = run(m, 1.0, hold_right_and_press)
    self.assertTrue(p.on_ground)                 # it fell by gravity
    # It did not move on purpose.
    self.assertAlmostEqual(p.x, x0, delta=0.5)
    self.assertLess(p.kick_t, 0)
    self.assertGreaterEqual(count(ev, protocol.EV_KICK_BLOCKED), 1)

  def test_injured_can_jump_not_kick(self):
    m = playing_match()
    activate(m, "injured_self", 0)
    m.set_input(0, False, False, 1, 1)
    ev = run(m, 0.1)
    self.assertLess(m.players[0].vy, 0)
    self.assertEqual(count(ev, protocol.EV_KICK), 0)
    self.assertEqual(count(ev, protocol.EV_KICK_BLOCKED), 1)

  def test_size_changes_collision_gradually(self):
    m = quiet_match()
    activate(m, "grow", 0)
    m.step(DT)
    self.assertLess(m.players[0].scale, 1.05)    # not a sudden jump
    run(m, RULES.SIZE_TRANSITION + 0.05)
    self.assertAlmostEqual(m.players[0].head()[2],
                           config.PlayerSpec.HEAD_RADIUS * 1.25)

  def test_bomb_pushes_without_changing_last_touch(self):
    m = quiet_match()
    m.last_touch = 1
    activate(m, "bombs", 0)
    bomb = m.powers.bombs[0]
    self.assertTrue(RULES.BOMB_ZONE_X[0] <= bomb.x <= RULES.BOMB_ZONE_X[1])
    m.ball.x = bomb.x + 60
    m.ball.y = ARENA.FLOOR_Y - m.ball.radius
    self.check_blast(m)

  def check_blast(self, m):
    run(m, RULES.BOMB_WARNING - 0.05)
    self.assertEqual(len(m.powers.bombs), 1)     # 1 s warning
    ev = run(m, 0.1)
    self.assertEqual(count(ev, protocol.EV_BOMB_EXPLODE), 1)
    self.assertLess(m.ball.vy, -200)
    self.assertEqual(m.last_touch, 1)
    self.assertEqual(m.score, [0, 0])

  def test_grown_player_under_small_goal_is_released(self):
    m = playing_match()
    p = m.players[0]
    p.x = 40.0                           # inside its own goal
    activate(m, "grow", 0)
    activate(m, "small_goal", 1)         # shrinks the goal of P1
    xs = positions(m, p, 1.5)
    jumps = max(abs(b - a) for a, b in zip(xs, xs[1:]))
    self.assertLessEqual(jumps, MAX_STEP_PX + EPSILON)   # no teleports
    _, _, x1, y1 = m.goals[0].bar_rect()
    self.assertTrue(p.x - p.half_width() >= x1 - 0.5
                    or p.y - p.height() >= y1 - 0.5)

  def test_debug_power_modes(self):
    m = playing_match()
    ok, _, _ = m.debug_power("bombs", "spawn")
    self.assertTrue(ok)
    self.assertEqual(m.powers.pickup.power, "bombs")
    ok, _, _ = m.debug_power("grow", "p1")
    self.assertTrue(ok and ("p1", "size") in m.powers.effects)
    ok, _, _ = m.debug_power("fly", "p0")
    self.assertFalse(ok)
    self.assertIn("freeze_self", config.POWERS_BY_ID)


if __name__ == "__main__":
  unittest.main()
