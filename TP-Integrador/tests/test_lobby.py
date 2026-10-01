"""Salas del futuro modo online (lógica pura, sin red)."""
import random
import unittest

import helpers  # noqa: F401
from fdc.online.lobby import CHOOSING, PLAYING, WAITING, Lobby


def msgs_for(out, conn, mtype=None):
    return [m for targets, m in out if conn in targets and (mtype is None or m["type"] == mtype)]


class LobbyTest(unittest.TestCase):
    def setUp(self):
        self.lobby = Lobby(rng=random.Random(3))

    def hello(self, conn, name):
        return self.lobby.handle(conn, {"type": "hello", "username": name})

    def test_username_rules(self):
        self.assertEqual(msgs_for(self.hello("a", "Ale"), "a", "welcome")[0]["username"], "Ale")
        err = msgs_for(self.hello("b", "ale"), "b", "error")[0]
        self.assertEqual(err["code"], "nombre_en_uso")
        self.assertEqual(msgs_for(self.hello("c", "x"), "c", "error")[0]["code"], "nombre_invalido")
        out = self.lobby.handle("d", {"type": "list_rooms"})
        self.assertEqual(msgs_for(out, "d", "error")[0]["code"], "sin_nombre")

    def test_create_list_and_join_public_room(self):
        self.hello("a", "Ale")
        self.hello("b", "Bruno")
        out = self.lobby.handle("a", {"type": "create_room", "name": "Picadito"})
        room = msgs_for(out, "a", "room")[0]
        self.assertEqual(room["owner"], "Ale")
        self.assertEqual(room["state"], WAITING)
        rooms = msgs_for(out, "b", "rooms")[0]["rooms"]          # quien mira la lista la ve
        self.assertEqual([(r["name"], r["owner"], r["private"]) for r in rooms], [("Picadito", "Ale", False)])
        out = self.lobby.handle("b", {"type": "join_room", "room": room["room"]})
        detail = msgs_for(out, "a", "room")[0]
        self.assertEqual(detail["state"], CHOOSING)
        self.assertEqual([m["username"] for m in detail["members"]], ["Ale", "Bruno"])

    def test_private_room_needs_password(self):
        self.hello("a", "Ale")
        self.hello("b", "Bruno")
        rid = msgs_for(self.lobby.handle("a", {"type": "create_room", "password": "1234"}), "a", "room")[0]["room"]
        summary = msgs_for(self.lobby.handle("b", {"type": "list_rooms"}), "b", "rooms")[0]["rooms"][0]
        self.assertTrue(summary["private"])
        self.assertNotIn("password", str(summary))                  # nunca se expone
        err = msgs_for(self.lobby.handle("b", {"type": "join_room", "room": rid, "password": "0000"}), "b", "error")
        self.assertEqual(err[0]["code"], "clave_incorrecta")
        ok = self.lobby.handle("b", {"type": "join_room", "room": rid, "password": "1234"})
        self.assertTrue(msgs_for(ok, "b", "room"))

    def test_room_is_one_vs_one(self):
        for c, n in (("a", "Ale"), ("b", "Bruno"), ("c", "Caro")):
            self.hello(c, n)
        rid = msgs_for(self.lobby.handle("a", {"type": "create_room"}), "a", "room")[0]["room"]
        self.lobby.handle("b", {"type": "join_room", "room": rid})
        err = msgs_for(self.lobby.handle("c", {"type": "join_room", "room": rid}), "c", "error")
        self.assertEqual(err[0]["code"], "sala_llena")

    def test_choose_ready_and_automatic_sides(self):
        self.hello("a", "Ale")
        self.hello("b", "Bruno")
        rid = msgs_for(self.lobby.handle("a", {"type": "create_room"}), "a", "room")[0]["room"]
        err = msgs_for(self.lobby.handle("a", {"type": "choose_character", "character": "messi"}), "a", "error")
        self.assertEqual(err[0]["code"], "no_se_puede_elegir")      # falta el rival
        self.lobby.handle("b", {"type": "join_room", "room": rid})
        self.lobby.handle("a", {"type": "choose_character", "character": "messi"})
        self.lobby.handle("b", {"type": "choose_character", "character": "messi"})   # se puede repetir
        out = self.lobby.handle("a", {"type": "ready"})
        self.assertFalse(msgs_for(out, "a", "match_start"))
        out = self.lobby.handle("b", {"type": "ready"})
        start_a = msgs_for(out, "a", "match_start")[0]
        start_b = msgs_for(out, "b", "match_start")[0]
        self.assertEqual(start_a["match"], start_b["match"])
        self.assertEqual({start_a["you"], start_b["you"]}, {0, 1})   # un lado para cada uno
        sides = {p["side"]: p["username"] for p in start_a["players"]}
        self.assertEqual(set(sides.values()), {"Ale", "Bruno"})
        self.assertEqual(self.lobby.rooms[rid].state, PLAYING)
        self.lobby.finish_match(rid)                                   # revancha: vuelven a elegir
        self.assertEqual(self.lobby.rooms[rid].state, CHOOSING)

    def test_leave_and_disconnect(self):
        self.hello("a", "Ale")
        self.hello("b", "Bruno")
        rid = msgs_for(self.lobby.handle("a", {"type": "create_room"}), "a", "room")[0]["room"]
        self.lobby.handle("b", {"type": "join_room", "room": rid})
        out = self.lobby.disconnect("a")                              # se corta el creador
        self.assertTrue(msgs_for(out, "b", "opponent_left"))
        self.assertEqual(self.lobby.rooms[rid].owner, "Bruno")
        self.assertEqual(self.lobby.rooms[rid].state, WAITING)
        self.lobby.handle("b", {"type": "leave_room"})
        self.assertNotIn(rid, self.lobby.rooms)                        # sala vacía: desaparece
        self.assertTrue(msgs_for(self.hello("c", "Ale"), "c", "welcome"))   # el nombre quedó libre


if __name__ == "__main__":
    unittest.main()
