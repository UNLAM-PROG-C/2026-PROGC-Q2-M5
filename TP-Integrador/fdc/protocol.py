"""Message protocol between the user interface (UI) and the simulation (SIM).

Every message is a small dictionary, serializable with pickle, with a "type"
key. There are four channels (queues) with different policies:

    UI -> SIM  cmd_q    COMMANDS   reliable: put with a timeout, never
                                   dropped; each one has a "cid" and gets an
                                   ACK.
    UI -> SIM  input_q  CONTROLS   replaceable: put_nowait; if the queue is
                                   full THAT snapshot is dropped. No press is
                                   lost because jumps and kicks travel as
                                   CUMULATIVE counters.
    SIM -> UI  state_q  STATES     replaceable: "the newest wins". They carry
                                   the match number ("match") and the update
                                   number ("seq").
    SIM -> UI  event_q  EVENTS     acknowledgements and match facts with a
                                   unique id ("eid"). Critical ones are always
                                   delivered; cosmetic ones (bounce sounds)
                                   may be dropped if the queue is full.

A multiprocessing.Event (stop_event) also asks for the shutdown.
"""

# --- Commands UI -> SIM ------------------------------------------------------
CMD_START = "start_match"
CMD_PAUSE = "pause"
CMD_RESUME = "resume"
CMD_RESTART = "restart"
CMD_END = "end_match"
CMD_SKIP_GOAL = "skip_goal"        # the party and the replay are over
CMD_SHUTDOWN = "shutdown"
CMD_DEBUG_POWER = "debug_power"    # test mode only
CMD_DEBUG_CRASH = "debug_crash"    # test mode only
COMMANDS = (CMD_START, CMD_PAUSE, CMD_RESUME, CMD_RESTART, CMD_END,
            CMD_SKIP_GOAL, CMD_SHUTDOWN, CMD_DEBUG_POWER, CMD_DEBUG_CRASH)

# --- Controls UI -> SIM ------------------------------------------------------
MSG_INPUT = "input"

# --- SIM -> UI ---------------------------------------------------------------
MSG_STATE = "state"
EV_READY = "ready"
EV_ACK = "ack"
EV_ERROR = "error"
EV_BYE = "bye"
EV_KICKOFF = "kickoff"
EV_GOAL = "goal"
# The replay of the goal starts now (decided by the simulation): the match
# stays frozen `seconds` more, alike for every client, and then resumes.
EV_REPLAY = "replay"
EV_MATCH_END = "match_end"
EV_GOLDEN_GOAL = "golden_goal"   # draw at the end: the next goal wins
EV_PAUSED = "paused"             # pause decided by the simulation (watchdog)
EV_POWER_SPAWN = "power_spawn"
EV_POWER = "power"               # a power was activated
EV_POWER_EXPIRED = "power_expired"
# The fire power burned a player: the ball went out on that touch.
EV_BURN = "burn"
EV_PICKUP_EXPIRED = "pickup_expired"
EV_BOMB_ARMED = "bomb_armed"
EV_BOMB_EXPLODE = "bomb_explode"
EV_KICK = "kick"                 # cosmetic
EV_KICK_BLOCKED = "kick_blocked"  # cosmetic
EV_TOUCH = "touch"               # cosmetic (bounces, headers)

# Cosmetic events: if the queue is full they are dropped (and counted).
COSMETIC_EVENTS = frozenset({EV_KICK, EV_KICK_BLOCKED, EV_TOUCH})

# Match phases (decided by the simulation).
PHASE_COUNTDOWN = "countdown"
PHASE_PLAYING = "playing"
PHASE_GOAL = "goal"
PHASE_FINISHED = "finished"

PAUSE_REASON_USER = "user"
PAUSE_REASON_FOCUS = "focus"
PAUSE_REASON_WATCHDOG = "no_input"
# Online: asked by a player, it starts after the next goal.
PAUSE_REASON_REQUEST = "requested"
# Online: a player lost the connection.
PAUSE_REASON_DISCONNECT = "disconnect"


# ---------------------------------------------------------------------------
# Builders (UI)
# ---------------------------------------------------------------------------
def make_command(ctype, cid, **payload):
    """Returns a command message; raises ValueError for unknown types."""
    if ctype not in COMMANDS:
        raise ValueError(f"unknown command: {ctype}")
    msg = {"type": ctype, "cid": cid}
    msg.update(payload)
    return msg


def make_input(iseq, players, seqs=None):
    """players: [[left, right, jump_counter, kick_counter], [...]].

    `seqs` are the client sequence numbers of those snapshots (online mode,
    so the state can tell the client which input it applied)."""
    msg = {"type": MSG_INPUT, "iseq": iseq, "p": [list(p) for p in players]}
    if seqs is not None:
        msg["seqs"] = list(seqs)
    return msg


# ---------------------------------------------------------------------------
# Builders (SIM)
# ---------------------------------------------------------------------------
def make_ack(cid, cmd, ok=True, match=None, detail=""):
    """Acknowledgement of the command with id `cid`."""
    return {"type": EV_ACK, "cid": cid, "cmd": cmd, "ok": ok,
            "match": match, "detail": detail}


def make_event(etype, eid, match=None, **payload):
    """Event message with a unique, increasing id."""
    msg = {"type": etype, "eid": eid, "match": match}
    msg.update(payload)
    return msg


def is_cosmetic(msg):
    """True for events that may be dropped when the queue is full."""
    return msg.get("type") in COSMETIC_EVENTS


# ---------------------------------------------------------------------------
# Pure receiving logic (used by the UI and tested without processes)
# ---------------------------------------------------------------------------
class PressCounter:
    """Turns cumulative press counters into new presses.

    The UI increments a counter on each jump or kick KEYDOWN. Even if the SIM
    only reads the latest controls snapshot (compaction), the difference
    between counters tells how many presses happened since the previous one.
    """

    def __init__(self):
        self.last = None

    def update(self, count):
        """Returns how many presses happened since the previous snapshot."""
        if self.last is None or count < self.last:
            # First snapshot (or the UI restarted its counters): new baseline.
            self.last = count
            return 0
        new = count - self.last
        self.last = count
        return new


class StateFilter:
    """Accepts only states of the current match, newer than the last one."""

    def __init__(self):
        self.match = None
        self.last_seq = -1
        self.accepted = 0
        self.rejected_old_match = 0
        self.rejected_stale = 0

    def expect(self, match_id):
        """From now on only this match is valid (start, rematch or restart)."""
        self.match = match_id
        self.last_seq = -1

    def accept(self, state):
        """True if `state` belongs to the expected match and is newer."""
        if self.match is None or state.get("match") != self.match:
            self.rejected_old_match += 1
            return False
        seq = state.get("seq", -1)
        if seq <= self.last_seq:
            self.rejected_stale += 1
            return False
        self.last_seq = seq
        self.accepted += 1
        return True


class EventDeduper:
    """Guarantees that each event is handled only once.

    The eids grow inside one simulation process (a single producer and a FIFO
    queue), so remembering the last one is enough.
    """

    def __init__(self):
        self.last_eid = -1
        self.duplicates = 0

    def reset(self):
        self.last_eid = -1

    def fresh(self, msg):
        """True the first time an event is seen; False for repeats."""
        eid = msg.get("eid")
        if eid is None:
            return True
        if eid <= self.last_eid:
            self.duplicates += 1
            return False
        self.last_eid = eid
        return True
