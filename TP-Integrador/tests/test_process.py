"""Comunicación REAL con el proceso de simulación (multiprocessing, spawn)."""
import multiprocessing as mp
import os
import time
import unittest

from helpers import P
from fdc.config import MatchRules
from fdc.ipc import SimLink


def pump(link, seconds, feed=True, until=None):
    """Lee mensajes durante 'seconds' (o hasta que until(msgs, state) sea True)."""
    msgs, states = [], []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        m, s = link.poll()
        msgs += m
        if s:
            states.append(s)
        if feed:
            link.send_input([[False, False, 0, 0], [False, False, 0, 0]])
        if until and until(msgs, states):
            break
        time.sleep(1 / 120)
    return msgs, states


def acks(msgs, cmd):
    return [m for m in msgs if m["type"] == P.EV_ACK and m["cmd"] == cmd]


class ProcessTest(unittest.TestCase):
    def setUp(self):
        self.link = SimLink(test_mode=True, seed=11, log_to_file=False)
        self.link.start()
        pump(self.link, 10, feed=False, until=lambda m, s: self.link.ready)
        self.assertTrue(self.link.ready, "la simulación no envió READY")

    def tearDown(self):
        if self.link.proc is not None:
            self.link.stop()

    def start_match(self, match_id=1):
        self.link.send_command(P.CMD_START, match=match_id, characters=["messi", "pele"])
        msgs, states = pump(self.link, 3, until=lambda m, s: acks(m, P.CMD_START))
        self.assertTrue(acks(msgs, P.CMD_START))
        return msgs, states

    def test_ready_comes_from_another_process_without_pygame(self):
        info = self.link.ready_info
        self.assertNotEqual(info["pid"], os.getpid())
        self.assertEqual(info["pid"], self.link.proc.pid)
        self.assertFalse(info["pygame_loaded"])

    def test_start_pause_resume_restart(self):
        self.start_match(1)
        f = P.StateFilter()
        f.expect(1)
        _, states = pump(self.link, 3.6)
        good = [s for s in states if f.accept(s)]
        self.assertTrue(good)
        self.assertEqual(good[-1]["phase"], P.PHASE_PLAYING)

        self.link.send_command(P.CMD_PAUSE, reason=P.PAUSE_REASON_USER)
        msgs, _ = pump(self.link, 2, until=lambda m, s: acks(m, P.CMD_PAUSE))
        self.assertTrue(acks(msgs, P.CMD_PAUSE)[0]["ok"])
        _, states = pump(self.link, 1.0, feed=False)   # latidos durante la pausa
        paused = [s for s in states if f.accept(s)]
        self.assertGreaterEqual(len(paused), 2)
        self.assertTrue(all(s["paused"] for s in paused))
        self.assertEqual(len({s["clock"] for s in paused}), 1)   # reloj congelado

        self.link.send_command(P.CMD_RESUME)
        msgs, _ = pump(self.link, 2, until=lambda m, s: acks(m, P.CMD_RESUME))
        self.assertTrue(acks(msgs, P.CMD_RESUME)[0]["ok"])

        # reinicio: la UI pasa a esperar el partido 2 ANTES de la confirmación
        f.expect(2)
        self.link.send_command(P.CMD_RESTART, match=2)
        msgs, states = pump(self.link, 2, until=lambda m, s: acks(m, P.CMD_RESTART))
        ack = acks(msgs, P.CMD_RESTART)[0]
        self.assertEqual(ack["match"], 2)
        _, more = pump(self.link, 0.5)
        accepted = [s for s in states + more if f.accept(s)]
        self.assertTrue(accepted)
        self.assertTrue(all(s["match"] == 2 for s in accepted))
        self.assertEqual(accepted[0]["clock"], MatchRules.DURATION)
        self.assertEqual(accepted[0]["effects"], [])
        self.assertEqual(self.link.pending, {})

    def test_old_match_events_are_filtered(self):
        self.start_match(1)
        pump(self.link, 3.3)
        self.link.send_command(P.CMD_DEBUG_POWER, power="speed_up", mode="p0")
        self.link.send_command(P.CMD_RESTART, match=2)
        msgs, _ = pump(self.link, 1.0)
        powers = [m for m in msgs if m["type"] == P.EV_POWER]
        self.assertEqual(len(powers), 1)
        self.assertEqual(powers[0]["match"], 1)   # la UI lo descarta por partido

    def test_debug_power_event_once(self):
        self.start_match(1)
        pump(self.link, 3.3)
        self.link.send_command(P.CMD_DEBUG_POWER, power="bombs", mode="p1")
        msgs, _ = pump(self.link, 1.6)
        self.assertEqual(sum(1 for m in msgs if m["type"] == P.EV_POWER), 1)
        self.assertEqual(sum(1 for m in msgs if m["type"] == P.EV_BOMB_EXPLODE), 1)

    def test_watchdog_pauses_without_inputs(self):
        self.start_match(1)
        pump(self.link, 3.3)
        msgs, states = pump(self.link, 1.5, feed=False)
        self.assertTrue(any(m["type"] == P.EV_PAUSED and m["reason"] == P.PAUSE_REASON_WATCHDOG
                            for m in msgs))

    def test_coordinated_shutdown(self):
        self.start_match(1)
        pump(self.link, 0.5)
        proc = self.link.proc
        report = self.link.stop()
        self.assertEqual(report["method"], "ordenado")
        self.assertTrue(report["bye"])
        self.assertEqual(report["exitcode"], 0)
        self.assertFalse(proc.is_alive())

    def test_crash_is_detected(self):
        self.start_match(1)
        self.link.send_command(P.CMD_DEBUG_CRASH)
        pump(self.link, 3, until=lambda m, s: self.link.error is not None)
        self.assertIsNotNone(self.link.check_health())
        self.assertIn("error", self.link.error.lower())
        report = self.link.stop()
        self.assertEqual(report["exitcode"], 1)
        self.assertIn(report["method"], ("ordenado",))

    def test_dead_process_is_detected(self):
        self.link.proc.kill()        # simula un fallo abrupto (sin mensaje)
        self.link.proc.join(2)
        self.assertIn("inesperadamente", self.link.check_health())
        report = self.link.stop()
        self.assertFalse(report["bye"])


def _host_link(pid_q):
    """Proceso anfitrión que hace de "interfaz" y luego muere sin avisar."""
    link = SimLink(log_to_file=False)
    link.start()
    pump(link, 10, feed=False, until=lambda m, s: link.ready)
    pid_q.put(link.proc.pid)
    time.sleep(60)


def _pid_exists(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class OrphanTest(unittest.TestCase):
    def test_simulation_exits_if_ui_dies(self):
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        host = ctx.Process(target=_host_link, args=(q,))
        host.start()
        sim_pid = q.get(timeout=20)
        self.assertTrue(_pid_exists(sim_pid))
        host.kill()                       # la "interfaz" muere abruptamente
        host.join(5)
        deadline = time.monotonic() + 5
        while _pid_exists(sim_pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(_pid_exists(sim_pid), "la simulación quedó huérfana")


class NoTestModeTest(unittest.TestCase):
    def test_debug_commands_rejected(self):
        link = SimLink(test_mode=False, log_to_file=False)
        link.start()
        try:
            pump(link, 10, feed=False, until=lambda m, s: link.ready)
            link.send_command(P.CMD_START, match=1)
            link.send_command(P.CMD_DEBUG_POWER, power="grow", mode="p0")
            link.send_command(P.CMD_DEBUG_CRASH)
            msgs, _ = pump(link, 2, until=lambda m, s: acks(m, P.CMD_DEBUG_CRASH))
            self.assertFalse(acks(msgs, P.CMD_DEBUG_POWER)[0]["ok"])
            self.assertFalse(acks(msgs, P.CMD_DEBUG_CRASH)[0]["ok"])
            self.assertTrue(link.alive)
        finally:
            self.assertEqual(link.stop()["method"], "ordenado")


if __name__ == "__main__":
    unittest.main()
