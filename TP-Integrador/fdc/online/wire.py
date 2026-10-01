"""Mensajes del modo online: qué viaja por el WebSocket y cómo se valida.

Por la red va SIEMPRE JSON (texto), nunca pickle: pickle permite ejecutar
código ajeno. El servidor desconfía de todo lo que llega: cada mensaje se
decodifica, se controla su forma y se descarta si no la cumple.

Lo usan el servidor (fdc/online/server.py) y el cliente (fdc/online/client.py),
también dentro del navegador (pygbag): no importa pygame ni librerías de red.

Cliente -> servidor
    hello {username, player_id, token?}
                                    presentarse con el nombre del perfil (o volver,
                                    con el token recibido); player_id da la etiqueta
    list_rooms / create_room / join_room / leave_room / choose_character / ready
                                    salas (ver fdc/online/lobby.py)
    input {p: [izq, der, saltos, patadas]}
                                    foto de controles REEMPLAZABLE con contadores
                                    acumulados (no se pierden pulsaciones)
    pause_request                   pedir pausa: se activa después del próximo gol
    pause_ready                     "listo" durante la pausa
    abandon                         abandonar el partido (pierde)
    ping {t}                        medir la latencia

Servidor -> cliente
    welcome {username, tag, display, token, restored}
    rooms {rooms}   room {...}   error {code, message}
    opponent_left                   el rival se fue de la sala
    match_start {room, match, players, you}
    state {...}                     foto del partido (reemplazable: "el último gana")
    ev {e}                          evento del partido (gol, poder, rebote...) con "eid"
    pause_info {status, by, left, ready}  pausa pedida / activa / terminada
    opponent {connected, left}      el rival perdió la conexión (o volvió)
    match_over {score, winner, reason, by}
    pong {t}
"""
import json

# --- cliente -> servidor
HELLO = "hello"
INPUT = "input"
PAUSE_REQUEST = "pause_request"
PAUSE_READY = "pause_ready"
ABANDON = "abandon"
PING = "ping"
LOBBY_TYPES = frozenset({"hello", "list_rooms", "create_room", "join_room", "leave_room",
                         "choose_character", "ready"})
CLIENT_TYPES = LOBBY_TYPES | {INPUT, PAUSE_REQUEST, PAUSE_READY, ABANDON, PING}

# --- servidor -> cliente
WELCOME = "welcome"
ROOMS = "rooms"
ROOM = "room"
ERROR = "error"
OPPONENT_LEFT = "opponent_left"
MATCH_START = "match_start"
STATE = "state"
EVENT = "ev"
PAUSE_INFO = "pause_info"
OPPONENT = "opponent"
MATCH_OVER = "match_over"
PONG = "pong"

# estados de la pausa online (pause_info.status)
PAUSE_PENDING = "pedida"      # alguien la pidió: se activa tras el próximo gol
PAUSE_ACTIVE = "activa"       # partido detenido: "listo" de los dos o 30 s
PAUSE_NONE = "ninguna"

# motivos de fin (match_over.reason)
END_TIME = "tiempo"
END_FORFEIT = "abandono"
END_ERROR = "error"

MAX_COUNTER = 10 ** 9


class WireError(ValueError):
    """Mensaje mal formado: se descarta (y se cuenta)."""


def encode(msg):
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False)


def decode(raw, allowed=None):
    """Texto JSON -> diccionario con "type". Lanza WireError si no sirve."""
    if not isinstance(raw, str):
        raise WireError("se esperaba texto")
    try:
        msg = json.loads(raw)
    except ValueError as exc:
        raise WireError(f"JSON inválido: {exc}") from None
    if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
        raise WireError("falta el tipo de mensaje")
    if allowed is not None and msg["type"] not in allowed:
        raise WireError(f"tipo desconocido: {msg['type']!r}")
    return msg


def clean_input(p):
    """Valida una foto de controles: [bool, bool, entero >= 0, entero >= 0]."""
    if not isinstance(p, (list, tuple)) or len(p) != 4:
        raise WireError("controles mal formados")
    left, right, jumps, kicks = p
    for c in (jumps, kicks):
        if isinstance(c, bool) or not isinstance(c, int) or not 0 <= c <= MAX_COUNTER:
            raise WireError("contador inválido")
    return [bool(left), bool(right), jumps, kicks]


def _round(obj):
    if isinstance(obj, float):
        return round(obj, 1)
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v) for v in obj]
    return obj


# datos internos del proceso de simulación que no le sirven al navegador
_STATE_SKIP = ("dropped_states", "dropped_cosmetic")


def compact_state(state):
    """Estado de la simulación listo para la red: sin datos internos y con
    decimales recortados (≈40 % menos de bytes por segundo)."""
    out = {k: v for k, v in state.items() if k not in _STATE_SKIP}
    out = _round(out)
    out["type"] = STATE
    # el ángulo de la pelota y el avance de la patada necesitan más precisión
    out["ball"]["angle"] = round(state["ball"]["angle"] % 360.0, 1)
    for p, src in zip(out["players"], state["players"]):
        p["kick"] = round(src["kick"], 3)
        p["scale"] = round(src["scale"], 3)
    return out
