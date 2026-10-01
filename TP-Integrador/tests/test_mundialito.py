"""Mundialito: lógica del torneo y rival automático (sin interfaz)."""
import random
import unittest

from helpers import P, PHYSICS_DT
from fdc.bot import Bot
from fdc.config import CHARACTER_IDS
from fdc.mundialito import CHAMPION, ELIMINATED, IN_PROGRESS, STAGES, Tournament
from fdc.sim.match import Match


def play(level_left, level_right, seed):
    """Partido de 60 s con gol de oro; None = jugador quieto."""
    m = Match(1, seed=seed, golden_goal=True)
    bots = [Bot(0, level_left, seed + 1) if level_left is not None else None,
            Bot(1, level_right, seed + 2) if level_right is not None else None]
    last = [[0, 0], [0, 0]]
    st, k = m.snapshot(0), 0
    while m.phase != P.PHASE_FINISHED and k < 200 / PHYSICS_DT:
        if k % 2 == 0:
            st = m.snapshot(k)                    # como la UI: estados a 60 Hz
        for i, b in enumerate(bots):
            if b is None:
                continue
            l, r, j, kk = b.controls(st, PHYSICS_DT)
            m.set_input(i, l, r, j - last[i][0], kk - last[i][1])
            last[i] = [j, kk]
        m.step(PHYSICS_DT)
        k += 1
    return m


class TournamentTest(unittest.TestCase):
    def test_rivals_are_the_other_six(self):
        t = Tournament("messi", random.Random(1))
        self.assertEqual(sorted(t.rivals), sorted(c for c in CHARACTER_IDS if c != "messi"))
        self.assertEqual(t.stage_name, STAGES[0])
        self.assertEqual(t.level, 0)
        t2 = Tournament("messi", random.Random(1))
        self.assertEqual(t.rivals, t2.rivals)            # misma semilla, mismo sorteo

    def test_win_all_is_champion(self):
        t = Tournament("pele", random.Random(2))
        for i in range(6):
            self.assertEqual(t.level, i)                  # dificultad creciente
            self.assertTrue(t.record(2, 1))
        self.assertEqual(t.status, CHAMPION)
        self.assertEqual(t.position, 1)
        with self.assertRaises(RuntimeError):
            t.record(1, 0)

    def test_positions_when_eliminated(self):
        for lost_at, expected in ((0, 7), (2, 5), (3, 4), (5, 2)):
            t = Tournament("cr7", random.Random(3))
            for _ in range(lost_at):
                t.record(1, 0)
            self.assertEqual(t.status, IN_PROGRESS)
            self.assertFalse(t.record(0, 1))
            self.assertEqual(t.status, ELIMINATED)
            self.assertEqual(t.position, expected)
            self.assertEqual(t.results[-1][0], STAGES[lost_at])


class BotTest(unittest.TestCase):
    def test_no_presses_outside_play(self):
        b = Bot(0, 5, seed=1)
        m = Match(1, seed=1)                              # en cuenta regresiva
        for _ in range(100):
            left, right, j, k = b.controls(m.snapshot(0), PHYSICS_DT)
            self.assertFalse(left or right)
        self.assertEqual((j, k), (0, 0))
        self.assertEqual(b.controls(None, PHYSICS_DT)[:2], [False, False])

    def test_beats_an_idle_player(self):
        m = play(2, None, seed=11)
        self.assertGreater(m.score[0], m.score[1])
        self.assertEqual(m.winner, 0)

    def test_harder_level_wins_more(self):
        wins = sum(play(5, 0, seed).winner == 0 for seed in (21, 22, 23))
        self.assertGreaterEqual(wins, 2)


if __name__ == "__main__":
    unittest.main()
