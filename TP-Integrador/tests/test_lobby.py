"""Online rooms (pure logic, no network)."""
import random
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc.online import lobby
from fdc.online import wire


def msgs_for(out, conn, mtype=None):
    """Messages of 'out' that go to conn (only of that type, if given)."""
    return [m for targets, m in out
            if conn in targets and (mtype is None or m["type"] == mtype)]


class LobbyTest(unittest.TestCase):
    def setUp(self):
        self.lobby = lobby.Lobby(rng=random.Random(3))

    def hello(self, conn, name, player_id=None):
        return self.lobby.handle(conn, {"type": wire.HELLO, "username": name,
                                        "player_id": player_id or conn})

    def send(self, conn, mtype, **fields):
        return self.lobby.handle(conn, {"type": mtype, **fields})

    def two_players_room(self):
        """Ale creates a room and Bruno is connected; returns the room."""
        self.hello("a", "Ale")
        self.hello("b", "Bruno")
        out = self.send("a", wire.CREATE_ROOM)
        return msgs_for(out, "a", wire.ROOM)[0]["room"]

    def error_code(self, out, conn):
        return msgs_for(out, conn, wire.ERROR)[0]["code"]

    def test_username_rules(self):
        wa = msgs_for(self.hello("a", "Ale", "profile-1"), "a",
                      wire.WELCOME)[0]
        self.assertEqual((wa["username"], wa["display"]),
                         ("Ale", f"Ale #{wa['tag']:04d}"))
        # Another one with the SAME name (even the same profile opened
        # twice): another tag.
        wb = msgs_for(self.hello("b", "ale", "profile-1"), "b",
                      wire.WELCOME)[0]
        self.assertNotEqual(wa["tag"], wb["tag"])
        self.assertEqual(self.error_code(self.hello("c", "x"), "c"),
                         "invalid_name")
        self.check_same_tag_again(wa["tag"])

    def check_same_tag_again(self, tag):
        """The tag comes from the profile: the same person gets it back."""
        self.lobby.disconnect("a")
        self.lobby.disconnect("b")
        again = msgs_for(self.hello("e", "Ale", "profile-1"), "e",
                         wire.WELCOME)[0]
        self.assertEqual(again["tag"], tag)
        out = self.send("d", wire.LIST_ROOMS)
        self.assertEqual(self.error_code(out, "d"), "no_name")

    def test_create_list_and_join_public_room(self):
        self.hello("a", "Ale")
        self.hello("b", "Bruno")
        out = self.send("a", wire.CREATE_ROOM, name="Picadito")
        room = msgs_for(out, "a", wire.ROOM)[0]
        self.assertTrue(room["owner"].startswith("Ale #"))
        self.assertEqual(room["state"], lobby.WAITING)
        # Who looks at the list sees it.
        rooms = msgs_for(out, "b", wire.ROOMS)[0]["rooms"]
        self.assertEqual([(r["name"], r["owner"][:5], r["private"])
                          for r in rooms], [("Picadito", "Ale #", False)])
        self.check_join(room["room"])

    def check_join(self, rid):
        out = self.send("b", wire.JOIN_ROOM, room=rid)
        detail = msgs_for(out, "a", wire.ROOM)[0]
        self.assertEqual(detail["state"], lobby.CHOOSING)
        self.assertEqual([m["username"] for m in detail["members"]],
                         ["Ale", "Bruno"])

    def test_private_room_needs_password(self):
        self.hello("a", "Ale")
        self.hello("b", "Bruno")
        rid = msgs_for(self.send("a", wire.CREATE_ROOM, password="1234"),
                       "a", wire.ROOM)[0]["room"]
        summary = msgs_for(self.send("b", wire.LIST_ROOMS), "b",
                           wire.ROOMS)[0]["rooms"][0]
        self.assertTrue(summary["private"])
        self.assertNotIn("password", str(summary))       # never exposed
        out = self.send("b", wire.JOIN_ROOM, room=rid, password="0000")
        self.assertEqual(self.error_code(out, "b"), "wrong_password")
        ok = self.send("b", wire.JOIN_ROOM, room=rid, password="1234")
        self.assertTrue(msgs_for(ok, "b", wire.ROOM))

    def test_room_is_one_vs_one(self):
        rid = self.two_players_room()
        self.hello("c", "Caro")
        self.send("b", wire.JOIN_ROOM, room=rid)
        out = self.send("c", wire.JOIN_ROOM, room=rid)
        self.assertEqual(self.error_code(out, "c"), "room_full")

    def test_choose_ready_and_automatic_sides(self):
        rid = self.two_players_room()
        out = self.send("a", wire.CHOOSE_CHARACTER, character="messi")
        # The rival is missing.
        self.assertEqual(self.error_code(out, "a"), "cannot_choose")
        self.send("b", wire.JOIN_ROOM, room=rid)
        self.send("a", wire.CHOOSE_CHARACTER, character="messi")
        # The same one can be chosen twice.
        self.send("b", wire.CHOOSE_CHARACTER, character="messi")
        out = self.send("a", wire.READY)
        self.assertFalse(msgs_for(out, "a", wire.MATCH_START))
        self.check_match_start(self.send("b", wire.READY), rid)

    def check_match_start(self, out, rid):
        start_a = msgs_for(out, "a", wire.MATCH_START)[0]
        start_b = msgs_for(out, "b", wire.MATCH_START)[0]
        self.assertEqual(start_a["match"], start_b["match"])
        # One side for each one.
        self.assertEqual({start_a["you"], start_b["you"]}, {0, 1})
        sides = {p["side"]: p["username"] for p in start_a["players"]}
        self.assertEqual(set(sides.values()), {"Ale", "Bruno"})
        self.assertEqual(self.lobby.rooms[rid].state, lobby.PLAYING)
        self.lobby.finish_match(rid)          # rematch: they choose again
        self.assertEqual(self.lobby.rooms[rid].state, lobby.CHOOSING)

    def test_leave_and_disconnect(self):
        rid = self.two_players_room()
        self.send("b", wire.JOIN_ROOM, room=rid)
        out = self.lobby.disconnect("a")             # the owner drops
        self.assertTrue(msgs_for(out, "b", wire.OPPONENT_LEFT))
        self.assertTrue(self.lobby.rooms[rid].owner.startswith("Bruno #"))
        self.assertEqual(self.lobby.rooms[rid].state, lobby.WAITING)
        self.send("b", wire.LEAVE_ROOM)
        self.assertNotIn(rid, self.lobby.rooms)      # empty room: it goes
        self.assertTrue(msgs_for(self.hello("c", "Ale"), "c", wire.WELCOME))


if __name__ == "__main__":
    unittest.main()
