"""Protocolo de mensajes entre la interfaz (UI) y la simulación (SIM).

Todos los mensajes son diccionarios pequeños y serializables con pickle, con
una clave "type". Hay cuatro canales (colas) con políticas distintas:

    UI -> SIM  cmd_q    ÓRDENES      confiables: put con tiempo límite, nunca se
                                     descartan; cada una lleva "cid" y recibe ACK.
    UI -> SIM  input_q  CONTROLES    reemplazables: put_nowait; si la cola está
                                     llena se descarta ESA foto. No se pierde
                                     ninguna pulsación porque saltos y patadas
                                     viajan como CONTADORES acumulados.
    SIM -> UI  state_q  ESTADOS      reemplazables: "el último gana". Llevan
                                     número de partido ("match") y de
                                     actualización ("seq").
    SIM -> UI  event_q  EVENTOS      confirmaciones y hechos del partido con id
                                     único ("eid"). Los críticos se entregan
                                     siempre; los cosméticos (sonido de rebote)
                                     pueden descartarse si la cola se llena.

Además un multiprocessing.Event (stop_event) solicita el cierre.
"""

# --- Órdenes UI -> SIM -------------------------------------------------------
CMD_START = "start_match"
CMD_PAUSE = "pause"
CMD_RESUME = "resume"
CMD_RESTART = "restart"
CMD_END = "end_match"
CMD_SHUTDOWN = "shutdown"
CMD_DEBUG_POWER = "debug_power"    # sólo modo de prueba
CMD_DEBUG_CRASH = "debug_crash"    # sólo modo de prueba
COMMANDS = (CMD_START, CMD_PAUSE, CMD_RESUME, CMD_RESTART, CMD_END,
            CMD_SHUTDOWN, CMD_DEBUG_POWER, CMD_DEBUG_CRASH)

# --- Controles UI -> SIM -----------------------------------------------------
MSG_INPUT = "input"

# --- SIM -> UI ---------------------------------------------------------------
MSG_STATE = "state"
EV_READY = "ready"
EV_ACK = "ack"
EV_ERROR = "error"
EV_BYE = "bye"
EV_KICKOFF = "kickoff"
EV_GOAL = "goal"
EV_MATCH_END = "match_end"
EV_GOLDEN_GOAL = "golden_goal"    # empate al terminar: el próximo gol gana
EV_PAUSED = "paused"             # pausa decidida por la simulación (watchdog)
EV_POWER_SPAWN = "power_spawn"
EV_POWER = "power"               # activación de un poder
EV_POWER_EXPIRED = "power_expired"
EV_PICKUP_EXPIRED = "pickup_expired"
EV_BOMB_ARMED = "bomb_armed"
EV_BOMB_EXPLODE = "bomb_explode"
EV_KICK = "kick"                 # cosmético
EV_KICK_BLOCKED = "kick_blocked"  # cosmético
EV_TOUCH = "touch"               # cosmético (rebotes, cabezazos)

# Eventos cosméticos: si la cola está llena se descartan (y se cuentan).
COSMETIC_EVENTS = frozenset({EV_KICK, EV_KICK_BLOCKED, EV_TOUCH})

# Fases del partido (las decide la simulación)
PHASE_COUNTDOWN = "countdown"
PHASE_PLAYING = "playing"
PHASE_GOAL = "goal"
PHASE_FINISHED = "finished"

PAUSE_REASON_USER = "usuario"
PAUSE_REASON_FOCUS = "foco"
PAUSE_REASON_WATCHDOG = "sin_controles"
PAUSE_REASON_REQUEST = "pedida"          # online: pedida por un jugador, se activa tras un gol
PAUSE_REASON_DISCONNECT = "desconexion"  # online: un jugador perdió la conexión


# ---------------------------------------------------------------------------
# Constructores (UI)
# ---------------------------------------------------------------------------
def make_command(ctype, cid, **payload):
    if ctype not in COMMANDS:
        raise ValueError(f"orden desconocida: {ctype}")
    msg = {"type": ctype, "cid": cid}
    msg.update(payload)
    return msg


def make_input(iseq, players):
    """players: [[izq, der, contador_saltos, contador_patadas], [...]]"""
    return {"type": MSG_INPUT, "iseq": iseq,
            "p": [list(p) for p in players]}


# ---------------------------------------------------------------------------
# Constructores (SIM)
# ---------------------------------------------------------------------------
def make_ack(cid, cmd, ok=True, match=None, detail=""):
    return {"type": EV_ACK, "cid": cid, "cmd": cmd, "ok": ok,
            "match": match, "detail": detail}


def make_event(etype, eid, match=None, **payload):
    msg = {"type": etype, "eid": eid, "match": match}
    msg.update(payload)
    return msg


def is_cosmetic(msg):
    return msg.get("type") in COSMETIC_EVENTS


# ---------------------------------------------------------------------------
# Lógica pura de recepción (se usa en la UI y se prueba sin procesos)
# ---------------------------------------------------------------------------
class PressCounter:
    """Convierte contadores acumulados de pulsaciones en pulsaciones nuevas.

    La UI incrementa un contador por cada KEYDOWN de salto o patada. Aunque la
    SIM sólo lea la última foto de controles (compactación), la diferencia de
    contadores le dice cuántas pulsaciones ocurrieron desde la anterior.
    """

    def __init__(self):
        self.last = None

    def update(self, count):
        if self.last is None or count < self.last:
            # primera foto (o la UI reinició sus contadores): tomar como base
            self.last = count
            return 0
        new = count - self.last
        self.last = count
        return new


class StateFilter:
    """Acepta sólo estados del partido actual y más nuevos que el último."""

    def __init__(self):
        self.match = None
        self.last_seq = -1
        self.accepted = 0
        self.rejected_old_match = 0
        self.rejected_stale = 0

    def expect(self, match_id):
        """A partir de ahora sólo vale este partido (inicio, revancha o reinicio)."""
        self.match = match_id
        self.last_seq = -1

    def accept(self, state):
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
    """Garantiza que cada evento se procese una sola vez.

    Los eid son crecientes dentro de un proceso de simulación (un único
    productor y cola FIFO), así que alcanza con recordar el último.
    """

    def __init__(self):
        self.last_eid = -1
        self.duplicates = 0

    def reset(self):
        self.last_eid = -1

    def fresh(self, msg):
        eid = msg.get("eid")
        if eid is None:
            return True
        if eid <= self.last_eid:
            self.duplicates += 1
            return False
        self.last_eid = eid
        return True
