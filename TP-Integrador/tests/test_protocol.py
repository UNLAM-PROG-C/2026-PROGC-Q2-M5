"""Protocol: press counters, state filters and deduplication."""
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc import protocol


class PressCounterTest(unittest.TestCase):
  def test_first_snapshot_is_baseline(self):
    c = protocol.PressCounter()
    self.assertEqual(c.update(5), 0)   # earlier presses do not count
    self.assertEqual(c.update(5), 0)
    self.assertEqual(c.update(7), 2)

  def test_compaction_keeps_presses(self):
    """The SIM may read only the last snapshot and loses no press."""
    c = protocol.PressCounter()
    c.update(0)
    snapshots = [protocol.make_input(i, [[False, True, j, 0],
                                         [False, False, 0, 0]])
                 for i, j in enumerate([0, 1, 1, 1, 2])]
    latest = snapshots[-1]       # compaction: the others are dropped
    self.assertEqual(c.update(latest["p"][0][2]), 2)

  def test_counter_reset_rebaselines(self):
    c = protocol.PressCounter()
    c.update(10)
    self.assertEqual(c.update(3), 0)
    self.assertEqual(c.update(4), 1)


class StateFilterTest(unittest.TestCase):
  def test_rejects_other_match_and_stale(self):
    f = protocol.StateFilter()
    # Nothing is expected yet.
    self.assertFalse(f.accept({"match": 1, "seq": 1}))
    f.expect(1)
    self.assertTrue(f.accept({"match": 1, "seq": 1}))
    self.assertFalse(f.accept({"match": 1, "seq": 1}))   # repeated
    self.assertTrue(f.accept({"match": 1, "seq": 5}))
    self.assertFalse(f.accept({"match": 1, "seq": 3}))   # old
    f.expect(2)                                  # rematch / restart
    self.assertFalse(f.accept({"match": 1, "seq": 99}))  # older match
    self.assertTrue(f.accept({"match": 2, "seq": 1}))
    self.assertEqual(f.rejected_old_match, 2)
    self.assertEqual(f.rejected_stale, 2)


class DeduperTest(unittest.TestCase):
  def test_each_event_once(self):
    d = protocol.EventDeduper()
    ev = protocol.make_event(protocol.EV_GOAL, 7, 1, scorer=0)
    self.assertTrue(d.fresh(ev))
    self.assertFalse(d.fresh(ev))
    self.assertFalse(d.fresh(protocol.make_event(protocol.EV_GOAL, 6, 1)))
    self.assertTrue(d.fresh(protocol.make_event(protocol.EV_GOAL, 8, 1)))
    self.assertTrue(d.fresh(protocol.make_event(protocol.EV_READY, None,
                                                None)))


class ConstructorsTest(unittest.TestCase):
  def test_unknown_command(self):
    with self.assertRaises(ValueError):
      protocol.make_command("dance", 1)

  def test_cosmetic_classification(self):
    self.assertTrue(protocol.is_cosmetic(
        protocol.make_event(protocol.EV_TOUCH, 1)))
    self.assertFalse(protocol.is_cosmetic(
        protocol.make_event(protocol.EV_GOAL, 1)))
    self.assertFalse(protocol.is_cosmetic(
        protocol.make_ack(1, protocol.CMD_PAUSE)))


if __name__ == "__main__":
  unittest.main()
