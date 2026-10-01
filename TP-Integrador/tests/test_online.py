"""Modo online: servidor real con conexiones WebSocket reales y lógica de sala."""
import os
import tempfile
import time
import unittest
import urllib.request

try:
    import websockets  # noqa: F401
except ImportError:  # el juego local no lo necesita: sin websockets se saltean
    raise unittest.SkipTest("falta websockets (pip install -r requirements-online.txt)") from None

import helpers  # noqa: F401
from online_helpers import Client, ServerThread, start_match

from fdc import protocol as P
from fdc.online import wire as W
from fdc.online.interp import Interpolator
from fdc.online.server import GameServer, RoomRunner
from fdc.sim.match import Match


# ---------------------------------------------------------------------------
# Puente de la sala sin procesos: pausa pedida, "listo", desconexiones
# ---------------------------------------------------------------------------
class FakeLink:
    ready = True
    sim_pid = None

    def __init__(self):
        self.cmds, self.events, self.state, self.inputs = [], [], None, None

    def start(self):
        pass

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
    def __init__(self):
        self.msgs = []

    def send(self, msg):
        self.msgs.append(msg)

    def send_text(self, text, replaceable=False):
        self.msgs.append(W.decode(text))

    def last(self, mtype):
        found = [m for m in self.msgs if m["type"] == mtype]
        return found[-1] if found else None


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.server = GameServer(web_dir=None, pause_max=30.0, sim_logs=False)
        self.server.deliver = lambda out: None
        self.a, self.b = FakeSession(), FakeSession()
        self.server.sessions = {"a": self.a, "b": self.b}
        self.r = RoomRunner(self.server, 1)
        self.r.link = self.link = FakeLink()
        self.r.match = {"id": 7, "sids": ["a", "b"], "names": ["Ale", "Bruno"], "chars": ["messi", "pele"],
                        "start_msgs": [{"type": "match_start", "match": 7, "you": 0},
                                       {"type": "match_start", "match": 7, "you": 1}]}
        m = Match(7)
        m.phase = P.PHASE_PLAYING
        self.r.last_state = m.snapshot(1)
        self.match = m

    def cmds(self, ctype):
        return [kw for c, kw in self.link.cmds if c == ctype]

    def activate_pause(self, now):
        self.link.events = [{"type": P.EV_PAUSED, "reason": P.PAUSE_REASON_REQUEST, "by": 0,
                             "match": 7, "eid": 3}]
        self.r.tick(now)

    def test_pause_request_waits_for_goal_then_both_ready(self):
        self.r.request_pause(0)
        self.assertEqual(self.cmds(P.CMD_PAUSE), [{"after_goal": True, "by": 0, "reason": P.PAUSE_REASON_REQUEST}])
        info = self.b.last(W.PAUSE_INFO)                    # el rival ve quién la pidió
        self.assertEqual((info["status"], info["by_name"]), (W.PAUSE_PENDING, "Ale"))
        self.r.request_pause(1)                             # ya hay una pedida: no se repite
        self.assertEqual(len(self.cmds(P.CMD_PAUSE)), 1)
        self.activate_pause(100.0)
        self.assertEqual(self.a.last(W.PAUSE_INFO)["status"], W.PAUSE_ACTIVE)
        self.r.pause_ready(0)
        self.r.tick(101.0)
        self.assertEqual(self.cmds(P.CMD_RESUME), [])       # falta el otro
        self.assertEqual(self.b.last(W.PAUSE_INFO)["ready"], [True, False])
        self.r.pause_ready(1)
        self.r.tick(101.5)
        self.assertEqual(len(self.cmds(P.CMD_RESUME)), 1)
        self.assertEqual(self.a.last(W.PAUSE_INFO)["status"], W.PAUSE_NONE)

    def test_pause_resumes_alone_after_limit(self):
        self.r.request_pause(1)
        self.activate_pause(100.0)
        self.r.tick(129.0)
        self.assertEqual(self.cmds(P.CMD_RESUME), [])
        self.r.tick(130.1)
        self.assertEqual(len(self.cmds(P.CMD_RESUME)), 1)

    def test_disconnect_keeps_match_paused_until_return(self):
        self.r.request_pause(0)
        self.activate_pause(100.0)
        self.r.player_away(1, time.monotonic() + 30)
        self.assertEqual(self.cmds(P.CMD_PAUSE)[-1], {"reason": P.PAUSE_REASON_DISCONNECT})
        self.assertFalse(self.a.last(W.OPPONENT)["connected"])
        self.r.pause_ready(0)
        self.r.pause_ready(1)
        self.r.tick(101.0)                                  # terminó la pausa pedida...
        self.assertEqual(self.cmds(P.CMD_RESUME), [])       # ...pero falta que vuelva
        back = FakeSession()
        self.server.sessions["b"] = back
        self.r.player_back(1, back)
        self.assertEqual(back.msgs[0]["type"], "match_start")   # vuelve a su partido
        self.assertTrue(self.a.last(W.OPPONENT)["connected"])
        self.assertEqual(len(self.cmds(P.CMD_RESUME)), 1)

    def test_forfeit_gives_the_win_to_who_stayed(self):
        self.r.forfeit(0)
        over = self.b.last(W.MATCH_OVER)
        self.assertEqual((over["winner"], over["reason"], over["by_name"]), (1, W.END_FORFEIT, "Ale"))
        self.assertIn(P.CMD_END, [c for c, _ in self.link.cmds])
        self.assertIsNone(self.r.match)

    def test_inputs_and_states_are_forwarded(self):
        self.r.set_input(1, [False, True, 2, 1])
        self.link.state = self.match.snapshot(2)
        self.r.tick(50.0)
        self.assertEqual(self.link.inputs[1], [False, True, 2, 1])
        st = self.a.last(W.STATE)
        self.assertEqual((st["match"], st["seq"]), (7, 2))
        self.assertNotIn("dropped_states", st)


class PauseAfterGoalTest(unittest.TestCase):
    def test_match_pauses_only_after_next_goal(self):
        m = helpers.playing_match()
        self.assertTrue(m.request_pause_after_goal(1))
        helpers.run(m, 1.0)
        self.assertFalse(m.paused)                          # la jugada sigue
        m.ball.x, m.ball.y, m.ball.vx, m.ball.vy = 60, 600, -400, 0     # gol en el arco izquierdo
        events = helpers.run(m, 0.2)
        self.assertEqual(helpers.count(events, P.EV_GOAL), 1)
        self.assertFalse(m.paused)                          # festejo del gol
        events = helpers.run(m, 3.0)
        paused = [e for e in events if e[0] == P.EV_PAUSED]
        self.assertEqual(paused, [(P.EV_PAUSED, {"reason": P.PAUSE_REASON_REQUEST, "by": 1})])
        self.assertTrue(m.paused)
        self.assertEqual(m.phase, P.PHASE_COUNTDOWN)        # ya en el centro
        self.assertEqual(m.snapshot(1)["pause_by"], 1)
        self.assertTrue(m.resume())
        self.assertIsNone(m.pause_pending)


class InterpolatorTest(unittest.TestCase):
    def test_smooths_between_states_but_not_teleports(self):
        m = Match(1)
        a = m.snapshot(1)
        m.players[0].x += 20
        m.ball.x += 400                                     # saque del medio: no se suaviza
        b = m.snapshot(2)
        it = Interpolator()
        it.push(a, 0.0)
        it.push(b, 1 / 30)
        mid = it.sample(1 / 30 + 1 / 60)
        self.assertLess(a["players"][0]["x"], mid["players"][0]["x"])
        self.assertLess(mid["players"][0]["x"], b["players"][0]["x"])
        self.assertEqual(mid["ball"]["x"], b["ball"]["x"])
        self.assertFalse(it.push(a, 0.1))                   # foto vieja: se ignora


class WireTest(unittest.TestCase):
    def test_validation(self):
        with self.assertRaises(W.WireError):
            W.decode("{no es json", W.CLIENT_TYPES)
        with self.assertRaises(W.WireError):
            W.decode('{"type": "borrar_todo"}', W.CLIENT_TYPES)
        with self.assertRaises(W.WireError):
            W.clean_input([True, False, -1, 0])
        with self.assertRaises(W.WireError):
            W.clean_input([True, False, "3", 0])
        self.assertEqual(W.clean_input([1, 0, 3, 4]), [True, False, 3, 4])

    def test_compact_state_is_smaller_and_complete(self):
        st = Match(1).snapshot(5)
        st["dropped_states"] = 0
        small = W.compact_state(st)
        self.assertLess(len(W.encode(small)), len(W.encode(st)))
        self.assertEqual(set(small) | {"dropped_states"}, set(st))


# ---------------------------------------------------------------------------
# Servidor real
# ---------------------------------------------------------------------------
class ServerLobbyTest(unittest.TestCase):
    def test_names_rooms_passwords_and_bad_messages(self):
        with ServerThread() as srv:
            a = Client(srv.url, "Ale")
            b = Client(srv.url)
            b.send({"type": "hello", "username": "ale"})
            self.assertEqual(b.wait("error")["code"], "nombre_en_uso")
            b.send({"type": "hello", "username": "Bruno"})       # reintento en la misma conexión
            b.wait("welcome")
            a.send({"type": "create_room", "name": "Privada", "password": "1234"})
            rid = a.wait("room")["room"]
            rooms = b.wait("rooms", cond=lambda m: m["rooms"])["rooms"]
            self.assertEqual((rooms[0]["owner"], rooms[0]["private"]), ("Ale", True))
            b.send({"type": "join_room", "room": rid, "password": "0000"})
            self.assertEqual(b.wait("error")["code"], "clave_incorrecta")
            b.send_raw("{esto no es json")
            self.assertEqual(b.wait("error")["code"], "mensaje_invalido")
            b.send({"type": "input", "p": [True, False, -5, 0]})   # fuera de partido: se ignora
            b.send({"type": "join_room", "room": rid, "password": "1234"})
            self.assertEqual(len(b.wait("room")["members"]), 2)
            for c in (a, b):
                c.close()

    def test_static_files_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as fh:
                fh.write("<html>hola</html>")
            with ServerThread(web_dir=tmp) as srv:
                base = f"http://127.0.0.1:{srv.server.port}"
                with urllib.request.urlopen(base + "/") as r:
                    self.assertIn(b"hola", r.read())
                    self.assertIn("text/html", r.headers["Content-Type"])
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(base + "/../../config.py")
                with urllib.request.urlopen(base + "/estado") as r:
                    self.assertIn(b"salas 0", r.read())


class ServerMatchTest(unittest.TestCase):
    def test_match_states_end_and_rematch_with_new_sides(self):
        with ServerThread(duration=3.0, seed=4) as srv:
            a, b, sa, sb, rid = start_match(srv)
            self.assertEqual({sa["you"], sb["you"]}, {0, 1})     # lados asignados por el sistema
            st = a.wait("state", cond=lambda m: m["match"] == sa["match"])
            self.assertIn("players", st)
            for _ in range(20):
                a.send({"type": "input", "p": [False, True, 0, 0]})
                time.sleep(0.02)
            over = b.wait("match_over", timeout=15)
            self.assertEqual(over["reason"], W.END_TIME)
            room = a.wait("room", cond=lambda m: m["state"] == "eligiendo")
            self.assertFalse(any(m["ready"] for m in room["members"]))
            a.send({"type": "ready"})                          # revancha: mismos personajes
            b.send({"type": "ready"})
            ra = a.wait("match_start", cond=lambda m: m["match"] != sa["match"])
            self.assertEqual({p["username"] for p in ra["players"]}, {"Ale", "Bruno"})
            for c in (a, b):
                c.close()

    def test_abandon_gives_the_win_and_room_stays_open(self):
        with ServerThread() as srv:
            a, b, sa, sb, rid = start_match(srv)
            b.wait("state")
            a.send({"type": "abandon"})
            over = b.wait("match_over")
            self.assertEqual((over["winner"], over["reason"], over["by_name"]), (sb["you"], W.END_FORFEIT, "Ale"))
            b.wait("opponent_left")
            room = b.wait("room", cond=lambda m: m["state"] == "esperando")
            self.assertEqual(room["owner"], "Bruno")              # la sala sigue abierta
            a.wait("rooms")                                        # quien abandonó vuelve a la lista
            for c in (a, b):
                c.close()

    def test_disconnect_pause_and_reconnect_with_token(self):
        with ServerThread(grace=8.0) as srv:
            a, b, sa, sb, rid = start_match(srv)
            b.wait("state", cond=lambda m: m["phase"] == "playing", timeout=10)
            a.kill()                                               # se corta la red de Ale
            opp = b.wait("opponent", cond=lambda m: not m["connected"])
            self.assertEqual(opp["name"], "Ale")
            b.wait("state", cond=lambda m: m["paused"] and m["pause_reason"] == P.PAUSE_REASON_DISCONNECT)
            a2 = Client(srv.url)
            a2.send({"type": "hello", "username": "Ale", "token": a.token})
            self.assertTrue(a2.wait("welcome")["restored"])
            back = a2.wait("match_start")
            self.assertEqual((back["match"], back["you"]), (sa["match"], sa["you"]))
            b.wait("opponent", cond=lambda m: m["connected"])
            b.wait("state", cond=lambda m: not m["paused"])        # el partido sigue
            for c in (a2, b):
                c.close()

    def test_no_return_within_grace_loses_by_forfeit(self):
        with ServerThread(grace=1.0) as srv:
            a, b, sa, sb, rid = start_match(srv)
            b.wait("state")
            a.kill()
            over = b.wait("match_over", timeout=10)
            self.assertEqual((over["winner"], over["reason"]), (sb["you"], W.END_FORFEIT))
            b.wait("opponent_left")
            c = Client(srv.url, "Ale")                             # el nombre quedó libre
            c.close()
            b.close()


if __name__ == "__main__":
    unittest.main()
