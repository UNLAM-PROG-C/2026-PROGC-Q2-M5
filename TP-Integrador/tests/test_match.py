"""Match: goals, clock, controls and physics (no processes)."""
import math
import random
import unittest

import helpers
from fdc import config
from fdc import protocol
from fdc.sim import match

ARENA = config.Arena
BALL = config.BallSpec
PLAYER = config.PlayerSpec
RULES = config.MatchRules
DT = config.PHYSICS_DT
EPSILON = 1e-6
run = helpers.run
count = helpers.count


def park_players(m):
    """Moves the players away from the play zone."""
    m.players[0].x, m.players[1].x = 500.0, 780.0


def parked_match():
    m = helpers.playing_match()
    park_players(m)
    return m


def walk_right(m, i):
    """Inputs of run(): player 2 walks to the right."""
    del i  # Unused.
    m.set_input(1, False, True, 0, 0)


def kicks_of(events, player):
    return sum(1 for e in events
               if e[0] == protocol.EV_KICK and e[1]["player"] == player)


class GoalTest(unittest.TestCase):
    def test_valid_goal_counts_once(self):
        m = parked_match()
        g = m.goals[0]
        m.ball.x, m.ball.y = g.mouth_x + 60, ARENA.FLOOR_Y - 60
        m.ball.vx, m.ball.vy = -700, 0
        ev = run(m, 1.0)
        self.assertEqual(count(ev, protocol.EV_GOAL), 1)
        self.assertEqual(m.score, [0, 1])      # left goal -> point for P2
        self.assertEqual(m.phase, protocol.PHASE_GOAL)
        # The ball stays inside during the celebration: it does not add
        # another one.
        ev = run(m, RULES.GOAL_CELEBRATION - 1.1)
        self.assertEqual(count(ev, protocol.EV_GOAL), 0)
        self.assertEqual(m.score, [0, 1])

    def test_reset_after_goal(self):
        m = parked_match()
        m.last_touch = 0
        m.powers.activate("speed_up", 0, m, 0, 0, [])
        m.powers.activate("bombs", 0, m, 0, 0, [])
        m.ball.x = ARENA.WIDTH - ARENA.GOAL_DEPTH - 50
        m.ball.y = ARENA.FLOOR_Y - 60
        m.ball.vx = 800
        run(m, RULES.GOAL_HOLD + 0.2)
        self.assertEqual(m.score, [1, 0])
        self.assertEqual(m.phase, protocol.PHASE_COUNTDOWN)
        self.check_clean_kickoff(m)

    def check_clean_kickoff(self, m):
        self.assertIsNone(m.last_touch)
        self.assertEqual(m.powers.effects, {})
        self.assertEqual(m.powers.bombs, [])
        self.assertIsNone(m.powers.pickup)
        self.assertEqual((m.ball.x, m.ball.y), tuple(map(float, BALL.SPAWN)))
        self.assertEqual(m.players[0].x, PLAYER.SPAWN_X[0])
        self.assertEqual(m.players[0].speed_mult, 1.0)

    def test_partial_crossing_is_not_goal(self):
        m = parked_match()
        g = m.goals[0]
        # Most of the ball inside, not all of it.
        m.ball.x = g.mouth_x - m.ball.radius + 6
        m.ball.y = ARENA.FLOOR_Y - m.ball.radius
        ev = run(m, 1.0)
        self.assertEqual(count(ev, protocol.EV_GOAL), 0)

    def test_ball_over_crossbar_is_not_goal(self):
        m = parked_match()
        g = m.goals[0]
        m.ball.x, m.ball.y = g.mouth_x + 40, g.bar_y() - 120
        m.ball.vx, m.ball.vy = -500, 0
        ev = run(m, 1.5)
        self.assertEqual(count(ev, protocol.EV_GOAL), 0)
        # It stayed over the crossbar or went back to the pitch by its tip,
        # never inside.
        self.assertFalse(g.ball_inside(m.ball))
        self.assertTrue(m.ball.y < g.bar_y() or m.ball.x > g.mouth_x)

    def test_shrinking_ball_on_line_is_not_goal(self):
        m = parked_match()
        g = m.goals[0]
        m.ball.x = g.mouth_x - m.ball.radius + 4
        m.ball.y = ARENA.FLOOR_Y - m.ball.radius
        m.powers.activate("small_ball", None, m, 0, 0, [])
        ev = run(m, 1.0)
        self.assertEqual(count(ev, protocol.EV_GOAL), 0)

    def test_ball_on_crossbar_rolls_back_to_field(self):
        m = parked_match()
        g = m.goals[0]
        m.ball.x = 30.0
        m.ball.y = g.bar_y() - ARENA.BAR_THICKNESS / 2 - m.ball.radius
        run(m, 3.0)
        self.assertGreater(m.ball.x, g.mouth_x)        # in play again
        self.assertEqual(m.score, [0, 0])

    def test_fast_ball_does_not_tunnel_crossbar(self):
        for side in (0, 1):
            m = parked_match()
            g = m.goals[side]
            x = 40 if side == 0 else ARENA.WIDTH - 40
            m.ball.x, m.ball.y = x, g.bar_y() - 200
            m.ball.vx, m.ball.vy = 0, BALL.MAX_SPEED
            for _ in range(60):
                m.step(DT)
                self.assertLess(m.ball.y, g.bar_y(),
                                "the ball went through the crossbar")
            self.assertEqual(m.score, [0, 0])


class PhysicsTest(unittest.TestCase):
    def test_ball_does_not_tunnel_through_head(self):
        m = helpers.playing_match()
        m.players[0].x = 150.0
        p = m.players[1]
        p.x = 700.0
        hy = p.head()[1]
        m.ball.x, m.ball.y = 480, hy
        m.ball.vx, m.ball.vy = BALL.MAX_SPEED, 0
        run(m, 0.2)
        self.assertLess(m.ball.x, p.x)
        self.assertEqual(m.last_touch, 1)

    def test_speed_is_capped(self):
        m = helpers.playing_match()
        m.ball.vx, m.ball.vy = 9000, -9000
        m.step(DT)
        self.assertLessEqual(math.hypot(m.ball.vx, m.ball.vy),
                             BALL.MAX_SPEED + EPSILON)

    def test_players_do_not_pass_through(self):
        m = helpers.playing_match()

        def push(mm, i):
            del i  # Unused.
            mm.set_input(0, False, True, 0, 0)
            mm.set_input(1, True, False, 0, 0)
        run(m, 4.0, push)
        a, b = m.players
        self.assertLess(a.x, b.x)
        self.assertGreater(b.x - a.x, PLAYER.HEAD_RADIUS)

    def test_can_stand_on_head_and_fall_when_other_moves(self):
        m = helpers.playing_match()
        a, b = m.players
        a.x = b.x = 640.0
        a.y = ARENA.FLOOR_Y - 180
        a.on_ground = False
        run(m, 1.0)
        self.assertEqual(a.on_head, 1)        # the other head is a floor
        self.assertTrue(a.on_ground)
        self.assertLess(a.y, ARENA.FLOOR_Y - PLAYER.HEAD_OFFSET_Y)
        run(m, 1.0, walk_right)          # the one below moves away
        self.assertIsNone(a.on_head)
        # It fell to the floor: nobody is stuck.
        self.assertEqual(a.y, ARENA.FLOOR_Y)

    def test_jump_from_head_reaches_crossbar(self):
        m = helpers.playing_match()
        a, b = m.players
        g = m.goals[0]
        b.x = g.mouth_x + 110.0
        a.x, a.y, a.on_ground = b.x, ARENA.FLOOR_Y - 200, False
        run(m, 0.6)
        self.assertEqual(a.on_head, 1)
        m.set_input(0, False, False, 0, 0)
        m.set_input(0, True, False, 1, 0)      # jumps towards the goal
        self.assertTrue(self.climbs_bar(m, a, g),
                        "it did not get onto the crossbar")

    def climbs_bar(self, m, a, g):
        """Keeps walking left; True when standing on the crossbar."""
        for _ in range(int(1.5 / DT)):
            m.set_input(0, True, False, 0, 0)
            m.step(DT)
            y0 = g.bar_rect()[1]
            if a.on_ground and abs(a.y - y0) < 0.5:
                return True
        return False

    def test_floor_jump_does_not_reach_crossbar(self):
        m = helpers.playing_match()
        p = m.players[0]
        g = m.goals[0]
        p.x = 50.0                                   # inside the goal
        m.set_input(0, False, False, 0, 0)
        m.set_input(0, False, False, 1, 0)
        top = ARENA.FLOOR_Y
        for _ in range(int(1.0 / DT)):
            m.step(DT)
            top = min(top, p.y - p.height())
        # The head never touches the crossbar.
        self.assertGreater(top, g.bar_rect()[3])

    def test_goal_counts_with_player_inside_goal(self):
        m = helpers.playing_match()
        g = m.goals[0]
        keeper = m.players[0]
        # Hidden at the back of the goal.
        keeper.x = keeper.half_width() + 1
        m.players[1].x = 900.0
        m.ball.x, m.ball.y = g.mouth_x + 60, ARENA.FLOOR_Y - 40
        m.ball.vx, m.ball.vy = -600, 0
        ev = run(m, 1.0)
        self.assertEqual(count(ev, protocol.EV_GOAL), 1)

    def test_wall_bounce_keeps_last_touch(self):
        m = parked_match()
        m.last_touch = 0
        m.ball.x, m.ball.y = 400, 200
        m.ball.vx, m.ball.vy = -1200, 0
        run(m, 1.0)
        self.assertEqual(m.last_touch, 0)

    def test_simultaneous_contact_rule(self):
        m = helpers.playing_match()
        # pylint: disable=protected-access
        m._resolve_last_touch([(0, "body", 300.0), (1, "kick", 100.0)])
        self.assertEqual(m.last_touch, 1)              # kick > body
        m._resolve_last_touch([(0, "head", 500.0), (1, "head", 200.0)])
        self.assertEqual(m.last_touch, 0)              # stronger impact
        m._resolve_last_touch([(0, "head", 200.0), (1, "head", 200.0)])
        self.assertEqual(m.last_touch, 0)              # tie: it is kept


class ControlsTest(unittest.TestCase):
    def test_one_kick_per_press(self):
        m = helpers.playing_match()
        # Base of the counters (the server does it).
        m.set_input(0, False, False, 0, 0)
        m.set_input(0, False, False, 0, 1)   # one press, then "held"
        ev = run(m, 1.5)
        self.assertEqual(kicks_of(ev, 0), 1)

    def test_kick_cooldown(self):
        m = helpers.playing_match()
        m.set_input(0, False, False, 0, 1)
        run(m, 0.05)
        m.set_input(0, False, False, 0, 1)   # during the cooldown: dropped
        ev = run(m, 0.6)
        m.set_input(0, False, False, 0, 1)   # after the cooldown: valid
        ev += run(m, 0.3)
        self.assertEqual(kicks_of(ev, 0), 1)

    def test_no_double_jump(self):
        m = helpers.playing_match()
        p = m.players[0]
        m.set_input(0, False, False, 1, 0)
        run(m, 0.15)
        self.assertLess(p.vy, 0)
        vy_before = p.vy
        m.set_input(0, False, False, 1, 0)   # second press in the air
        m.step(DT)
        self.assertGreater(p.vy, vy_before)  # only gravity acted
        run(m, 1.0)
        self.assertTrue(p.on_ground)

    def test_presses_outside_play_are_ignored(self):
        m = match.Match(1, seed=1)           # in the countdown
        m.set_input(0, False, False, 1, 1)
        run(m, RULES.KICKOFF_COUNTDOWN + 0.3)
        self.assertTrue(m.players[0].on_ground)
        self.assertLess(m.players[0].kick_t, 0)


class ClockTest(unittest.TestCase):
    def played(self, m):
        return RULES.DURATION - m.clock

    def test_clock_stops_in_countdown_pause_and_celebration(self):
        m = match.Match(1, seed=1)
        m.powers.spawn_timer = helpers.NO_SPAWN
        run(m, RULES.KICKOFF_COUNTDOWN - 0.1)
        self.assertEqual(m.clock, RULES.DURATION)
        run(m, 1.1)
        played = self.played(m)
        self.assertAlmostEqual(played, 1.0, delta=0.05)
        m.pause()
        run(m, 5.0)
        self.assertAlmostEqual(self.played(m), played, delta=1e-9)
        self.check_stopped_after_resume(m, played)

    def check_stopped_after_resume(self, m, played):
        m.resume()
        self.assertEqual(m.phase, protocol.PHASE_COUNTDOWN)
        run(m, RULES.RESUME_COUNTDOWN - 0.1)
        self.assertAlmostEqual(self.played(m), played, delta=1e-9)
        m.phase = protocol.PHASE_GOAL
        m.phase_left = 1.0
        run(m, 0.9)
        self.assertAlmostEqual(self.played(m), played, delta=1e-9)

    def test_match_end_draw_and_win(self):
        m = helpers.playing_match()
        m.clock = 0.05
        ev = run(m, 0.5)
        self.assertEqual(count(ev, protocol.EV_MATCH_END), 1)
        self.assertEqual(m.phase, protocol.PHASE_FINISHED)
        self.assertIsNone(m.winner)
        m = helpers.playing_match()
        m.score = [2, 1]
        m.clock = 0.05
        ev = run(m, 0.5)
        end = [e for e in ev if e[0] == protocol.EV_MATCH_END][0][1]
        self.assertEqual(end["winner"], 0)


class GoldenGoalTest(unittest.TestCase):
    def test_tie_goes_to_golden_goal_and_next_goal_wins(self):
        m = helpers.playing_match()
        m.golden_goal = True
        m.score = [1, 1]
        m.clock = 0.05
        ev = run(m, 0.2)
        self.assertEqual(count(ev, protocol.EV_GOLDEN_GOAL), 1)
        self.assertEqual(count(ev, protocol.EV_MATCH_END), 0)
        self.assertTrue(m.golden)
        self.check_no_end_by_time(m)
        self.check_next_goal_wins(m)

    def check_no_end_by_time(self, m):
        self.assertEqual(m.phase, protocol.PHASE_COUNTDOWN)   # new kickoff
        run(m, RULES.GOLDEN_GOAL_COUNTDOWN + 5.0)
        # Without a goal it does not end by time.
        self.assertNotEqual(m.phase, protocol.PHASE_FINISHED)
        self.assertEqual(m.clock, 0.0)

    def check_next_goal_wins(self, m):
        g = m.goals[0]
        m.players[0].x, m.players[1].x = 500.0, 800.0
        m.ball.x, m.ball.y = g.mouth_x + 50, ARENA.FLOOR_Y - 40
        m.ball.vx, m.ball.vy = -700, 0
        ev = run(m, 1.0)
        self.assertEqual(count(ev, protocol.EV_GOAL), 1)
        ev = run(m, RULES.GOAL_HOLD + 0.2)
        end = [e for e in ev if e[0] == protocol.EV_MATCH_END]
        self.assertEqual(len(end), 1)
        # Goal in the goal of P1 -> P2 wins.
        self.assertEqual(end[0][1]["winner"], 1)
        self.assertEqual(m.score, [1, 2])

    def test_without_golden_goal_tie_ends(self):
        m = helpers.playing_match()
        m.score = [2, 2]
        m.clock = 0.05
        ev = run(m, 0.2)
        self.assertEqual(count(ev, protocol.EV_GOLDEN_GOAL), 0)
        self.assertEqual(m.phase, protocol.PHASE_FINISHED)
        self.assertIsNone(m.winner)


class RandomPlayers:
    """Pseudo random keys of both players (held keys and presses)."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.counters = [[0, 0], [0, 0]]
        self.held = [[False, False], [False, False]]
        self.prev = [[0, 0], [0, 0]]

    def press(self):
        rng = self.rng
        for i in (0, 1):
            if rng.random() < 0.02:
                self.held[i] = [rng.random() < 0.5, rng.random() < 0.5]
            if rng.random() < 0.01:
                self.counters[i][0] += 1
            if rng.random() < 0.02:
                self.counters[i][1] += 1

    def feed(self, m):
        for i in (0, 1):
            m.set_input(i, self.held[i][0], self.held[i][1],
                        self.counters[i][0] - self.prev[i][0],
                        self.counters[i][1] - self.prev[i][1])
        self.prev = [c[:] for c in self.counters]


class RobustnessTest(unittest.TestCase):
    def test_random_full_match_keeps_invariants(self):
        """A whole match with pseudo random inputs and powers: nothing
        breaks."""
        m = match.Match(1, seed=42)
        players = RandomPlayers(42)
        events = []
        steps = int((RULES.KICKOFF_COUNTDOWN + RULES.DURATION + 40) / DT)
        for _ in range(steps):
            players.press()
            players.feed(m)
            events += m.step(DT)
            self.check_invariants(m)
            if m.phase == protocol.PHASE_FINISHED:
                break
        self.assertEqual(m.phase, protocol.PHASE_FINISHED)
        self.check_events(m, events)

    def check_invariants(self, m):
        b = m.ball
        for v in (b.x, b.y, b.vx, b.vy):
            self.assertFalse(math.isnan(v))
        self.assertTrue(-1 <= b.x - b.radius
                        and b.x + b.radius <= ARENA.WIDTH + 1)
        self.assertTrue(b.y + b.radius <= ARENA.FLOOR_Y + 1)
        self.assertLessEqual(math.hypot(b.vx, b.vy), BALL.MAX_SPEED + EPSILON)
        for p in m.players:
            self.assertTrue(p.half_width() - 1 <= p.x
                            <= ARENA.WIDTH - p.half_width() + 1)
            self.assertLessEqual(p.y, ARENA.FLOOR_Y + EPSILON)

    def check_events(self, m, events):
        # One event per goal, nothing repeated.
        self.assertEqual(sum(m.score), count(events, protocol.EV_GOAL))
        self.assertEqual(count(events, protocol.EV_MATCH_END), 1)
        self.assertGreater(count(events, protocol.EV_POWER_SPAWN), 3)


# --- F10: the ball squeezed between two players ---------------------------
SQUEEZE_SECONDS = 2.0            # s of pressing
MAX_SINK = 2.0                   # px the ball may be inside a player
MAX_SHOVE = 3.0                  # px a player may move in one step
BALL_ON_FLOOR_Y = ARENA.FLOOR_Y - BALL.RADIUS
PRESSED_X = (599.0, 681.0)       # the two players pressed head to head
WIDE_X = (540.0, 740.0)          # both players walking to the middle
HEAD_BETWEEN_Y = ARENA.FLOOR_Y - PLAYER.HEAD_OFFSET_Y
BALL_SPEEDS = (0, 300, -300, 800, -800)   # px/s of the ball at the start


def sink(ball, player):
    """px the ball is inside the worst circle of a player."""
    worst = 0.0
    for radius, (cx, cy, _) in ((PLAYER.HEAD_RADIUS, player.head()),
                                (PLAYER.BODY_RADIUS, player.body())):
        overlap = ball.radius + radius - math.hypot(ball.x - cx, ball.y - cy)
        worst = max(worst, overlap)
    return worst


def prepared_match(ball_x, ball_y, vx=0.0, vy=0.0, players=WIDE_X):
    """Ball and players where the squeeze test wants them."""
    m = helpers.playing_match()
    for p, x in zip(m.players, players):
        p.x, p.y = x, ARENA.FLOOR_Y
        p.vx = p.vy = 0.0
    m.ball.x, m.ball.y = ball_x, ball_y
    m.ball.vx, m.ball.vy = vx, vy
    return m


def press(m, seconds=SQUEEZE_SECONDS):
    """Both players walk into each other; returns the worst sink seen."""
    worst = 0.0
    for _ in range(int(round(seconds / DT))):
        m.set_input(0, False, True, 0, 0)
        m.set_input(1, True, False, 0, 0)
        m.step(DT)
        for p in m.players:
            worst = max(worst, sink(m.ball, p))
    return worst


class SqueezeTest(unittest.TestCase):
    """The ball pressed between the players stays between them."""

    def assert_between(self, m):
        left, right = m.players
        self.assertLess(left.x, m.ball.x)
        self.assertGreater(right.x, m.ball.x)

    def test_ball_on_the_floor_stays_between_the_two(self):
        for vx in BALL_SPEEDS:
            with self.subTest(vx=vx):
                m = prepared_match(ARENA.WIDTH / 2, BALL_ON_FLOOR_Y, vx,
                                   players=PRESSED_X)
                worst = press(m)
                self.assert_between(m)
                self.assertLess(worst, MAX_SINK)

    def test_ball_between_the_heads_does_not_sink_into_one(self):
        for vy in (0, 300, -300, 700):
            with self.subTest(vy=vy):
                m = prepared_match(ARENA.WIDTH / 2, HEAD_BETWEEN_Y, 0, vy,
                                   players=PRESSED_X)
                worst = press(m)
                self.assert_between(m)
                self.assertLess(worst, MAX_SINK)

    def test_ball_at_the_feet_does_not_shove_the_players(self):
        m = prepared_match(PRESSED_X[0] + 3, BALL_ON_FLOOR_Y,
                           players=PRESSED_X)
        for _ in range(int(round(SQUEEZE_SECONDS / DT))):
            before = [p.x for p in m.players]
            m.step(DT)
            for p, was in zip(m.players, before):
                self.assertLess(abs(p.x - was), MAX_SHOVE)

    def test_ball_against_the_wall_is_not_pushed_through(self):
        m = prepared_match(0.0, BALL_ON_FLOOR_Y, 0.0, 0.0,
                           (PLAYER.HALF_WIDTH, WIDE_X[1]))
        m.ball.x = m.players[0].x - 20.0
        for _ in range(int(round(SQUEEZE_SECONDS / DT))):
            m.set_input(0, True, False, 0, 0)      # the player walks left
            m.step(DT)
            self.assertLess(m.ball.x, m.players[0].x)
        self.assertLessEqual(m.ball.x - m.ball.radius, EPSILON)

    def test_fast_ball_does_not_cross_the_pressed_players(self):
        m = prepared_match(ARENA.WIDTH / 2, BALL_ON_FLOOR_Y, BALL.MAX_SPEED,
                           players=PRESSED_X)
        worst = press(m)
        self.assert_between(m)
        self.assertLess(worst, MAX_SINK)


class ChargeTest(unittest.TestCase):
    """A player running into the ball pushes it away, never over it."""

    def test_ball_in_front_is_pushed_ahead(self):
        m = prepared_match(0.0, BALL_ON_FLOOR_Y, 0.0, 0.0,
                           (540.0, WIDE_X[1]))
        m.ball.x = m.players[0].x + 20.0
        worst = 0.0
        for _ in range(int(round(SQUEEZE_SECONDS / DT))):
            m.set_input(0, False, True, 0, 0)
            m.step(DT)
            worst = max(worst, sink(m.ball, m.players[0]))
        self.assertGreater(m.ball.x, m.players[0].x)
        self.assertLess(worst, MAX_SINK)

    def test_player_does_not_jump_over_the_ball(self):
        m = prepared_match(0.0, BALL_ON_FLOOR_Y, 0.0, 0.0,
                           (540.0, WIDE_X[1]))
        m.ball.x = m.players[0].x
        for _ in range(int(round(SQUEEZE_SECONDS / DT))):
            before = m.players[0].x
            m.step(DT)
            self.assertLess(abs(m.players[0].x - before), MAX_SHOVE)
            self.assertLess(sink(m.ball, m.players[0]), MAX_SINK)
        self.assertGreater(abs(m.ball.x - m.players[0].x),
                           PLAYER.BODY_RADIUS + BALL.RADIUS)


def score_a_goal(m, steps=90):
    """Puts the ball into the left goal and steps until it counts."""
    goal = m.goals[0]
    m.ball.x, m.ball.y = goal.mouth_x + 60, ARENA.FLOOR_Y - 60
    m.ball.vx, m.ball.vy = -700, 0
    for _ in range(steps):
        events = m.step(DT)
        if count(events, protocol.EV_GOAL):
            return
    raise AssertionError("the ball never went in")


def walking_right(m, i):
    """Inputs of run(): player 1 walks right and kicks at every step."""
    del i  # Unused.
    m.set_input(0, False, True, 1, 1)


def replayless_match():
    """Playing match of an interface that shows no party nor replay."""
    m = match.Match(1, seed=1, presentation=False)
    m.phase = protocol.PHASE_PLAYING
    m.phase_left = 0.0
    m.powers.spawn_timer = helpers.NO_SPAWN
    park_players(m)
    return m


class GoalHoldTest(unittest.TestCase):
    """F10: the match is frozen while the party and the replay run."""

    def test_the_match_does_not_move_during_the_replay(self):
        m = parked_match()
        score_a_goal(m)
        before = m.snapshot(0)
        spawn_timer = m.powers.spawn_timer
        run(m, RULES.GOAL_REPLAY - 0.1, inputs=walking_right)
        after = m.snapshot(0)
        self.assertEqual(m.phase, protocol.PHASE_GOAL)
        self.assertEqual(after["clock"], before["clock"])
        self.assertEqual(after["players"], before["players"])
        self.assertEqual(after["ball"], before["ball"])
        self.assertEqual(after["goals"], before["goals"])
        self.assertEqual(m.powers.spawn_timer, spawn_timer)
        self.assertLess(after["phase_left"], before["phase_left"])

    def test_the_kickoff_comes_when_the_hold_ends(self):
        m = parked_match()
        score_a_goal(m)
        run(m, RULES.GOAL_HOLD - 0.1)
        self.assertEqual(m.phase, protocol.PHASE_GOAL)
        run(m, 0.2)
        self.assertEqual(m.phase, protocol.PHASE_COUNTDOWN)
        self.assertEqual((m.ball.x, m.ball.y), tuple(map(float, BALL.SPAWN)))

    def test_the_hold_is_the_party_plus_the_replay(self):
        self.assertAlmostEqual(RULES.GOAL_HOLD,
                               RULES.GOAL_CELEBRATION + RULES.GOAL_REPLAY)

    def test_without_the_replay_only_the_party_is_held(self):
        m = replayless_match()
        self.assertAlmostEqual(m.goal_hold, RULES.GOAL_CELEBRATION)
        score_a_goal(m)
        run(m, RULES.GOAL_CELEBRATION + 0.1)
        self.assertEqual(m.phase, protocol.PHASE_COUNTDOWN)

    def test_skipping_the_replay_goes_straight_to_the_kickoff(self):
        m = parked_match()
        score_a_goal(m)
        run(m, 0.5)
        ok, events = m.skip_goal()
        self.assertTrue(ok)
        self.assertEqual(events, [])
        self.assertEqual(m.phase, protocol.PHASE_COUNTDOWN)
        self.assertEqual(m.phase_left, RULES.GOAL_COUNTDOWN)
        self.assertEqual((m.ball.x, m.ball.y), tuple(map(float, BALL.SPAWN)))

    def test_skipping_without_a_goal_on_screen_does_nothing(self):
        m = helpers.playing_match()
        self.assertEqual(m.skip_goal(), (False, []))
        self.assertEqual(m.phase, protocol.PHASE_PLAYING)

    def test_skipping_the_golden_goal_ends_the_match(self):
        m = parked_match()
        m.golden = True
        score_a_goal(m)
        ok, events = m.skip_goal()
        self.assertTrue(ok)
        self.assertEqual(m.phase, protocol.PHASE_FINISHED)
        self.assertEqual(count(events, protocol.EV_MATCH_END), 1)


if __name__ == "__main__":
    unittest.main()
