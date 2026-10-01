"""Protocolo: contadores de pulsaciones, filtros de estado y deduplicación."""
import unittest

from helpers import P


class PressCounterTest(unittest.TestCase):
    def test_first_snapshot_is_baseline(self):
        c = P.PressCounter()
        self.assertEqual(c.update(5), 0)   # pulsaciones previas no cuentan
        self.assertEqual(c.update(5), 0)
        self.assertEqual(c.update(7), 2)

    def test_compaction_keeps_presses(self):
        """La SIM puede leer sólo la última foto y no pierde pulsaciones."""
        c = P.PressCounter()
        c.update(0)
        snapshots = [P.make_input(i, [[False, True, j, 0], [False, False, 0, 0]])
                     for i, j in enumerate([0, 1, 1, 1, 2])]
        latest = snapshots[-1]          # compactación: se descartan las intermedias
        self.assertEqual(c.update(latest["p"][0][2]), 2)

    def test_counter_reset_rebaselines(self):
        c = P.PressCounter()
        c.update(10)
        self.assertEqual(c.update(3), 0)
        self.assertEqual(c.update(4), 1)


class StateFilterTest(unittest.TestCase):
    def test_rejects_other_match_and_stale(self):
        f = P.StateFilter()
        self.assertFalse(f.accept({"match": 1, "seq": 1}))   # aún no se espera nada
        f.expect(1)
        self.assertTrue(f.accept({"match": 1, "seq": 1}))
        self.assertFalse(f.accept({"match": 1, "seq": 1}))   # repetido
        self.assertTrue(f.accept({"match": 1, "seq": 5}))
        self.assertFalse(f.accept({"match": 1, "seq": 3}))   # viejo
        f.expect(2)                                          # revancha / reinicio
        self.assertFalse(f.accept({"match": 1, "seq": 99}))  # partido anterior
        self.assertTrue(f.accept({"match": 2, "seq": 1}))
        self.assertEqual(f.rejected_old_match, 2)
        self.assertEqual(f.rejected_stale, 2)


class DeduperTest(unittest.TestCase):
    def test_each_event_once(self):
        d = P.EventDeduper()
        ev = P.make_event(P.EV_GOAL, 7, 1, scorer=0)
        self.assertTrue(d.fresh(ev))
        self.assertFalse(d.fresh(ev))
        self.assertFalse(d.fresh(P.make_event(P.EV_GOAL, 6, 1)))
        self.assertTrue(d.fresh(P.make_event(P.EV_GOAL, 8, 1)))
        self.assertTrue(d.fresh(P.make_event(P.EV_READY, None, None)))


class ConstructorsTest(unittest.TestCase):
    def test_unknown_command(self):
        with self.assertRaises(ValueError):
            P.make_command("bailar", 1)

    def test_cosmetic_classification(self):
        self.assertTrue(P.is_cosmetic(P.make_event(P.EV_TOUCH, 1)))
        self.assertFalse(P.is_cosmetic(P.make_event(P.EV_GOAL, 1)))
        self.assertFalse(P.is_cosmetic(P.make_ack(1, P.CMD_PAUSE)))


if __name__ == "__main__":
    unittest.main()
