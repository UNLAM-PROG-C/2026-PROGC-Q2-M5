"""Partido: goles, reloj, controles y física (sin procesos)."""
import math
import unittest

from helpers import P, PHYSICS_DT, count, playing_match, run
from fdc.config import Arena, BallSpec, MatchRules, PlayerSpec
from fdc.sim.match import Match


def park_players(m):
    """Aleja a los jugadores de la zona de la jugada."""
    m.players[0].x, m.players[1].x = 500.0, 780.0


class GoalTest(unittest.TestCase):
    def test_valid_goal_counts_once(self):
        m = playing_match()
        park_players(m)
        g = m.goals[0]
        m.ball.x, m.ball.y = g.mouth_x + 60, Arena.FLOOR_Y - 60
        m.ball.vx, m.ball.vy = -700, 0
        ev = run(m, 1.0)
        self.assertEqual(count(ev, P.EV_GOAL), 1)
        self.assertEqual(m.score, [0, 1])          # arco izquierdo -> punto de J2
        self.assertEqual(m.phase, P.PHASE_GOAL)
        # la pelota sigue dentro durante la celebración: no suma otra vez
        ev = run(m, MatchRules.GOAL_CELEBRATION - 1.1)
        self.assertEqual(count(ev, P.EV_GOAL), 0)
        self.assertEqual(m.score, [0, 1])

    def test_reset_after_goal(self):
        m = playing_match()
        park_players(m)
        m.last_touch = 0
        m.powers.activate("speed_up", 0, m, 0, 0, [])
        m.powers.activate("bombs", 0, m, 0, 0, [])
        m.ball.x, m.ball.y = Arena.WIDTH - Arena.GOAL_DEPTH - 50, Arena.FLOOR_Y - 60
        m.ball.vx = 800
        run(m, MatchRules.GOAL_CELEBRATION + 0.2)
        self.assertEqual(m.score, [1, 0])
        self.assertEqual(m.phase, P.PHASE_COUNTDOWN)
        self.assertIsNone(m.last_touch)
        self.assertEqual(m.powers.effects, {})
        self.assertEqual(m.powers.bombs, [])
        self.assertIsNone(m.powers.pickup)
        self.assertEqual((m.ball.x, m.ball.y), tuple(map(float, BallSpec.SPAWN)))
        self.assertEqual(m.players[0].x, PlayerSpec.SPAWN_X[0])
        self.assertEqual(m.players[0].speed_mult, 1.0)

    def test_partial_crossing_is_not_goal(self):
        m = playing_match()
        park_players(m)
        g = m.goals[0]
        m.ball.x = g.mouth_x - m.ball.radius + 6      # la mayor parte adentro, no toda
        m.ball.y = Arena.FLOOR_Y - m.ball.radius
        ev = run(m, 1.0)
        self.assertEqual(count(ev, P.EV_GOAL), 0)

    def test_ball_over_crossbar_is_not_goal(self):
        m = playing_match()
        park_players(m)
        g = m.goals[0]
        m.ball.x, m.ball.y = g.mouth_x + 40, g.bar_y() - 120
        m.ball.vx, m.ball.vy = -500, 0
        ev = run(m, 1.5)
        self.assertEqual(count(ev, P.EV_GOAL), 0)
        # quedó arriba del travesaño o volvió a la cancha por la punta, nunca adentro
        self.assertFalse(g.ball_inside(m.ball))
        self.assertTrue(m.ball.y < g.bar_y() or m.ball.x > g.mouth_x)

    def test_shrinking_ball_on_line_is_not_goal(self):
        m = playing_match()
        park_players(m)
        g = m.goals[0]
        m.ball.x = g.mouth_x - m.ball.radius + 4
        m.ball.y = Arena.FLOOR_Y - m.ball.radius
        m.powers.activate("small_ball", None, m, 0, 0, [])
        ev = run(m, 1.0)
        self.assertEqual(count(ev, P.EV_GOAL), 0)

    def test_ball_on_crossbar_rolls_back_to_field(self):
        m = playing_match()
        park_players(m)
        g = m.goals[0]
        m.ball.x = 30.0
        m.ball.y = g.bar_y() - Arena.BAR_THICKNESS / 2 - m.ball.radius
        run(m, 3.0)
        self.assertGreater(m.ball.x, g.mouth_x)       # volvió a estar en juego
        self.assertEqual(m.score, [0, 0])

    def test_fast_ball_does_not_tunnel_crossbar(self):
        for side in (0, 1):
            m = playing_match()
            park_players(m)
            g = m.goals[side]
            x = 40 if side == 0 else Arena.WIDTH - 40
            m.ball.x, m.ball.y = x, g.bar_y() - 200
            m.ball.vx, m.ball.vy = 0, BallSpec.MAX_SPEED
            for _ in range(60):
                m.step(PHYSICS_DT)
                self.assertLess(m.ball.y, g.bar_y(), "la pelota atravesó el travesaño")
            self.assertEqual(m.score, [0, 0])


class PhysicsTest(unittest.TestCase):
    def test_ball_does_not_tunnel_through_head(self):
        m = playing_match()
        m.players[0].x = 150.0
        p = m.players[1]
        p.x = 700.0
        hx, hy, _ = p.head()
        m.ball.x, m.ball.y = 480, hy
        m.ball.vx, m.ball.vy = BallSpec.MAX_SPEED, 0
        run(m, 0.2)
        self.assertLess(m.ball.x, p.x)
        self.assertEqual(m.last_touch, 1)

    def test_speed_is_capped(self):
        m = playing_match()
        m.ball.vx, m.ball.vy = 9000, -9000
        m.step(PHYSICS_DT)
        self.assertLessEqual(math.hypot(m.ball.vx, m.ball.vy), BallSpec.MAX_SPEED + 1e-6)

    def test_players_do_not_pass_through(self):
        m = playing_match()

        def push(mm, i):
            mm.set_input(0, False, True, 0, 0)
            mm.set_input(1, True, False, 0, 0)
        run(m, 4.0, push)
        a, b = m.players
        self.assertLess(a.x, b.x)
        self.assertGreater(b.x - a.x, PlayerSpec.HEAD_RADIUS)

    def test_can_stand_on_head_and_fall_when_other_moves(self):
        m = playing_match()
        a, b = m.players
        a.x = b.x = 640.0
        a.y = Arena.FLOOR_Y - 180
        a.on_ground = False
        run(m, 1.0)
        self.assertEqual(a.on_head, 1)                  # la cabeza del otro es piso
        self.assertTrue(a.on_ground)
        self.assertLess(a.y, Arena.FLOOR_Y - PlayerSpec.HEAD_OFFSET_Y)

        def walk(mm, i):
            mm.set_input(1, False, True, 0, 0)          # el de abajo se corre
        run(m, 1.0, walk)
        self.assertIsNone(a.on_head)
        self.assertEqual(a.y, Arena.FLOOR_Y)            # cayó al piso: nadie queda trabado

    def test_jump_from_head_reaches_crossbar(self):
        m = playing_match()
        a, b = m.players
        g = m.goals[0]
        b.x = g.mouth_x + 110.0
        a.x, a.y, a.on_ground = b.x, Arena.FLOOR_Y - 200, False
        run(m, 0.6)
        self.assertEqual(a.on_head, 1)
        m.set_input(0, False, False, 0, 0)
        m.set_input(0, True, False, 1, 0)               # salta hacia el arco
        on_bar = False
        for _ in range(int(1.5 / PHYSICS_DT)):
            m.set_input(0, True, False, 0, 0)
            m.step(PHYSICS_DT)
            x0, y0, x1, y1 = g.bar_rect()
            if a.on_ground and abs(a.y - y0) < 0.5:
                on_bar = True
                break
        self.assertTrue(on_bar, "no llegó a subirse al travesaño")

    def test_floor_jump_does_not_reach_crossbar(self):
        m = playing_match()
        p = m.players[0]
        g = m.goals[0]
        p.x = 50.0                                      # adentro del arco
        m.set_input(0, False, False, 0, 0)
        m.set_input(0, False, False, 1, 0)
        top = Arena.FLOOR_Y
        for _ in range(int(1.0 / PHYSICS_DT)):
            m.step(PHYSICS_DT)
            top = min(top, p.y - p.height())
        self.assertGreater(top, g.bar_rect()[3])        # la cabeza nunca toca el travesaño

    def test_goal_counts_with_player_inside_goal(self):
        m = playing_match()
        g = m.goals[0]
        keeper = m.players[0]
        keeper.x = keeper.half_width() + 1              # escondido al fondo del arco
        m.players[1].x = 900.0
        m.ball.x, m.ball.y = g.mouth_x + 60, Arena.FLOOR_Y - 40
        m.ball.vx, m.ball.vy = -600, 0
        ev = run(m, 1.0)
        self.assertEqual(count(ev, P.EV_GOAL), 1)

    def test_wall_bounce_keeps_last_touch(self):
        m = playing_match()
        park_players(m)
        m.last_touch = 0
        m.ball.x, m.ball.y = 400, 200
        m.ball.vx, m.ball.vy = -1200, 0
        run(m, 1.0)
        self.assertEqual(m.last_touch, 0)

    def test_simultaneous_contact_rule(self):
        m = playing_match()
        m._resolve_last_touch([(0, "body", 300.0), (1, "kick", 100.0)])
        self.assertEqual(m.last_touch, 1)              # patada > cuerpo
        m._resolve_last_touch([(0, "head", 500.0), (1, "head", 200.0)])
        self.assertEqual(m.last_touch, 0)              # mayor impacto
        m._resolve_last_touch([(0, "head", 200.0), (1, "head", 200.0)])
        self.assertEqual(m.last_touch, 0)              # empate: se conserva


class ControlsTest(unittest.TestCase):
    def test_one_kick_per_press(self):
        m = playing_match()
        m.set_input(0, False, False, 0, 0)   # base de contadores (la hace el servidor)
        m.set_input(0, False, False, 0, 1)   # una pulsación, luego "mantenida"
        ev = run(m, 1.5)
        self.assertEqual(sum(1 for e in ev if e[0] == P.EV_KICK and e[1]["player"] == 0), 1)

    def test_kick_cooldown(self):
        m = playing_match()
        m.set_input(0, False, False, 0, 1)
        run(m, 0.05)
        m.set_input(0, False, False, 0, 1)   # durante la recuperación: se descarta
        ev = run(m, 0.6)
        m.set_input(0, False, False, 0, 1)   # después de la recuperación: vale
        ev += run(m, 0.3)
        self.assertEqual(sum(1 for e in ev if e[0] == P.EV_KICK and e[1]["player"] == 0), 1)

    def test_no_double_jump(self):
        m = playing_match()
        p = m.players[0]
        m.set_input(0, False, False, 1, 0)
        run(m, 0.15)
        self.assertLess(p.vy, 0)
        vy_before = p.vy
        m.set_input(0, False, False, 1, 0)   # segunda pulsación en el aire
        m.step(PHYSICS_DT)
        self.assertGreater(p.vy, vy_before)  # sólo actuó la gravedad
        run(m, 1.0)
        self.assertTrue(p.on_ground)

    def test_presses_outside_play_are_ignored(self):
        m = Match(1, seed=1)                 # en cuenta regresiva
        m.set_input(0, False, False, 1, 1)
        run(m, MatchRules.KICKOFF_COUNTDOWN + 0.3)
        self.assertTrue(m.players[0].on_ground)
        self.assertLess(m.players[0].kick_t, 0)


class ClockTest(unittest.TestCase):
    def test_clock_stops_in_countdown_pause_and_celebration(self):
        m = Match(1, seed=1)
        m.powers.spawn_timer = 1e9
        run(m, MatchRules.KICKOFF_COUNTDOWN - 0.1)
        self.assertEqual(m.clock, MatchRules.DURATION)
        run(m, 1.1)
        played = MatchRules.DURATION - m.clock
        self.assertAlmostEqual(played, 1.0, delta=0.05)
        m.pause()
        run(m, 5.0)
        self.assertAlmostEqual(MatchRules.DURATION - m.clock, played, delta=1e-9)
        m.resume()
        self.assertEqual(m.phase, P.PHASE_COUNTDOWN)
        run(m, MatchRules.RESUME_COUNTDOWN - 0.1)
        self.assertAlmostEqual(MatchRules.DURATION - m.clock, played, delta=1e-9)
        m.phase = P.PHASE_GOAL
        m.phase_left = 1.0
        run(m, 0.9)
        self.assertAlmostEqual(MatchRules.DURATION - m.clock, played, delta=1e-9)

    def test_match_end_draw_and_win(self):
        m = playing_match()
        m.clock = 0.05
        ev = run(m, 0.5)
        self.assertEqual(count(ev, P.EV_MATCH_END), 1)
        self.assertEqual(m.phase, P.PHASE_FINISHED)
        self.assertIsNone(m.winner)
        m = playing_match()
        m.score = [2, 1]
        m.clock = 0.05
        ev = run(m, 0.5)
        end = [e for e in ev if e[0] == P.EV_MATCH_END][0][1]
        self.assertEqual(end["winner"], 0)


class GoldenGoalTest(unittest.TestCase):
    def test_tie_goes_to_golden_goal_and_next_goal_wins(self):
        m = Match(1, seed=1, golden_goal=True)
        m.phase, m.phase_left = P.PHASE_PLAYING, 0.0
        m.powers.spawn_timer = 1e9
        m.score = [1, 1]
        m.clock = 0.05
        ev = run(m, 0.2)
        self.assertEqual(count(ev, P.EV_GOLDEN_GOAL), 1)
        self.assertEqual(count(ev, P.EV_MATCH_END), 0)
        self.assertTrue(m.golden)
        self.assertEqual(m.phase, P.PHASE_COUNTDOWN)       # saque nuevo
        run(m, MatchRules.GOLDEN_GOAL_COUNTDOWN + 5.0)
        self.assertNotEqual(m.phase, P.PHASE_FINISHED)     # sin gol, no termina por tiempo
        self.assertEqual(m.clock, 0.0)
        g = m.goals[0]
        m.players[0].x, m.players[1].x = 500.0, 800.0
        m.ball.x, m.ball.y, m.ball.vx, m.ball.vy = g.mouth_x + 50, Arena.FLOOR_Y - 40, -700, 0
        ev = run(m, 1.0)
        self.assertEqual(count(ev, P.EV_GOAL), 1)
        ev = run(m, MatchRules.GOAL_CELEBRATION + 0.2)
        end = [e for e in ev if e[0] == P.EV_MATCH_END]
        self.assertEqual(len(end), 1)
        self.assertEqual(end[0][1]["winner"], 1)            # gol en el arco de J1 -> gana J2
        self.assertEqual(m.score, [1, 2])

    def test_without_golden_goal_tie_ends(self):
        m = playing_match()
        m.score = [2, 2]
        m.clock = 0.05
        ev = run(m, 0.2)
        self.assertEqual(count(ev, P.EV_GOLDEN_GOAL), 0)
        self.assertEqual(m.phase, P.PHASE_FINISHED)
        self.assertIsNone(m.winner)


class RobustnessTest(unittest.TestCase):
    def test_random_full_match_keeps_invariants(self):
        """Un partido completo con entradas pseudoaleatorias y poderes: nada se rompe."""
        import random
        rng = random.Random(42)
        m = Match(1, seed=42)
        counters = [[0, 0], [0, 0]]
        held = [[False, False], [False, False]]
        goals = 0
        events = []
        steps = int((MatchRules.KICKOFF_COUNTDOWN + MatchRules.DURATION + 40) / PHYSICS_DT)
        for _ in range(steps):
            for i in (0, 1):
                if rng.random() < 0.02:
                    held[i] = [rng.random() < 0.5, rng.random() < 0.5]
                if rng.random() < 0.01:
                    counters[i][0] += 1
                if rng.random() < 0.02:
                    counters[i][1] += 1
            for i in (0, 1):
                prev = getattr(m, "_prev", [[0, 0], [0, 0]])
                m.set_input(i, held[i][0], held[i][1], counters[i][0] - prev[i][0], counters[i][1] - prev[i][1])
            m._prev = [c[:] for c in counters]
            ev = m.step(PHYSICS_DT)
            events += ev
            b = m.ball
            for v in (b.x, b.y, b.vx, b.vy):
                self.assertFalse(math.isnan(v))
            self.assertTrue(-1 <= b.x - b.radius and b.x + b.radius <= Arena.WIDTH + 1)
            self.assertTrue(b.y + b.radius <= Arena.FLOOR_Y + 1)
            self.assertLessEqual(math.hypot(b.vx, b.vy), BallSpec.MAX_SPEED + 1e-6)
            for p in m.players:
                self.assertTrue(p.half_width() - 1 <= p.x <= Arena.WIDTH - p.half_width() + 1)
                self.assertLessEqual(p.y, Arena.FLOOR_Y + 1e-6)
            if m.phase == P.PHASE_FINISHED:
                break
        goals = count(events, P.EV_GOAL)
        self.assertEqual(m.phase, P.PHASE_FINISHED)
        self.assertEqual(sum(m.score), goals)            # un evento por gol, nada duplicado
        self.assertEqual(count(events, P.EV_MATCH_END), 1)
        self.assertGreater(count(events, P.EV_POWER_SPAWN), 3)


if __name__ == "__main__":
    unittest.main()
