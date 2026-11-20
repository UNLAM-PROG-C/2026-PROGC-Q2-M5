"""Rooms of the online mode (1 against 1). Pure logic, WITHOUT network.

This module implements the rules agreed for the online mode:
  * each person enters with the name chosen when opening the game (no
    accounts). Names can repeat: each connected person gets a 4-digit tag
    ("Ale #4821") that tells them apart from another one with the same name.
    The tag comes from the profile id, so it is the same every time that
    person enters (unless it clashes with another connected one);
  * a room can be free or have a password;
  * everybody sees the list of rooms with the name of who created each one
    and can join;
  * with 2 people in the room, each one chooses a character and confirms;
  * the system assigns the sides (left / right) automatically and starts
    the match.

It opens no sockets and does not know the transport: it receives messages
(dictionaries that can be sent as JSON) from an identified session and
returns the list of messages to send, with their receivers. The server
(fdc/online/server.py) only routes what comes in and what goes out.
"""
import hashlib
import hmac
import itertools
import os
import random

from fdc import config
from fdc import profile
from fdc.online import wire

MAX_PLAYERS = 2             # a room is always 1 against 1
TAGS = 10000                # tags #0000 to #9999
SALT_BYTES = 16             # random salt bytes per room password
# Hexadecimal digits of the profile hash used for the tag.
TAG_HASH_DIGITS = 8
HEX = 16                    # base of the hexadecimal digits
ROOM_NAME_MAX = 24          # most characters of a room name
# Password of a room (not of an account): this is enough and the hash takes
# a few ms, so it does not slow down the server loop that serves everybody.
PBKDF2_ROUNDS = 20_000

# Room states.
WAITING = "waiting"         # 1 person inside
CHOOSING = "choosing"       # 2 people choosing characters
PLAYING = "playing"

SIDE_NAMES = ("left", "right")


class LobbyError(Exception):
  """Usage error with a stable code (for the client) and a Spanish text
    (shown to the player)."""

  def __init__(self, code, message):
    super().__init__(message)
    self.code = code
    self.message = message


def _hash_password(password, salt):
  return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                             PBKDF2_ROUNDS)


class User:
  """A connected person: chosen name and tag."""

  def __init__(self, name, tag):
    self.name = name
    self.tag = tag

  @property
  def display(self):
    return f"{self.name} #{self.tag:04d}"

  def public(self):
    return {"username": self.name, "tag": self.tag,
            "display": self.display}


class Member:
  """A user inside a room, with the character chosen and the side."""

  def __init__(self, conn, user):
    self.conn = conn
    self.user = user
    self.character = None
    self.ready = False
    self.side = None
    self.connected = True       # False while waiting for it to come back

  @property
  def username(self):
    return self.user.name

  def public(self):
    return dict(self.user.public(), character=self.character,
                ready=self.ready, side=self.side,
                connected=self.connected)


class Room:
  """A 1 against 1 room, free or with a password."""

  def __init__(self, room_id, name, owner, password=None):
    self.id = room_id
    self.name = name
    self.owner = owner      # who created it, with the tag ("Ale #4821")
    self.salt = os.urandom(SALT_BYTES) if password else None
    self.password_hash = (_hash_password(password, self.salt)
                          if password else None)
    self.members = []
    self.state = WAITING
    self.matches_played = 0

  @property
  def private(self):
    return self.password_hash is not None

  def check_password(self, password):
    if not self.private:
      return True
    if not password:
      return False
    return hmac.compare_digest(self.password_hash,
                               _hash_password(password, self.salt))

  def member(self, conn):
    return next((m for m in self.members if m.conn == conn), None)

  def summary(self):
    """What anybody sees in the room list (never the password)."""
    return {"room": self.id, "name": self.name, "owner": self.owner,
            "private": self.private, "players": len(self.members),
            "max_players": MAX_PLAYERS, "state": self.state}

  def detail(self):
    data = self.summary()
    data["members"] = [m.public() for m in self.members]
    return data


class Lobby:
  """Users and rooms. A single thread/task must call handle()."""

  def __init__(self, rng=None, max_rooms=config.Online.MAX_ROOMS):
    self.rng = rng or random.Random()
    self.max_rooms = max_rooms
    self.users = {}                    # conn -> User (name + tag)
    self.rooms = {}                    # id -> Room
    self.room_of = {}                  # conn -> room id
    self._ids = itertools.count(1)
    self._match_ids = itertools.count(1)
    self._handlers = {
        wire.HELLO: self._hello, wire.LIST_ROOMS: self._list,
        wire.CREATE_ROOM: self._create, wire.JOIN_ROOM: self._join,
        wire.LEAVE_ROOM: self._leave, wire.CHOOSE_CHARACTER: self._choose,
        wire.READY: self._ready,
    }

  # ----------------------------------------------------------- single entry
  def handle(self, conn, msg):
    """Handles a message of a connection. Returns [(receivers, msg)]."""
    handler = self._handlers.get(msg.get("type"))
    try:
      if handler is None:
        raise LobbyError("unknown",
                         f"Mensaje desconocido: {msg.get('type')!r}")
      if msg.get("type") != "hello" and conn not in self.users:
        raise LobbyError("no_name", "Primero hay que elegir un "
                         "nombre de usuario.")
      return handler(conn, msg)
    except LobbyError as err:
      return [([conn], {"type": wire.ERROR, "code": err.code,
                        "message": err.message})]

  def disconnect(self, conn):
    """The connection is gone for good: it leaves its room and frees its
        tag."""
    out = self._leave(conn, {}) if conn in self.room_of else []
    self.users.pop(conn, None)
    return out

  def set_connected(self, conn, connected):
    """The connection dropped (or came back) but the session stays
        reserved: the rival sees it in the room and cannot start without
        it."""
    room = self.rooms.get(self.room_of.get(conn))
    me = room.member(conn) if room else None
    if me is None or me.connected == connected:
      return []
    me.connected = connected
    if not connected:
      me.ready = False
    return self._room_update(room)

  def room_of_conn(self, conn):
    return self.rooms.get(self.room_of.get(conn))

  def resync(self, conn):
    """Messages so a reconnected session sees where it was."""
    room = self.room_of_conn(conn)
    if room is None:
      return [([conn], self._rooms_msg())]
    return [([conn], {"type": wire.ROOM, **room.detail()})]

  # ------------------------------------------------------- users and rooms
  def _hello(self, conn, msg):
    name = (msg.get("username") or "").strip()
    if not profile.NAME_RE.match(name):
      raise LobbyError("invalid_name",
                       f"El nombre debe tener {profile.NAME_RULE}.")
    user = User(name, self._tag_for(conn, name, msg.get("player_id")))
    self.users[conn] = user
    return [([conn], {"type": wire.WELCOME, **user.public()}),
            ([conn], self._rooms_msg())]

  def _tag_for(self, conn, name, player_id):
    """Stable tag for that profile, different from the one of another
        connected person with the same name."""
    if (isinstance(player_id, str)
            and 0 < len(player_id) <= profile.MAX_PLAYER_ID):
      digest = hashlib.sha256(player_id.encode("utf-8")).hexdigest()
      tag = int(digest[:TAG_HASH_DIGITS], HEX) % TAGS
    else:
      tag = self.rng.randrange(TAGS)
    taken = {u.tag for c, u in self.users.items()
             if c != conn and u.name.lower() == name.lower()}
    while tag in taken:
      tag = (tag + 1) % TAGS
    return tag

  def user(self, conn):
    return self.users.get(conn)

  def _rooms_msg(self):
    rooms = sorted(self.rooms.values(), key=lambda r: r.id)
    return {"type": wire.ROOMS, "rooms": [r.summary() for r in rooms]}

  def _list(self, conn, msg):
    del msg  # Unused.
    return [([conn], self._rooms_msg())]

  def _lobby_conns(self):
    """Connections looking at the list (not inside a room)."""
    return [c for c in self.users if c not in self.room_of]

  def _broadcast_rooms(self):
    conns = self._lobby_conns()
    return [(conns, self._rooms_msg())] if conns else []

  def _room_update(self, room):
    return [([m.conn for m in room.members],
             {"type": wire.ROOM, **room.detail()})]

  def _create(self, conn, msg):
    if conn in self.room_of:
      raise LobbyError("already_in_room", "Ya estás en una sala.")
    if len(self.rooms) >= self.max_rooms:
      raise LobbyError("too_many_rooms",
                       "El servidor está lleno: probá más tarde.")
    user = self.users[conn]
    name = (msg.get("name") or f"Sala de {user.name}").strip()
    room = Room(next(self._ids), name[:ROOM_NAME_MAX], user.display,
                msg.get("password") or None)
    room.members.append(Member(conn, user))
    self.rooms[room.id] = room
    self.room_of[conn] = room.id
    return self._room_update(room) + self._broadcast_rooms()

  def _join(self, conn, msg):
    if conn in self.room_of:
      raise LobbyError("already_in_room", "Ya estás en una sala.")
    room = self.rooms.get(msg.get("room"))
    if room is None:
      raise LobbyError("no_such_room", "Esa sala ya no existe.")
    if len(room.members) >= MAX_PLAYERS:
      raise LobbyError("room_full", "La sala está completa.")
    if not room.check_password(msg.get("password")):
      raise LobbyError("wrong_password", "Contraseña incorrecta.")
    room.members.append(Member(conn, self.users[conn]))
    self.room_of[conn] = room.id
    room.state = CHOOSING
    return self._room_update(room) + self._broadcast_rooms()

  def _leave(self, conn, msg):
    del msg  # Unused.
    room = self.rooms.get(self.room_of.pop(conn, None))
    if room is None:
      raise LobbyError("not_in_room", "No estás en ninguna sala.")
    room.members = [m for m in room.members if m.conn != conn]
    out = [([conn], self._rooms_msg())]
    if not room.members:
      del self.rooms[room.id]            # an empty room disappears
    else:
      out += self._new_owner(room)
    return out + self._broadcast_rooms()

  def _new_owner(self, room):
    """Whoever stays becomes the owner; a match in play ends."""
    left = room.members[0]
    room.owner = left.user.display
    room.state = WAITING
    left.character, left.ready, left.side = None, False, None
    return self._room_update(room) + [([left.conn],
                                       {"type": wire.OPPONENT_LEFT})]

  # ------------------------------------------------------ choice and start
  def _in_room(self, conn):
    room = self.rooms.get(self.room_of.get(conn))
    if room is None:
      raise LobbyError("not_in_room", "No estás en ninguna sala.")
    return room, room.member(conn)

  def _choose(self, conn, msg):
    room, me = self._in_room(conn)
    if room.state != CHOOSING:
      raise LobbyError("cannot_choose", "Hay que esperar a que se "
                       "complete la sala.")
    character = msg.get("character")
    if character not in config.CHARACTER_IDS:
      raise LobbyError("invalid_character", "Ese personaje no existe.")
    me.character = character              # both may choose the same one
    me.ready = False
    return self._room_update(room)

  def _ready(self, conn, msg):
    room, me = self._in_room(conn)
    if room.state != CHOOSING:
      raise LobbyError("cannot_confirm", "La sala no está eligiendo "
                       "personajes.")
    if me.character is None:
      raise LobbyError("no_character", "Primero elegí un personaje.")
    me.ready = bool(msg.get("ready", True))
    out = self._room_update(room)
    if (len(room.members) == MAX_PLAYERS
            and all(m.ready and m.connected for m in room.members)):
      out += self._start(room)
    return out

  def _start(self, room):
    """Draws the sides at random and announces the start to both."""
    order = list(room.members)
    self.rng.shuffle(order)
    for side, member in enumerate(order):
      member.side = side
    room.state = PLAYING
    room.matches_played += 1
    match_id = next(self._match_ids)
    players = [_player_entry(m) for m in order]
    out = [([m.conn], {"type": wire.MATCH_START, "room": room.id,
                       "match": match_id, "players": players,
                       "you": m.side}) for m in order]
    return out + self._room_update(room) + self._broadcast_rooms()

  def finish_match(self, room_id):
    """Called by the room server when the match ends: they choose a
        character again (rematch) or leave."""
    room = self.rooms.get(room_id)
    if room is None or room.state != PLAYING:
      return []
    room.state = CHOOSING
    for member in room.members:
      member.ready = False
      member.side = None
    return self._room_update(room) + self._broadcast_rooms()


def _player_entry(member):
  """A player as announced in match_start."""
  return dict(member.user.public(), side=member.side,
              side_name=SIDE_NAMES[member.side],
              character=member.character)
