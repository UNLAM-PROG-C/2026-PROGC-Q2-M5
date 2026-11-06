"""Online mode: real server with real WebSocket connections and room logic."""
import base64
import http.client
import json
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.request

try:
    import websockets  # pylint: disable=unused-import
except ImportError:  # the local game does not need it: skipped without it
    raise unittest.SkipTest(
        "websockets is missing (pip install -r requirements-online.txt)"
    ) from None

import helpers
import online_helpers
from fdc import config
from fdc import protocol
from fdc.online import interp
from fdc.online import lobby
from fdc.online import room_runner
from fdc.online import server as game_server
from fdc.online import wire
from fdc.sim import match

Client = online_helpers.Client
ServerThread = online_helpers.ServerThread
rules = config.MatchRules
start_match = online_helpers.start_match
PAUSE_MAX = 30.0        # s of a requested pause in these tests
GRACE = 30              # s to come back after a disconnection
INPUT_SENDS = 20        # control snapshots sent during the match
INPUT_GAP = 0.02        # s between them
HTTP_TIMEOUT = 5        # s of the raw HTTP connection
REDIRECT = 302          # HTTP status of the localhost redirection
UNAUTHORIZED = 401      # HTTP status without the panel password
NOT_FOUND = 404         # HTTP status when there is no full panel


# ---------------------------------------------------------------------------
# Room bridge without processes: requested pause, "ready", disconnections
# ---------------------------------------------------------------------------
class FakeLink:
    """MatchLink double: it records commands and returns given events."""
    ready = True
    sim_pid = None
    alive = True
    proc = None
    last_confirmed = None

    def __init__(self):
        self.cmds, self.events, self.state, self.inputs = [], [], None, None
        self.pending = {}

    def start(self):
        """Nothing to start."""

    def stop(self):
        return {}

    def poll(self):
        ev, self.events = self.events, []
        st, self.state = self.state, None
        return ev, st

    def check_health(self):
        return None

    def send_command(self, ctype, **kw):
        self.cmds.append((ctype, kw))
        return len(self.cmds)

    def send_input(self, p):
        self.inputs = [list(x) for x in p]


class FakeSession:
    """Session double: it keeps the messages sent to it."""

    def __init__(self):
        self.msgs = []

    def send(self, msg):
        self.msgs.append(msg)

    def send_text(self, text, replaceable=False):
        del replaceable  # Unused.
        self.msgs.append(wire.decode(text))

    def last(self, mtype):
        found = [m for m in self.msgs if m["type"] == mtype]
        return found[-1] if found else None


def _start_msgs(match_id):
    return [{"type": wire.MATCH_START, "match": match_id, "you": 0},
            {"type": wire.MATCH_START, "match": match_id, "you": 1}]


def _playing(match_id):
    m = match.Match(match_id)
    m.phase = protocol.PHASE_PLAYING
    return m


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.server = game_server.GameServer(web_dir=None, pause_max=PAUSE_MAX,
                                             sim_logs=False)
        self.server.deliver = lambda out: None
        self.a, self.b = FakeSession(), FakeSession()
        self.server.sessions = {"a": self.a, "b": self.b}
        self.r = room_runner.RoomRunner(self.server, 1)
        self.r.link = self.link = FakeLink()
        self.r.match = {"id": 7, "sids": ["a", "b"], "names": ["Ale", "Bruno"],
                        "chars": ["messi", "pele"],
                        "start_msgs": _start_msgs(7)}
        self.match = _playing(7)
        self.r.last_state = self.match.snapshot(1)

    def cmds(self, ctype):
        return [kw for c, kw in self.link.cmds if c == ctype]

    def activate_pause(self, now):
        self.link.events = [{"type": protocol.EV_PAUSED,
                             "reason": protocol.PAUSE_REASON_REQUEST, "by": 0,
                             "match": 7, "eid": 3}]
        self.r.tick(now)

    def test_pause_request_waits_for_goal_then_both_ready(self):
        self.r.request_pause(0)
        self.assertEqual(self.cmds(protocol.CMD_PAUSE),
                         [{"after_goal": True, "by": 0,
                           "reason": protocol.PAUSE_REASON_REQUEST}])
        info = self.b.last(wire.PAUSE_INFO)     # the rival sees who asked
        self.assertEqual((info["status"], info["by_name"]),
                         (wire.PAUSE_PENDING, "Ale"))
        self.r.request_pause(1)       # there is one already: not repeated
        self.assertEqual(len(self.cmds(protocol.CMD_PAUSE)), 1)
        self.activate_pause(100.0)
        self.assertEqual(self.a.last(wire.PAUSE_INFO)["status"],
                         wire.PAUSE_ACTIVE)
        self.check_both_ready()

    def check_both_ready(self):
        self.r.pause_ready(0)
        self.r.tick(101.0)
        self.assertEqual(self.cmds(protocol.CMD_RESUME), [])   # one missing
        self.assertEqual(self.b.last(wire.PAUSE_INFO)["ready"], [True, False])
        self.r.pause_ready(1)
        self.r.tick(101.5)
        self.assertEqual(len(self.cmds(protocol.CMD_RESUME)), 1)
        self.assertEqual(self.a.last(wire.PAUSE_INFO)["status"],
                         wire.PAUSE_NONE)

    def test_pause_resumes_alone_after_limit(self):
        self.r.request_pause(1)
        self.activate_pause(100.0)
        self.r.tick(129.0)
        self.assertEqual(self.cmds(protocol.CMD_RESUME), [])
        self.r.tick(130.1)
        self.assertEqual(len(self.cmds(protocol.CMD_RESUME)), 1)

    def test_disconnect_keeps_match_paused_until_return(self):
        self.r.request_pause(0)
        self.activate_pause(100.0)
        self.r.player_away(1, time.monotonic() + GRACE)
        self.assertEqual(self.cmds(protocol.CMD_PAUSE)[-1],
                         {"reason": protocol.PAUSE_REASON_DISCONNECT})
        self.assertFalse(self.a.last(wire.OPPONENT)["connected"])
        self.r.pause_ready(0)
        self.r.pause_ready(1)
        self.r.tick(101.0)               # the requested pause ended...
        self.assertEqual(self.cmds(protocol.CMD_RESUME), [])   # ...not back
        self.check_back()

    def check_back(self):
        back = FakeSession()
        self.server.sessions["b"] = back
        self.r.player_back(1, back)
        # Back to its match.
        self.assertEqual(back.msgs[0]["type"], wire.MATCH_START)
        self.assertTrue(self.a.last(wire.OPPONENT)["connected"])
        self.assertEqual(len(self.cmds(protocol.CMD_RESUME)), 1)

    def test_forfeit_gives_the_win_to_who_stayed(self):
        self.r.forfeit(0)
        over = self.b.last(wire.MATCH_OVER)
        self.assertEqual((over["winner"], over["reason"], over["by_name"]),
                         (1, wire.END_FORFEIT, "Ale"))
        self.assertIn(protocol.CMD_END, [c for c, _ in self.link.cmds])
        self.assertIsNone(self.r.match)

    def test_inputs_and_states_are_forwarded(self):
        self.r.set_input(1, [False, True, 2, 1])
        self.link.state = self.match.snapshot(2)
        self.r.tick(50.0)
        self.assertEqual(self.link.inputs[1], [False, True, 2, 1])
        st = self.a.last(wire.STATE)
        self.assertEqual((st["match"], st["seq"]), (7, 2))
        self.assertNotIn("dropped_states", st)


class PauseAfterGoalTest(unittest.TestCase):
    def test_match_pauses_only_after_next_goal(self):
        m = helpers.playing_match()
        self.assertTrue(m.request_pause_after_goal(1))
        helpers.run(m, 1.0)
        self.assertFalse(m.paused)                   # the play goes on
        # Goal in the left goal.
        m.ball.x, m.ball.y, m.ball.vx, m.ball.vy = 60, 600, -400, 0
        events = helpers.run(m, 0.2)
        self.assertEqual(helpers.count(events, protocol.EV_GOAL), 1)
        self.assertFalse(m.paused)                   # goal celebration
        events = helpers.run(m, rules.GOAL_HOLD + 0.1)
        self.check_paused_at_kickoff(m, events)

    def check_paused_at_kickoff(self, m, events):
        paused = [e for e in events if e[0] == protocol.EV_PAUSED]
        self.assertEqual(paused, [(protocol.EV_PAUSED,
                                   {"reason": protocol.PAUSE_REASON_REQUEST,
                                    "by": 1})])
        self.assertTrue(m.paused)
        # Already at the centre.
        self.assertEqual(m.phase, protocol.PHASE_COUNTDOWN)
        self.assertEqual(m.snapshot(1)["pause_by"], 1)
        self.assertTrue(m.resume())
        self.assertIsNone(m.pause_pending)


class InterpolatorTest(unittest.TestCase):
    def test_smooths_between_states_but_not_teleports(self):
        m = match.Match(1)
        a = m.snapshot(1)
        m.players[0].x += 20
        m.ball.x += 400                 # kickoff from the centre: not smoothed
        b = m.snapshot(2)
        it = interp.Interpolator()
        it.push(a, 0.0)
        it.push(b, 1 / 30)
        mid = it.sample(1 / 30 + 1 / 60)
        self.assertLess(a["players"][0]["x"], mid["players"][0]["x"])
        self.assertLess(mid["players"][0]["x"], b["players"][0]["x"])
        self.assertEqual(mid["ball"]["x"], b["ball"]["x"])
        self.assertFalse(it.push(a, 0.1))            # old snapshot: ignored


class WireTest(unittest.TestCase):
    def test_validation(self):
        for raw in ("{not json", '{"type": "delete_everything"}'):
            with self.assertRaises(wire.WireError):
                wire.decode(raw, wire.CLIENT_TYPES)
        for bad in ([True, False, -1, 0], [True, False, "3", 0]):
            with self.assertRaises(wire.WireError):
                wire.clean_input(bad)
        self.assertEqual(wire.clean_input([1, 0, 3, 4]), [True, False, 3, 4])

    def test_compact_state_is_smaller_and_complete(self):
        st = match.Match(1).snapshot(5)
        st["dropped_states"] = 0
        small = wire.compact_state(st)
        self.assertLess(len(wire.encode(small)), len(wire.encode(st)))
        self.assertEqual(set(small) | {"dropped_states"}, set(st))


# ---------------------------------------------------------------------------
# Real server
# ---------------------------------------------------------------------------
def _get(url):
    with urllib.request.urlopen(url) as r:
        return r.read()


class ServerLobbyTest(unittest.TestCase):
    def test_names_rooms_passwords_and_bad_messages(self):
        with ServerThread() as srv:
            a = Client(srv.url, "Ale", player_id="profile-a")
            b = self.second_ale(srv, a)
            self.check_private_room(a, b)
            for c in (a, b):
                c.close()

    def second_ale(self, srv, a):
        """Another Ale: a bad name fails; the same name is valid."""
        b = Client(srv.url)
        b.send({"type": wire.HELLO, "username": "x"})
        self.assertEqual(b.wait(wire.ERROR)["code"], "invalid_name")
        b.send({"type": wire.HELLO, "username": "Ale",
                "player_id": "profile-b"})
        wb = b.wait(wire.WELCOME)
        self.assertEqual(wb["username"], "Ale")
        # The tag tells them apart.
        self.assertNotEqual(wb["tag"], a.welcome["tag"])
        return b

    def check_private_room(self, a, b):
        a.send({"type": wire.CREATE_ROOM, "name": "Privada",
                "password": "1234"})
        rid = a.wait(wire.ROOM)["room"]
        rooms = b.wait(wire.ROOMS, cond=lambda m: m["rooms"])["rooms"]
        self.assertEqual((rooms[0]["owner"], rooms[0]["private"]),
                         (a.welcome["display"], True))
        self.check_bad_messages(b, rid)
        b.send({"type": wire.JOIN_ROOM, "room": rid, "password": "1234"})
        self.check_members(b.wait(wire.ROOM)["members"])

    def check_bad_messages(self, b, rid):
        b.send({"type": wire.JOIN_ROOM, "room": rid, "password": "0000"})
        self.assertEqual(b.wait(wire.ERROR)["code"], "wrong_password")
        b.send_raw("{this is not json")
        self.assertEqual(b.wait(wire.ERROR)["code"], "invalid_message")
        # Outside a match: ignored.
        b.send({"type": wire.INPUT, "p": [True, False, -5, 0]})

    def check_members(self, members):
        self.assertEqual([m["username"] for m in members], ["Ale", "Ale"])
        self.assertEqual(len({(m["username"], m["tag"]) for m in members}), 2)

    def test_static_files_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "index.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("<html>hola</html>")
            with ServerThread(web_dir=tmp) as srv:
                base = f"http://127.0.0.1:{srv.server.port}"
                with urllib.request.urlopen(base + "/") as r:
                    self.assertIn(b"hola", r.read())
                    self.assertIn("text/html", r.headers["Content-Type"])
                with self.assertRaises(urllib.error.HTTPError) as err:
                    _get(base + "/../../config.py")
                err.exception.close()
                self.check_localhost_redirect(srv.server.port)

    def check_localhost_redirect(self, port):
        """pygbag does not start served from localhost:8...: redirected to
        127.0.0.1."""
        conn = http.client.HTTPConnection("127.0.0.1", port,
                                          timeout=HTTP_TIMEOUT)
        conn.request("GET", "/", headers={"Host": f"localhost:{port}"})
        r = conn.getresponse()
        self.assertEqual((r.status, r.getheader("Location")),
                         (REDIRECT, f"http://127.0.0.1:{port}/"))
        r.read()
        r.close()
        conn.close()

    def test_panel_public_and_protected(self):
        with ServerThread(panel_password="secret") as srv:
            base = f"http://127.0.0.1:{srv.server.port}"
            page = _get(base + "/status").decode("utf-8")
            self.assertIn("Panel del servidor", page)
            a = Client(srv.url, "Ale")
            a.send({"type": wire.CREATE_ROOM, "name": "Secreta"})
            a.wait(wire.ROOM)
            self.check_public(json.loads(_get(base + "/status.json")))
            self.check_full(base)
            a.close()
        self.check_no_full_panel()

    def check_no_full_panel(self):
        with ServerThread() as srv:               # no password configured
            with self.assertRaises(urllib.error.HTTPError) as err:
                _get(f"http://127.0.0.1:{srv.server.port}/status/full")
            self.assertEqual(err.exception.code, NOT_FOUND)
            err.exception.close()

    def check_public(self, data):
        self.assertEqual((data["view"], data["connections"],
                          len(data["rooms"])), ("public", 1, 1))
        self.assertIn("principal (bucle asyncio)", data["threads"])
        # The public view shows no names.
        self.assertNotIn("Ale", json.dumps(data))
        self.assertNotIn("Secreta", json.dumps(data))

    def check_full(self, base):
        with self.assertRaises(urllib.error.HTTPError) as err:
            _get(base + "/status/full.json")       # no password: 401
        self.assertEqual(err.exception.code, UNAUTHORIZED)
        err.exception.close()
        auth = base64.b64encode(b"panel:secret").decode()
        req = urllib.request.Request(base + "/status/full.json", headers={
            "Authorization": "Basic " + auth})
        with urllib.request.urlopen(req) as r:
            full = json.loads(r.read())
        self.assertEqual(full["view"], "full")
        self.assertEqual(full["rooms"][0]["name"], "Secreta")
        self.assertTrue(full["players"][0]["name"].startswith("Ale #"))


class ServerMatchTest(unittest.TestCase):
    def test_match_states_end_and_rematch_with_new_sides(self):
        with ServerThread(duration=3.0, seed=4) as srv:
            a, b, sa, sb, _ = start_match(srv)
            # Sides given by the system.
            self.assertEqual({sa["you"], sb["you"]}, {0, 1})
            self.check_room_process(a, sa)
            for _ in range(INPUT_SENDS):
                a.send({"type": wire.INPUT, "p": [False, True, 0, 0]})
                time.sleep(INPUT_GAP)
            self.check_end_and_rematch(a, b, sa)
            for c in (a, b):
                c.close()

    def check_room_process(self, a, sa):
        st = a.wait(wire.STATE, cond=lambda m: m["match"] == sa["match"])
        self.assertIn("players", st)
        info = a.wait(wire.ROOM_INFO, timeout=5)    # for the F3 panel
        self.assertIsNotNone(info["sim_pid"])
        # The room runs in another process.
        self.assertNotEqual(info["sim_pid"], info["server_pid"])

    def check_end_and_rematch(self, a, b, sa):
        over = b.wait(wire.MATCH_OVER, timeout=15)
        self.assertEqual(over["reason"], wire.END_TIME)
        room = a.wait(wire.ROOM, cond=lambda m: m["state"] == lobby.CHOOSING)
        self.assertFalse(any(m["ready"] for m in room["members"]))
        a.send({"type": wire.READY})     # rematch: the same characters
        b.send({"type": wire.READY})
        ra = a.wait(wire.MATCH_START, cond=lambda m: m["match"] != sa["match"])
        self.assertEqual({p["username"] for p in ra["players"]},
                         {"Ale", "Bruno"})

    def test_abandon_gives_the_win_and_room_stays_open(self):
        with ServerThread() as srv:
            a, b, _, sb, _ = start_match(srv)
            b.wait(wire.STATE)
            a.send({"type": wire.ABANDON})
            self.check_forfeit(b, sb, a.welcome["display"])
            room = b.wait(wire.ROOM,
                          cond=lambda m: m["state"] == lobby.WAITING)
            # The room stays open.
            self.assertEqual(room["owner"], b.welcome["display"])
            a.wait(wire.ROOMS)              # who left goes back to the list
            for c in (a, b):
                c.close()

    def check_forfeit(self, b, sb, quitter):
        over = b.wait(wire.MATCH_OVER)
        self.assertEqual((over["winner"], over["reason"], over["by_name"]),
                         (sb["you"], wire.END_FORFEIT, quitter))
        b.wait(wire.OPPONENT_LEFT)

    def test_disconnect_pause_and_reconnect_with_token(self):
        with ServerThread(grace=8.0) as srv:
            a, b, sa, _, _ = start_match(srv)
            b.wait(wire.STATE, timeout=10, cond=lambda m: m["phase"]
                   == protocol.PHASE_PLAYING)
            a.kill()                        # the network of Ale drops
            self.check_disconnect_seen(b, a.welcome["display"])
            a2 = self.reconnect(srv, a, sa)
            b.wait(wire.OPPONENT, cond=lambda m: m["connected"])
            # The match goes on.
            b.wait(wire.STATE, cond=lambda m: not m["paused"])
            for c in (a2, b):
                c.close()

    def check_disconnect_seen(self, b, name):
        opp = b.wait(wire.OPPONENT, cond=lambda m: not m["connected"])
        self.assertEqual(opp["name"], name)
        b.wait(wire.STATE, cond=lambda m: m["paused"] and m[
            "pause_reason"] == protocol.PAUSE_REASON_DISCONNECT)

    def reconnect(self, srv, a, sa):
        a2 = Client(srv.url)
        a2.send({"type": wire.HELLO, "username": "Ale", "token": a.token})
        self.assertTrue(a2.wait(wire.WELCOME)["restored"])
        back = a2.wait(wire.MATCH_START)
        self.assertEqual((back["match"], back["you"]),
                         (sa["match"], sa["you"]))
        return a2

    def test_no_return_within_grace_loses_by_forfeit(self):
        with ServerThread(grace=1.0) as srv:
            a, b, _, sb, _ = start_match(srv)
            b.wait(wire.STATE)
            a.kill()
            over = b.wait(wire.MATCH_OVER, timeout=10)
            self.assertEqual((over["winner"], over["reason"]),
                             (sb["you"], wire.END_FORFEIT))
            b.wait(wire.OPPONENT_LEFT)
            c = Client(srv.url, "Ale")
            c.close()
            b.close()


if __name__ == "__main__":
    unittest.main()
