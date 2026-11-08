"""Online mode messages: what travels on the WebSocket and how it is checked.

The network ALWAYS carries JSON (text), never pickle: pickle can run foreign
code. The server distrusts everything that arrives: each message is decoded,
its shape is checked and it is dropped if it does not match.

Used by the server (fdc/online/server.py) and the client
(fdc/online/client.py), also inside the browser (pygbag): it imports neither
pygame nor network libraries.

Client -> server
    hello {username, player_id, protocol?, token?}
                                introduce itself with the profile name (or
                                come back with the received token);
                                player_id gives the tag; protocol is the
                                version of its protocol (the server refuses
                                another one with an "error" of code
                                "version" and closes the connection)
    list_rooms / create_room / join_room / leave_room / choose_character /
    ready                       rooms (see fdc/online/lobby.py)
    input {p: [left, right, jumps, kicks], seq}
                                REPLACEABLE controls snapshot with cumulative
                                counters (no press is lost); `seq` (online,
                                optional) numbers the snapshot so the client
                                can reconcile its prediction with "ack"
    pause_request               ask for a pause: it starts after the next goal
    pause_ready                 "ready" during the pause
    abandon                     leave the match (loses)
    ping {t}                    measure the latency

Server -> client
    welcome {username, tag, display, token, restored}
    rooms {rooms}   room {...}   error {code, message}
    opponent_left               the rival left the room
    match_start {room, match, players, you}
    state {...}                 match snapshot (replaceable: "the newest wins")
                                with "ack": last controls sequence number the
                                simulation applied for each player
    ev {e}                      match event (goal, power, bounce...) with "eid"
    pause_info {status, by, left, ready}  pause requested / active / over
    opponent {connected, left}  the rival lost the connection (or came back)
    match_over {score, winner, reason, by}
    room_info {...}             once per second during the match: data of the
                                room on the server (pid of its process, states
                                per second, ACK times...) for the F3 panel
    pong {t}
"""
import json

# --- client -> server
HELLO = "hello"
INPUT = "input"
PAUSE_REQUEST = "pause_request"
PAUSE_READY = "pause_ready"
ABANDON = "abandon"
PING = "ping"
LIST_ROOMS = "list_rooms"
CREATE_ROOM = "create_room"
JOIN_ROOM = "join_room"
LEAVE_ROOM = "leave_room"
CHOOSE_CHARACTER = "choose_character"
READY = "ready"
LOBBY_TYPES = frozenset({HELLO, LIST_ROOMS, CREATE_ROOM, JOIN_ROOM, LEAVE_ROOM,
                         CHOOSE_CHARACTER, READY})
CLIENT_TYPES = LOBBY_TYPES | {INPUT, PAUSE_REQUEST, PAUSE_READY, ABANDON, PING}

# --- server -> client
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
ROOM_INFO = "room_info"
PONG = "pong"

# WebSocket close codes (RFC 6455; 4000 to 4999 are our own).
CLOSE_POLICY = 1008     # broke the rules: too many messages or not reading
CLOSE_TRY_AGAIN = 1013  # server full: better try later
CLOSE_REPLACED = 4000   # its session was opened in another window

# Codes of the "error" message the server sends to the client.
CODE_VERSION = "version"    # the game version does not match the server's

# States of the online pause (pause_info.status).
PAUSE_PENDING = "pending"   # someone asked: it starts after the next goal
PAUSE_ACTIVE = "active"     # match stopped: "ready" from both or 30 s
PAUSE_NONE = "none"

# Reasons of the end (match_over.reason).
END_TIME = "time"
END_FORFEIT = "forfeit"
END_ERROR = "error"

# Cap of the jump and kick counters (more means a forged message).
MAX_COUNTER = 10 ** 9
INPUT_FIELDS = 4        # controls snapshot: left, right, jumps, kicks
POSITION_DECIMALS = 1   # tenths of a pixel are enough to draw
FINE_DECIMALS = 3       # the kick progress and the scale need more precision
FULL_TURN = 360.0       # degrees: the ball angle is sent between 0 and 360
# Internal data of the simulation process that the browser does not need.
_STATE_SKIP = ("dropped_states", "dropped_cosmetic")


class WireError(ValueError):
    """Malformed message: it is dropped (and counted)."""


def encode(msg):
    """Compact JSON text of a message."""
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False)


def decode(raw, allowed=None):
    """JSON text -> dictionary with "type". Raises WireError if unusable."""
    if not isinstance(raw, str):
        raise WireError("text expected")
    try:
        msg = json.loads(raw)
    except ValueError as exc:
        raise WireError(f"invalid JSON: {exc}") from None
    if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
        raise WireError("missing message type")
    if allowed is not None and msg["type"] not in allowed:
        raise WireError(f"unknown type: {msg['type']!r}")
    return msg


def clean_input(p):
    """Checks a controls snapshot: [bool, bool, int >= 0, int >= 0]."""
    if not isinstance(p, (list, tuple)) or len(p) != INPUT_FIELDS:
        raise WireError("malformed controls")
    left, right, jumps, kicks = p
    for counter in (jumps, kicks):
        if (isinstance(counter, bool) or not isinstance(counter, int)
                or not 0 <= counter <= MAX_COUNTER):
            raise WireError("invalid counter")
    return [bool(left), bool(right), jumps, kicks]


def clean_seq(seq):
    """Client sequence number of a controls snapshot (0 if it came without
    one: an older client)."""
    if seq is None:
        return 0
    valid = (not isinstance(seq, bool) and isinstance(seq, int)
             and 0 <= seq <= MAX_COUNTER)
    if not valid:
        raise WireError("invalid sequence number")
    return seq


def clean_controls(msg):
    """(controls snapshot, sequence number) of an input message."""
    return clean_input(msg.get("p")), clean_seq(msg.get("seq"))


def _round(obj):
    if isinstance(obj, float):
        return round(obj, POSITION_DECIMALS)
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v) for v in obj]
    return obj


def compact_state(state):
    """Simulation state ready for the network: without internal data and
    with fewer decimals (≈40 % fewer bytes per second)."""
    out = {k: v for k, v in state.items() if k not in _STATE_SKIP}
    out = _round(out)
    out["type"] = STATE
    # The ball angle and the kick progress need more precision.
    out["ball"]["angle"] = round(state["ball"]["angle"] % FULL_TURN,
                                 POSITION_DECIMALS)
    for player, source in zip(out["players"], state["players"]):
        player["kick"] = round(source["kick"], FINE_DECIMALS)
        player["scale"] = round(source["scale"], FINE_DECIMALS)
        player["speed"] = round(source["speed"], FINE_DECIMALS)
        player["jump"] = round(source["jump"], FINE_DECIMALS)
    return out
