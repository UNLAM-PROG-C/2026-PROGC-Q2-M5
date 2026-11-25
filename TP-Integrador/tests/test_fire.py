"""The fire power: the ball burns the first player who touches it.

Rules of 1.0.2: the first player who touches the burning ball (any team)
stays BURN_DURATION s without walking, jumping or kicking, and the ball goes
out on that touch. If nobody touches it, it goes out on its own after the 6 s
of the power, as before.
"""
import unittest

import helpers
from fdc import config
from fdc import protocol
from fdc.sim import physics

ARENA = config.Arena
RULES = config.PowerRules
DT = config.PHYSICS_DT
play = helpers.playing_match
run = helpers.run
count = helpers.count
# px: the ball does not move this far in a step of a burnt player.
STILL = 1.0


def burning_match():
  """Match in play with the ball on fire."""
  m = play(spawn_powers=False)
  m.players[0].x, m.players[1].x = 250.0, 1030.0
  m.powers.activate("fire", 0, m, 0, 0, [])
  return m


def on_the_player(m, idx=0):
  """Puts the ball against the body of player `idx` (a touch)."""
  player = m.players[idx]
  m.ball.x = player.x
  m.ball.y = player.y - config.PlayerSpec.BODY_OFFSET_Y
  m.ball.vx = m.ball.vy = 0.0


def away_from_the_players(m):
  """Ball still in the middle, far from both players."""
  m.ball.x, m.ball.y = 640.0, ARENA.FLOOR_Y - m.ball.radius
  m.ball.vx = m.ball.vy = 0.0


def burns(events):
  """Payloads of the burn events."""
  return [payload for kind, payload in events if kind == protocol.EV_BURN]


class FireTest(unittest.TestCase):
  def test_the_first_touch_burns_and_puts_the_ball_out(self):
    m = burning_match()
    on_the_player(m, 0)
    ev = run(m, DT)
    burned = burns(ev)
    self.assertEqual(len(burned), 1)
    self.assertEqual(burned[0]["player"], 0)
    self.assertAlmostEqual(burned[0]["seconds"], RULES.BURN_DURATION)
    self.assertNotIn(("ball", "fire"), m.powers.effects)
    self.assertTrue(m.players[0].burned)
    self.assertFalse(m.players[1].burned)

  def test_the_role_does_not_matter(self):
    """Whoever touches it burns, of any team."""
    m = burning_match()
    on_the_player(m, 1)
    ev = run(m, DT)
    self.assertEqual(burns(ev)[0]["player"], 1)
    self.assertTrue(m.players[1].burned)
    self.assertFalse(m.players[0].burned)

  def test_the_second_touch_does_nothing(self):
    m = burning_match()
    on_the_player(m, 0)
    ev = run(m, DT)
    away_from_the_players(m)
    on_the_player(m, 1)
    ev += run(m, DT)
    self.assertEqual(len(burns(ev)), 1)
    self.assertFalse(m.players[1].burned)

  def test_the_burn_lasts_two_seconds(self):
    m = burning_match()
    on_the_player(m, 0)
    run(m, DT)
    run(m, RULES.BURN_DURATION - 3 * DT)
    self.assertTrue(m.players[0].burned)
    run(m, 4 * DT)
    self.assertFalse(m.players[0].burned)
    self.assertEqual(m.players[0].burned_left, 0.0)

  def test_the_burned_player_cannot_walk_jump_or_kick(self):
    m = burning_match()
    on_the_player(m, 0)
    run(m, DT)
    x0 = m.players[0].x
    ev = run(m, 0.2, inputs=_hold_right_and_press)
    player = m.players[0]
    self.assertAlmostEqual(player.x, x0, delta=STILL)
    self.assertTrue(player.on_ground)
    self.assertEqual(count(ev, protocol.EV_KICK), 0)

  def test_nobody_touches_it_and_the_ball_goes_out(self):
    m = burning_match()
    away_from_the_players(m)
    run(m, config.POWERS_BY_ID["fire"].duration + 2 * DT)
    self.assertNotIn(("ball", "fire"), m.powers.effects)
    self.assertFalse(m.players[0].burned)
    self.assertFalse(m.players[1].burned)

  def test_the_state_carries_the_burn(self):
    m = burning_match()
    on_the_player(m, 0)
    run(m, DT)
    state = m.snapshot(1)
    mine, rival = state["players"]
    self.assertTrue(mine["burned"])
    self.assertFalse(rival["burned"])
    self.assertGreater(mine["burned_left"], 0.0)
    self.assertLessEqual(mine["burned_left"], RULES.BURN_DURATION)
    self.assertEqual([e["prop"] for e in state["effects"]], ["burned"])


def _hold_right_and_press(m, step):
  """Controls of the test: run right and press jump and kick."""
  del step  # Unused.
  m.set_input(0, False, True, 1, 1)


class BurntPhysicsTest(unittest.TestCase):
  """The player of the simulation with the burn flag on."""

  def test_control_player_ignores_the_controls(self):
    p = physics.Player(0)
    p.burned = True
    x0 = p.x
    for _ in range(6):
      physics.control_player(p, DT, 1, True, True, [])
      physics.integrate_player(p, DT, [])
    self.assertAlmostEqual(p.x, x0, delta=STILL)
    self.assertTrue(p.on_ground)
    self.assertEqual(p.kick_t, -1.0)


if __name__ == "__main__":
  unittest.main()
