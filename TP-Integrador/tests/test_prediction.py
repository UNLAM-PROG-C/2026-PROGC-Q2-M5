"""Client prediction of the own player: movement and reconciliation."""
import unittest

import helpers  # pylint: disable=unused-import

from fdc import config
from fdc import protocol
from fdc.online import prediction

DT = config.PHYSICS_DT
FLOOR_Y = config.Arena.FLOOR_Y
FRAME_HZ = 60                   # frames per second of the client loop
FRAME = 1.0 / FRAME_HZ
REST = [False, False, 0, 0]
RIGHT = [False, True, 0, 0]


class Clock:
    """Clock the test moves by hand (the prediction stamps its history)."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, dt):
        self.now += dt


def make_state(x, ack=(0, 0), other_x=None, phase=protocol.PHASE_PLAYING,
               paused=False, goals=(110.0, 110.0), burned=False):
    """A state like the compact one the server sends (only what matters)."""
    players = [_player(x if side == 0 else (other_x or -x), side, burned)
               for side in (0, 1)]
    state = {"type": "state", "match": 1, "seq": 1, "tick": 1,
             "phase": phase, "paused": paused, "players": players,
             "goals": list(goals), "ball": {"x": 640.0, "y": 500.0}}
    if ack is not None:
        state["ack"] = list(ack)
    return state


def _player(x, side, burned=False):
    return {"x": float(x), "y": FLOOR_Y, "vx": 0.0, "vy": 0.0,
            "facing": 1 if side == 0 else -1, "ground": True, "kick": -1.0,
            "scale": 1.0, "frozen": False, "no_kick": False, "stride": 0.0,
            "burned": burned, "burned_left": 1.5 if burned else 0.0,
            "knock": False, "celebrate": False, "on_head": None,
            "speed": 1.0, "jump": 1.0}


def frames(pred, clock, seconds):
    """Runs the prediction `seconds` at the client's frame rate."""
    for _ in range(int(round(seconds * FRAME_HZ))):
        clock.advance(FRAME)
        pred.step(FRAME)


def ready_prediction(x=300.0, ack=0):
    """A prediction already in sync with a server player at `x`."""
    clock = Clock()
    pred = prediction.Prediction(0)
    pred.clock = clock
    pred.reconcile(make_state(x, ack=(ack, 0)), clock.now)
    pred.play()
    return pred, clock


def anchored_x(pred, now):
    """Where the prediction was one-way latency ago (the server's moment)."""
    entry = pred._anchor(now)
    return entry[1] if entry else pred.player.x


class PredictionTest(unittest.TestCase):
    def test_it_moves_at_once_without_waiting_for_the_server(self):
        pred, clock = ready_prediction()
        pred.push_input(RIGHT)
        frames(pred, clock, 0.1)
        self.assertGreater(pred.player.x, 300.0 + 5.0)

    def test_a_jump_starts_in_the_same_frame(self):
        pred, clock = ready_prediction()
        pred.push_input([False, False, 1, 0])
        clock.advance(FRAME)
        pred.step(FRAME)
        self.assertLess(pred.player.vy, 0.0)

    def test_only_the_own_player_is_replaced(self):
        pred, clock = ready_prediction()
        view = make_state(300.0)
        out = pred.apply(view)
        self.assertIsNot(out, view)
        self.assertEqual(out["players"][1], view["players"][1])
        self.assertEqual(out["players"][0]["x"], 300.0)

    def test_without_ack_it_turns_itself_off(self):
        pred, clock = ready_prediction()
        pred.reconcile(make_state(300.0, ack=None), clock.now)
        self.assertTrue(pred.unsupported)
        self.assertFalse(pred.enabled)
        view = make_state(300.0)
        self.assertIs(pred.apply(view), view)


class ReconcileTest(unittest.TestCase):
    def test_a_small_error_is_fixed_smoothly(self):
        pred, clock = ready_prediction()
        pred.push_input(RIGHT)
        frames(pred, clock, 0.3)
        before = pred.player.x
        anchor = anchored_x(pred, clock.now)      # where we were then
        state = make_state(anchor + 6.0, ack=(pred.seq, 0))
        pred.reconcile(state, clock.now)
        self.assertEqual((pred.fixes, pred.snaps), (1, 0))
        self.assertGreater(pred.player.x, before)
        self.assertLess(pred.player.x - before, 6.0)

    def test_a_big_error_snaps_to_the_server(self):
        pred, clock = ready_prediction()
        pred.push_input(RIGHT)
        frames(pred, clock, 0.3)
        state = make_state(900.0, ack=(pred.seq, 0))
        pred.reconcile(state, clock.now)
        self.assertEqual(pred.snaps, 1)
        self.assertEqual(pred.player.x, 900.0)
        self.assertEqual(pred.fixes, 0)

    def test_a_goal_snaps_to_the_new_position(self):
        pred, clock = ready_prediction()
        state = make_state(640.0, ack=(pred.seq, 0),
                           phase=protocol.PHASE_GOAL)
        pred.reconcile(state, clock.now)
        self.assertEqual(pred.player.x, 640.0)

    def test_lost_inputs_snap(self):
        pred, clock = ready_prediction()
        pred.push_input(RIGHT)
        frames(pred, clock, 0.2)
        for _ in range(config.Online.PREDICT_MAX_PENDING + 1):
            pred.push_input(RIGHT)
        state = make_state(anchored_x(pred, clock.now) + 2.0, ack=(1, 0))
        pred.reconcile(state, clock.now)
        self.assertEqual(pred.snaps, 1)

    def test_an_old_state_is_ignored(self):
        pred, clock = ready_prediction()
        pred.push_input(RIGHT)
        frames(pred, clock, 0.2)
        pred.reconcile(make_state(anchored_x(pred, clock.now), ack=(9, 0)),
                       clock.now)
        after_ok = pred.player.x
        pred.reconcile(make_state(120.0, ack=(4, 0)), clock.now)
        self.assertEqual(pred.stale, 1)
        self.assertEqual(pred.ack, 9)
        self.assertEqual(pred.player.x, after_ok)

    def test_nothing_is_predicted_in_a_pause_or_a_goal(self):
        pred, clock = ready_prediction()
        pred.push_input(RIGHT)
        frames(pred, clock, 0.2)
        pred.hold(make_state(500.0, paused=True))
        frames(pred, clock, 0.2)
        self.assertEqual(pred.player.x, 500.0)


class BurnedPredictionTest(unittest.TestCase):
    """1.0.2: the own player does not move while the fire power burns it."""

    def burned_prediction(self, x=300.0):
        """Prediction in sync with a server player that is burning."""
        clock = Clock()
        pred = prediction.Prediction(0)
        pred.clock = clock
        pred.reconcile(make_state(x, burned=True), clock.now)
        pred.play()
        return pred, clock

    def test_the_burned_player_does_not_move(self):
        pred, clock = self.burned_prediction()
        pred.push_input(RIGHT)
        frames(pred, clock, 0.3)
        self.assertAlmostEqual(pred.player.x, 300.0, delta=1.0)

    def test_it_does_not_jump_or_kick(self):
        pred, clock = self.burned_prediction()
        pred.push_input([False, False, 1, 1])
        frames(pred, clock, 0.3)
        self.assertEqual(pred.player.vy, 0.0)
        self.assertLess(pred.player.kick_t, 0.0)

    def test_it_moves_again_when_the_burn_is_over(self):
        pred, clock = self.burned_prediction()
        pred.push_input(RIGHT)
        frames(pred, clock, 0.2)
        pred.reconcile(make_state(300.0, ack=(1, 0)), clock.now)
        frames(pred, clock, 0.3)
        self.assertGreater(pred.player.x, 300.0 + 5.0)


if __name__ == "__main__":
    unittest.main()
