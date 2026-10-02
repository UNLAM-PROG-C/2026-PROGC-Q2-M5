"""Salas del modo online (1 contra 1). Lógica pura, SIN red.

Este módulo implementa las reglas acordadas para el online:
  * cada persona entra con el nombre que eligió al abrir el juego (sin
    cuentas). Los nombres se pueden repetir: a cada persona conectada se le da
    una etiqueta de 4 dígitos ("Ale #4821") que la distingue de otra con el
    mismo nombre. La etiqueta sale del id del perfil, así que es la misma cada
    vez que esa persona entra (salvo que choque con otra conectada);
  * se puede crear una sala libre o con contraseña;
  * todos ven la lista de salas con el nombre de quien la creó y pueden unirse;
  * con 2 personas en la sala, cada una elige personaje y confirma;
  * el sistema asigna automáticamente los lados (izquierda / derecha) y
    arranca el partido.

No abre sockets ni conoce el transporte: recibe mensajes (diccionarios que se
pueden mandar como JSON) de una sesión identificada y devuelve la lista de
mensajes a enviar, con sus destinatarios. El servidor (fdc/online/server.py)
sólo enruta lo que entra y lo que sale.
"""
import hashlib
import hmac
import itertools
import os
import random

from ..config import CHARACTER_IDS, Online
from ..profile import MAX_PLAYER_ID, NAME_RE as USERNAME_RE, NAME_RULE

MAX_PLAYERS = 2             # una sala es siempre 1 contra 1
TAGS = 10000                # etiquetas #0000 a #9999
SALT_BYTES = 16             # bytes de sal aleatoria por contraseña de sala
TAG_HASH_DIGITS = 8         # dígitos hexadecimales del hash del perfil que se usan para la etiqueta
HEX = 16                    # base de los dígitos hexadecimales
ROOM_NAME_MAX = 24          # caracteres máximos del nombre de una sala
# contraseña de una sala (no de una cuenta): alcanza con esto y el hash tarda
# unos pocos ms, así no frena el bucle del servidor que atiende a todos
PBKDF2_ROUNDS = 20_000

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


class User:
    def __init__(self, name, tag):
        self.name = name
        self.tag = tag

    @property
    def display(self):
        return f"{self.name} #{self.tag:04d}"

    def public(self):
        return {"username": self.name, "tag": self.tag, "display": self.display}


class Member:
    def __init__(self, conn, user):
        self.conn = conn
        self.user = user
        self.character = None
        self.ready = False
        self.side = None
        self.connected = True       # False mientras se espera que vuelva a conectarse

    @property
    def username(self):
        return self.user.name

    def public(self):
        return dict(self.user.public(), character=self.character, ready=self.ready, side=self.side,
                    connected=self.connected)


class Room:
    def __init__(self, room_id, name, owner, password=None):
        self.id = room_id
        self.name = name
        self.owner = owner                  # quien la creó, con su etiqueta ("Ale #4821")
        self.salt = os.urandom(SALT_BYTES) if password else None
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

    def __init__(self, rng=None, max_rooms=Online.MAX_ROOMS):
        self.rng = rng or random.Random()
        self.max_rooms = max_rooms
        self.users = {}                    # conn -> User (nombre + etiqueta)
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
        """La conexión se cortó del todo: sale de su sala y se libera su etiqueta."""
        out = self._leave(conn, {}) if conn in self.room_of else []
        self.users.pop(conn, None)
        return out

    def set_connected(self, conn, connected):
        """La conexión se cortó (o volvió) pero la sesión sigue reservada:
        el rival lo ve en la sala y no se puede arrancar sin él."""
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
        """Mensajes para que una sesión que se reconectó vea dónde estaba."""
        room = self.room_of_conn(conn)
        if room is None:
            return [([conn], self._rooms_msg())]
        return [([conn], {"type": "room", **room.detail()})]

    # ------------------------------------------------------------------ usuarios y salas
    def _hello(self, conn, msg):
        name = (msg.get("username") or "").strip()
        if not USERNAME_RE.match(name):
            raise LobbyError("nombre_invalido", f"El nombre debe tener {NAME_RULE}.")
        user = User(name, self._tag_for(conn, name, msg.get("player_id")))
        self.users[conn] = user
        return [([conn], {"type": "welcome", **user.public()}), ([conn], self._rooms_msg())]

    def _tag_for(self, conn, name, player_id):
        """Etiqueta estable para ese perfil y distinta de la de otro conectado con el mismo nombre."""
        if isinstance(player_id, str) and 0 < len(player_id) <= MAX_PLAYER_ID:
            digest = hashlib.sha256(player_id.encode("utf-8")).hexdigest()
            tag = int(digest[:TAG_HASH_DIGITS], HEX) % TAGS
        else:
            tag = self.rng.randrange(TAGS)
        taken = {u.tag for c, u in self.users.items() if c != conn and u.name.lower() == name.lower()}
        while tag in taken:
            tag = (tag + 1) % TAGS
        return tag

    def user(self, conn):
        return self.users.get(conn)

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
        if len(self.rooms) >= self.max_rooms:
            raise LobbyError("demasiadas_salas", "El servidor está lleno: probá más tarde.")
        user = self.users[conn]
        name = (msg.get("name") or f"Sala de {user.name}").strip()[:ROOM_NAME_MAX]
        password = msg.get("password") or None
        room = Room(next(self._ids), name, user.display, password)
        room.members.append(Member(conn, user))
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
            room.owner = left.user.display
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
        if (len(room.members) == MAX_PLAYERS and all(m.ready for m in room.members)
                and all(m.connected for m in room.members)):
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
        players = [dict(m.user.public(), side=m.side, side_name=SIDE_NAMES[m.side], character=m.character)
                   for m in order]
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
