"""Tournament: tournament logic and the automatic rival (no interface)."""
import random
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc import bot
from fdc import config
from fdc import protocol
from fdc import tournament
from fdc.sim import match

MAX_MATCH_TIME = 200    # s: a golden goal match always ends before this


def _bots(level_left, level_right, seed):
  """One bot per side; None = a player that does not move."""
  return [bot.Bot(0, level_left, seed + 1) if level_left is not None
          else None,
          bot.Bot(1, level_right, seed + 2) if level_right is not None
          else None]


def _feed(m, bots, st, last):
  for i, b in enumerate(bots):
    if b is not None:
      left, right, jumps, kicks = b.controls(st, config.PHYSICS_DT)
      m.set_input(i, left, right, jumps - last[i][0],
                  kicks - last[i][1])
      last[i] = [jumps, kicks]


def play(level_left, level_right, seed):
  """60 s match with golden goal; None = a player that does not move."""
  m = match.Match(1, seed=seed, golden_goal=True)
  bots = _bots(level_left, level_right, seed)
  last = [[0, 0], [0, 0]]
  st, k = m.snapshot(0), 0
  while (m.phase != protocol.PHASE_FINISHED
         and k < MAX_MATCH_TIME / config.PHYSICS_DT):
    if k % 2 == 0:
      st = m.snapshot(k)          # like the UI: states at 60 Hz
    _feed(m, bots, st, last)
    m.step(config.PHYSICS_DT)
    k += 1
  return m


class TournamentTest(unittest.TestCase):
  def test_rivals_are_the_other_six(self):
    t = tournament.Tournament("messi", random.Random(1))
    self.assertEqual(sorted(t.rivals),
                     sorted(c for c in config.CHARACTER_IDS
                            if c != "messi"))
    self.assertEqual(t.stage_name, tournament.STAGES[0])
    self.assertEqual(t.level, 0)
    t2 = tournament.Tournament("messi", random.Random(1))
    self.assertEqual(t.rivals, t2.rivals)      # same seed, same draw

  def test_win_all_is_champion(self):
    t = tournament.Tournament("pele", random.Random(2))
    for i in range(6):
      self.assertEqual(t.level, i)            # growing difficulty
      self.assertTrue(t.record(2, 1))
    self.assertEqual(t.status, tournament.CHAMPION)
    self.assertEqual(t.position, 1)
    with self.assertRaises(RuntimeError):
      t.record(1, 0)

  def test_positions_when_eliminated(self):
    for lost_at, expected in ((0, 7), (2, 5), (3, 4), (5, 2)):
      t = tournament.Tournament("cr7", random.Random(3))
      for _ in range(lost_at):
        t.record(1, 0)
      self.assertEqual(t.status, tournament.IN_PROGRESS)
      self.assertFalse(t.record(0, 1))
      self.assertEqual(t.status, tournament.ELIMINATED)
      self.assertEqual(t.position, expected)
      self.assertEqual(t.results[-1][0], tournament.STAGES[lost_at])


class BotTest(unittest.TestCase):
  def test_no_presses_outside_play(self):
    b = bot.Bot(0, 5, seed=1)
    m = match.Match(1, seed=1)                  # in the countdown
    for _ in range(100):
      left, right, j, k = b.controls(m.snapshot(0), config.PHYSICS_DT)
      self.assertFalse(left or right)
    self.assertEqual((j, k), (0, 0))
    self.assertEqual(b.controls(None, config.PHYSICS_DT)[:2],
                     [False, False])

  def test_beats_an_idle_player(self):
    m = play(2, None, seed=11)
    self.assertGreater(m.score[0], m.score[1])
    self.assertEqual(m.winner, 0)

  def test_harder_level_wins_more(self):
    wins = sum(play(5, 0, seed).winner == 0 for seed in (21, 22, 23))
    self.assertGreaterEqual(wins, 2)


if __name__ == "__main__":
  unittest.main()
