"""REAL communication with the simulation process (multiprocessing, spawn)."""
import ctypes
import multiprocessing
import os
import time
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc import config
from fdc import ipc
from fdc import protocol

POLL_PERIOD = 1 / 120       # s between polls of the link
READY_WAIT = 10             # s at most until READY
IDLE_INPUT = [[False, False, 0, 0], [False, False, 0, 0]]
HOST_LIFE = 60              # s the fake interface lives (it is killed before)


def pump(link, seconds, feed=True, until=None):
    """Reads messages during 'seconds' (or until until(msgs, states))."""
    msgs, states = [], []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        m, s = link.poll()
        msgs += m
        if s:
            states.append(s)
        if feed:
            link.send_input(IDLE_INPUT)
        if until and until(msgs, states):
            break
        time.sleep(POLL_PERIOD)
    return msgs, states


def acks(msgs, cmd):
    return [m for m in msgs
            if m["type"] == protocol.EV_ACK and m["cmd"] == cmd]


def wait_ready(link):
    pump(link, READY_WAIT, feed=False, until=lambda m, s: link.ready)


class ProcessTest(unittest.TestCase):
    def setUp(self):
        self.link = ipc.SimLink(test_mode=True, seed=11, log_to_file=False)
        self.link.start()
        wait_ready(self.link)
        self.assertTrue(self.link.ready, "the simulation sent no READY")

    def tearDown(self):
        if self.link.proc is not None:
            self.link.stop()

    def command(self, cmd, seconds=2, **payload):
        """Sends a command and pumps until its ACK; returns the messages."""
        self.link.send_command(cmd, **payload)
        msgs, _ = pump(self.link, seconds, until=lambda m, s: acks(m, cmd))
        return msgs

    def start_match(self, match_id=1):
        self.link.send_command(protocol.CMD_START, match=match_id,
                               characters=["messi", "pele"])
        msgs, states = pump(self.link, 3, until=lambda m, s: acks(
            m, protocol.CMD_START))
        self.assertTrue(acks(msgs, protocol.CMD_START))
        return msgs, states

    def test_ready_comes_from_another_process_without_pygame(self):
        info = self.link.ready_info
        self.assertNotEqual(info["pid"], os.getpid())
        self.assertEqual(info["pid"], self.link.proc.pid)
        self.assertFalse(info["pygame_loaded"])

    def test_start_pause_resume_restart(self):
        self.start_match(1)
        f = protocol.StateFilter()
        f.expect(1)
        _, states = pump(self.link, 3.6)
        good = [s for s in states if f.accept(s)]
        self.assertTrue(good)
        self.assertEqual(good[-1]["phase"], protocol.PHASE_PLAYING)
        self.check_pause(f)
        msgs = self.command(protocol.CMD_RESUME)
        self.assertTrue(acks(msgs, protocol.CMD_RESUME)[0]["ok"])
        self.check_restart(f)

    def check_pause(self, f):
        msgs = self.command(protocol.CMD_PAUSE,
                            reason=protocol.PAUSE_REASON_USER)
        self.assertTrue(acks(msgs, protocol.CMD_PAUSE)[0]["ok"])
        # Heartbeats during the pause.
        _, states = pump(self.link, 1.0, feed=False)
        paused = [s for s in states if f.accept(s)]
        self.assertGreaterEqual(len(paused), 2)
        self.assertTrue(all(s["paused"] for s in paused))
        # Frozen clock.
        self.assertEqual(len({s["clock"] for s in paused}), 1)

    def check_restart(self, f):
        """The UI expects match 2 BEFORE the confirmation."""
        f.expect(2)
        self.link.send_command(protocol.CMD_RESTART, match=2)
        msgs, states = pump(self.link, 2, until=lambda m, s: acks(
            m, protocol.CMD_RESTART))
        self.assertEqual(acks(msgs, protocol.CMD_RESTART)[0]["match"], 2)
        _, more = pump(self.link, 0.5)
        accepted = [s for s in states + more if f.accept(s)]
        self.assertTrue(accepted)
        self.assertTrue(all(s["match"] == 2 for s in accepted))
        self.assertEqual(accepted[0]["clock"], config.MatchRules.DURATION)
        self.assertEqual(accepted[0]["effects"], [])
        self.assertEqual(self.link.pending, {})

    def test_skip_goal_without_a_goal_is_refused(self):
        """The interface may say the replay is over with no goal on screen:
        the simulation refuses and the match stays in play."""
        self.start_match(1)
        msgs = self.command(protocol.CMD_SKIP_GOAL)
        ack = acks(msgs, protocol.CMD_SKIP_GOAL)[0]
        self.assertFalse(ack["ok"])

    def test_old_match_events_are_filtered(self):
        self.start_match(1)
        pump(self.link, 3.3)
        self.link.send_command(protocol.CMD_DEBUG_POWER, power="speed_up",
                               mode="p0")
        self.link.send_command(protocol.CMD_RESTART, match=2)
        msgs, _ = pump(self.link, 1.0)
        powers = [m for m in msgs if m["type"] == protocol.EV_POWER]
        self.assertEqual(len(powers), 1)
        # The UI drops it by its match number.
        self.assertEqual(powers[0]["match"], 1)

    def test_debug_power_event_once(self):
        self.start_match(1)
        pump(self.link, 3.3)
        self.link.send_command(protocol.CMD_DEBUG_POWER, power="bombs",
                               mode="p1")
        msgs, _ = pump(self.link, 1.6)
        types = [m["type"] for m in msgs]
        self.assertEqual(types.count(protocol.EV_POWER), 1)
        self.assertEqual(types.count(protocol.EV_BOMB_EXPLODE), 1)

    def test_watchdog_pauses_without_inputs(self):
        self.start_match(1)
        pump(self.link, 3.3)
        msgs, _ = pump(self.link, 1.5, feed=False)
        self.assertTrue(any(
            m["type"] == protocol.EV_PAUSED
            and m["reason"] == protocol.PAUSE_REASON_WATCHDOG for m in msgs))

    def test_coordinated_shutdown(self):
        self.start_match(1)
        pump(self.link, 0.5)
        proc = self.link.proc
        report = self.link.stop()
        self.assertEqual(report["method"], "orderly")
        self.assertTrue(report["bye"])
        self.assertEqual(report["exitcode"], 0)
        self.assertFalse(proc.is_alive())

    def test_crash_is_detected(self):
        self.start_match(1)
        self.link.send_command(protocol.CMD_DEBUG_CRASH)
        pump(self.link, 3, until=lambda m, s: self.link.error is not None)
        self.assertIsNotNone(self.link.check_health())
        self.assertIn("error", self.link.error.lower())
        report = self.link.stop()
        self.assertEqual(report["exitcode"], 1)
        self.assertEqual(report["method"], "orderly")

    def test_dead_process_is_detected(self):
        self.link.proc.kill()      # an abrupt failure (no message)
        self.link.proc.join(2)
        self.assertIn("inesperadamente", self.link.check_health())
        report = self.link.stop()
        self.assertFalse(report["bye"])


def _host_link(pid_q):
    """Host process that plays the "interface" and then dies silently."""
    link = ipc.SimLink(log_to_file=False)
    link.start()
    wait_ready(link)
    pid_q.put(link.proc.pid)
    time.sleep(HOST_LIFE)


def _pid_exists(pid):
    """True if the process is alive (os.kill(pid, 0) fails on Windows)."""
    if os.name == "nt":
        return _win_pid_exists(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _win_pid_exists(pid):
    """Windows check with OpenProcess/GetExitCodeProcess (WinError 87 free).
    """
    kernel32 = ctypes.windll.kernel32
    still_active = 259          # STILL_ACTIVE exit code of a live process
    handle = kernel32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


class OrphanTest(unittest.TestCase):
    def test_simulation_exits_if_ui_dies(self):
        ctx = multiprocessing.get_context("spawn")
        q = ctx.Queue()
        host = ctx.Process(target=_host_link, args=(q,))
        host.start()
        sim_pid = q.get(timeout=20)
        self.assertTrue(_pid_exists(sim_pid))
        host.kill()                    # the "interface" dies abruptly
        host.join(5)
        deadline = time.monotonic() + 5
        while _pid_exists(sim_pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(_pid_exists(sim_pid), "the simulation was orphaned")


class NoTestModeTest(unittest.TestCase):
    def test_debug_commands_rejected(self):
        link = ipc.SimLink(test_mode=False, log_to_file=False)
        link.start()
        try:
            self.check_rejected(link)
        finally:
            self.assertEqual(link.stop()["method"], "orderly")

    def check_rejected(self, link):
        wait_ready(link)
        link.send_command(protocol.CMD_START, match=1)
        link.send_command(protocol.CMD_DEBUG_POWER, power="grow", mode="p0")
        link.send_command(protocol.CMD_DEBUG_CRASH)
        msgs, _ = pump(link, 2, until=lambda m, s: acks(
            m, protocol.CMD_DEBUG_CRASH))
        self.assertFalse(acks(msgs, protocol.CMD_DEBUG_POWER)[0]["ok"])
        self.assertFalse(acks(msgs, protocol.CMD_DEBUG_CRASH)[0]["ok"])
        self.assertTrue(link.alive)


if __name__ == "__main__":
    unittest.main()
