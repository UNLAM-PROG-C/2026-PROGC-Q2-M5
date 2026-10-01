"""Salas para el futuro modo online (1 contra 1). Lógica pura, SIN red.

Este módulo implementa las reglas acordadas para el online:
  * al entrar, cada persona elige un nombre de usuario (sin cuentas);
  * se puede crear una sala libre o con contraseña;
  * todos ven la lista de salas con el nombre de quien la creó y pueden unirse;
  * con 2 personas en la sala, cada una elige personaje y confirma;
  * el sistema asigna automáticamente los lados (izquierda / derecha) y
    arranca el partido.

No abre sockets ni conoce el transporte: recibe mensajes (diccionarios que se
pueden mandar como JSON) de una conexión identificada y devuelve la lista de
mensajes a enviar, con sus destinatarios. Un servidor WebSocket futuro sólo
tiene que enrutar lo que entra y lo que sale (ver docs/ONLINE.md).
"""
import hashlib
import hmac
import itertools
import os
import random
import re

from ..config import CHARACTER_IDS

MAX_PLAYERS = 2
USERNAME_RE = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ _.-]{3,16}$")
ROOM_NAME_MAX = 24
PBKDF2_ROUNDS = 100_000

# estados de una sala
WAITING = "esperando"      # hay 1 persona
CHOOSING = "eligiendo"     # hay 2 personas eligiendo personaje
PLAYING = "jugando"

SIDE_NAMES = ("izquierda", "derecha")


class LobbyError(Exception):
    """Error de uso con un código estable (para el cliente) y un texto en español."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)


class Member:
    def __init__(self, conn, username):
        self.conn = conn
        self.username = username
        self.character = None
        self.ready = False
        self.side = None

    def public(self):
        return {"username": self.username, "character": self.character, "ready": self.ready,
                "side": self.side}


class Room:
    def __init__(self, room_id, name, owner, password=None):
        self.id = room_id
        self.name = name
        self.owner = owner                  # nombre de usuario de quien la creó
        self.salt = os.urandom(16) if password else None
        self.password_hash = _hash_password(password, self.salt) if password else None
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
        return hmac.compare_digest(self.password_hash, _hash_password(password, self.salt))

    def member(self, conn):
        return next((m for m in self.members if m.conn == conn), None)

    def summary(self):
        """Lo que ve cualquiera en la lista de salas (nunca la contraseña)."""
        return {"room": self.id, "name": self.name, "owner": self.owner, "private": self.private,
                "players": len(self.members), "max_players": MAX_PLAYERS, "state": self.state}

    def detail(self):
        d = self.summary()
        d["members"] = [m.public() for m in self.members]
        return d


class Lobby:
    """Estado de usuarios y salas. Un único hilo/tarea debe llamar a handle()."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.users = {}                    # conn -> nombre de usuario
        self.rooms = {}                    # id -> Room
        self.room_of = {}                  # conn -> id de sala
        self._ids = itertools.count(1)
        self._match_ids = itertools.count(1)

    # ------------------------------------------------------------------ entrada única
    def handle(self, conn, msg):
        """Procesa un mensaje de una conexión. Devuelve [(destinatarios, mensaje)]."""
        handler = {
            "hello": self._hello, "list_rooms": self._list, "create_room": self._create,
            "join_room": self._join, "leave_room": self._leave, "choose_character": self._choose,
            "ready": self._ready,
        }.get(msg.get("type"))
        try:
            if handler is None:
                raise LobbyError("desconocido", f"Mensaje desconocido: {msg.get('type')!r}")
            if msg.get("type") != "hello" and conn not in self.users:
                raise LobbyError("sin_nombre", "Primero hay que elegir un nombre de usuario.")
            return handler(conn, msg)
        except LobbyError as err:
            return [([conn], {"type": "error", "code": err.code, "message": err.message})]

    def disconnect(self, conn):
        """La conexión se cortó: sale de su sala y se libera el nombre."""
        out = self._leave(conn, {}) if conn in self.room_of else []
        self.users.pop(conn, None)
        return out

    # ------------------------------------------------------------------ usuarios y salas
    def _hello(self, conn, msg):
        name = (msg.get("username") or "").strip()
        if not USERNAME_RE.match(name):
            raise LobbyError("nombre_invalido", "El nombre debe tener entre 3 y 16 letras, números o espacios.")
        if any(n.lower() == name.lower() for c, n in self.users.items() if c != conn):
            raise LobbyError("nombre_en_uso", f"El nombre «{name}» ya está en uso.")
        self.users[conn] = name
        return [([conn], {"type": "welcome", "username": name}), ([conn], self._rooms_msg())]

    def _rooms_msg(self):
        rooms = sorted(self.rooms.values(), key=lambda r: r.id)
        return {"type": "rooms", "rooms": [r.summary() for r in rooms]}

    def _list(self, conn, msg):
        return [([conn], self._rooms_msg())]

    def _lobby_conns(self):
        """Conexiones que están mirando la lista (no están en una sala)."""
        return [c for c in self.users if c not in self.room_of]

    def _broadcast_rooms(self):
        conns = self._lobby_conns()
        return [(conns, self._rooms_msg())] if conns else []

    def _room_update(self, room):
        return [([m.conn for m in room.members], {"type": "room", **room.detail()})]

    def _create(self, conn, msg):
        if conn in self.room_of:
            raise LobbyError("ya_en_sala", "Ya estás en una sala.")
        owner = self.users[conn]
        name = (msg.get("name") or f"Sala de {owner}").strip()[:ROOM_NAME_MAX]
        password = msg.get("password") or None
        room = Room(next(self._ids), name, owner, password)
        room.members.append(Member(conn, owner))
        self.rooms[room.id] = room
        self.room_of[conn] = room.id
        return self._room_update(room) + self._broadcast_rooms()

    def _join(self, conn, msg):
        if conn in self.room_of:
            raise LobbyError("ya_en_sala", "Ya estás en una sala.")
        room = self.rooms.get(msg.get("room"))
        if room is None:
            raise LobbyError("sala_inexistente", "Esa sala ya no existe.")
        if len(room.members) >= MAX_PLAYERS:
            raise LobbyError("sala_llena", "La sala está completa.")
        if not room.check_password(msg.get("password")):
            raise LobbyError("clave_incorrecta", "Contraseña incorrecta.")
        room.members.append(Member(conn, self.users[conn]))
        self.room_of[conn] = room.id
        room.state = CHOOSING
        return self._room_update(room) + self._broadcast_rooms()

    def _leave(self, conn, msg):
        room_id = self.room_of.pop(conn, None)
        room = self.rooms.get(room_id)
        if room is None:
            raise LobbyError("sin_sala", "No estás en ninguna sala.")
        room.members = [m for m in room.members if m.conn != conn]
        out = [([conn], self._rooms_msg())]
        if not room.members:
            del self.rooms[room.id]            # la sala vacía desaparece
        else:
            # quien queda pasa a ser el dueño; si había partido, termina
            left = room.members[0]
            room.owner = left.username
            room.state = WAITING
            left.character, left.ready, left.side = None, False, None
            out += self._room_update(room)
            out.append(([left.conn], {"type": "opponent_left"}))
        return out + self._broadcast_rooms()

    # ------------------------------------------------------------------ elección y arranque
    def _in_room(self, conn):
        room = self.rooms.get(self.room_of.get(conn))
        if room is None:
            raise LobbyError("sin_sala", "No estás en ninguna sala.")
        return room, room.member(conn)

    def _choose(self, conn, msg):
        room, me = self._in_room(conn)
        if room.state != CHOOSING:
            raise LobbyError("no_se_puede_elegir", "Hay que esperar a que se complete la sala.")
        character = msg.get("character")
        if character not in CHARACTER_IDS:
            raise LobbyError("personaje_invalido", "Ese personaje no existe.")
        me.character = character              # los dos pueden elegir el mismo
        me.ready = False
        return self._room_update(room)

    def _ready(self, conn, msg):
        room, me = self._in_room(conn)
        if room.state != CHOOSING:
            raise LobbyError("no_se_puede_confirmar", "La sala no está eligiendo personajes.")
        if me.character is None:
            raise LobbyError("sin_personaje", "Primero elegí un personaje.")
        me.ready = bool(msg.get("ready", True))
        out = self._room_update(room)
        if len(room.members) == MAX_PLAYERS and all(m.ready for m in room.members):
            out += self._start(room)
        return out

    def _start(self, room):
        """Asigna los lados al azar y avisa el comienzo a ambos."""
        order = list(room.members)
        self.rng.shuffle(order)
        for side, m in enumerate(order):
            m.side = side
        room.state = PLAYING
        room.matches_played += 1
        match_id = next(self._match_ids)
        players = [{"side": m.side, "side_name": SIDE_NAMES[m.side], "username": m.username,
                    "character": m.character} for m in order]
        out = []
        for m in order:
            out.append(([m.conn], {"type": "match_start", "room": room.id, "match": match_id,
                                   "players": players, "you": m.side}))
        return out + self._room_update(room) + self._broadcast_rooms()

    def finish_match(self, room_id):
        """Lo llama el servidor de la sala al terminar el partido: vuelven a
        elegir personaje (revancha) o a salir."""
        room = self.rooms.get(room_id)
        if room is None or room.state != PLAYING:
            return []
        room.state = CHOOSING
        for m in room.members:
            m.ready = False
            m.side = None
        return self._room_update(room) + self._broadcast_rooms()
