"""Central configuration of the game.

This module does NOT import pygame: both the user interface and the
simulation process use it. Every "number to tune" lives here, so the name,
keys, physics or powers can change without touching the logic.

Units: pixels of the logical resolution (1280 x 720) and seconds.
"""
import collections
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
GAME_NAME = "Futbol De Cabeza"
GAME_TAGLINE = "Duelo de cabezones - solo, de a dos u online"
# Version of the UI <-> simulation protocol (reported in READY).
PROTOCOL_VERSION = 1

# ---------------------------------------------------------------------------
# Screen (logical reference resolution; the window scales with SCALED,
# keeping the aspect ratio and adding bars when needed)
# ---------------------------------------------------------------------------
LOGICAL_WIDTH = 1280        # px: logical screen width (everything uses it)
LOGICAL_HEIGHT = 720        # px: logical screen height
UI_FPS = 60                 # frames per second drawn by the interface
MS_PER_SECOND = 1000        # to show times in milliseconds (latency, ACK)

# ---------------------------------------------------------------------------
# Controls, stored as pygame key names (pygame.key.key_code) so this module
# does not depend on pygame. Index 0 = P1, 1 = P2.
# ---------------------------------------------------------------------------
PLAYER_KEYS = (
    {"left": "a", "right": "d", "jump": "w", "kick": "space"},
    {"left": "left", "right": "right", "jump": "up", "kick": "p"},
)
PAUSE_KEY = "escape"
DEBUG_PANEL_KEY = "f3"
FULLSCREEN_KEY = "f11"
MUTE_KEY = "m"
GPU_TOGGLE_KEY = "f4"       # F4: effects GPU <-> numpy, without restarting
OVERLAY_KEY = "f2"          # F2: performance overlay off -> compact -> full
NIGHT_KEY = "n"             # F8 is "give power to P1" in --test mode
# Test mode keys (only active with --test).
TEST_PREV_POWER_KEY = "f5"
TEST_NEXT_POWER_KEY = "f6"
TEST_SPAWN_POWER_KEY = "f7"
TEST_GIVE_P1_KEY = "f8"
TEST_GIVE_P2_KEY = "f9"
TEST_CRASH_SIM_KEY = "f12"

PLAYER_LABELS = ("J1", "J2")
# Available characters (their look is in fdc/ui/characters.py; the
# simulation does NOT use this list to compute anything: all play the same).
CHARACTER_IDS = ("messi", "maradona", "pele", "cr7", "henry", "neymar",
                 "mbappe")
# Identification colour of each player (outline and marker), chosen so they
# are not confused with any shirt or with the power categories.
PLAYER_COLORS = ((255, 138, 30), (255, 64, 160))


# ---------------------------------------------------------------------------
# Pitch
# ---------------------------------------------------------------------------
class Arena:
    """Size of the pitch and of the goals."""
    WIDTH = 1280           # px: pitch width (the whole screen)
    HEIGHT = 720           # px: pitch height
    FLOOR_Y = 646          # px: line where boots stand and the ball bounces
    CEILING_Y = 0          # px: invisible ceiling, the ball never leaves
    # px: deep goal, so the ball can cross the line even with a player inside
    GOAL_DEPTH = 112
    # px: a player jumping from the floor does not reach the crossbar
    GOAL_HEIGHT = 250
    BAR_THICKNESS = 10     # px: crossbar thickness (capsule, round tip)
    GOAL_MIN_HEIGHT = 150  # px: lowest goal allowed by the goal powers
    GOAL_MAX_HEIGHT = 340  # px: highest goal (with the big goal power)


# ---------------------------------------------------------------------------
# Physics. Fixed step: the simulation always advances PHYSICS_DT, no matter
# how many frames per second the interface draws.
# ---------------------------------------------------------------------------
PHYSICS_HZ = 120            # physics steps per second
PHYSICS_DT = 1.0 / PHYSICS_HZ   # s: length of each fixed step
STATE_EVERY_TICKS = 2       # a state is published every 2 steps (60 per s)
MAX_CATCHUP_STEPS = 6       # a late simulation does not "catch up" more


class PlayerSpec:
    """Base abilities: identical for the seven characters.

    A player is a big head with a boot below ("cabezones" style): a head
    circle and a small boot circle hit the ball and the other player, and a
    box collides with the floor, the walls and the crossbars. The balance was
    measured with simulations (see README): players are fast compared to the
    ball, so defending is always possible.
    """
    HEAD_RADIUS = 41        # px: head radius (what hits the ball on headers)
    HEAD_OFFSET_Y = 65      # px: head centre measured from the sole
    BODY_RADIUS = 12        # px: boot radius
    BODY_OFFSET_Y = 12      # px: boot centre measured from the sole
    HALF_WIDTH = 34         # px: half width of the floor/wall/crossbar box
    HEIGHT = 106            # px: total height, from sole to top of the head
    SPAWN_X = (340, 940)    # px: start x of each player (left, right)

    MOVE_SPEED = 340        # px/s: top walking speed
    GROUND_ACCEL = 3400     # px/s²: quick acceleration...
    GROUND_DECEL = 4600     # px/s²: ...and strong braking: little sliding
    AIR_ACCEL = 2500        # px/s²: air acceleration (less control)
    AIR_DECEL = 1500        # px/s²: air braking
    JUMP_SPEED = 697        # px/s: ~128 px jump, head stays below the bar
    # Jumping from the rival's head (~216 px): reaches above the goal.
    HEAD_JUMP_BOOST = 1.3
    GRAVITY = 1900          # px/s²: gravity of the players
    MAX_FALL_SPEED = 1500   # px/s: top falling speed
    COYOTE_TIME = 0.07      # s: margin to jump right after leaving an edge
    JUMP_BUFFER = 0.10      # s: a press just before landing still counts

    KICK_DURATION = 0.22    # s: whole kick animation
    KICK_ACTIVE = (0.03, 0.17)  # s: window in which the foot hits
    KICK_COOLDOWN = 0.32    # s: recovery between kicks
    KICK_BUFFER = 0.08      # s: a kick press just before it is allowed counts
    KICK_REACH_X = 27       # px: foot centre from the player centre
    KICK_REACH_Y = 14       # px: foot height above the sole
    KICK_RADIUS = 22        # px: radius of the foot hit
    KICK_POWER = 920        # px/s: speed the kick gives to the ball
    # High kick (~52°): the ball "flies" up to the height of the powers.
    KICK_LIFT = 1.30
    KICK_CARRY = 0.25       # share of the player speed the ball inherits

    HEAD_RESTITUTION = 0.60  # bounce on the head (0 = none, 1 = no loss)
    BODY_RESTITUTION = 0.45  # bounce on the boot
    HEADER_BOOST = 34       # px/s: extra push if the head moves to the ball
    KNOCKBACK_CONTROL = 0.25  # horizontal control while being pushed
    # True: the character faces where it last moved and kicks that way.
    # False: it always faces the rival goal.
    FACE_MOVEMENT = True


class BallSpec:
    """Physical behaviour of the ball."""
    RADIUS = 17             # px: ball radius
    GRAVITY = 850           # px/s²: floaty ball...
    RESTITUTION_FLOOR = 0.60  # bounce on the floor
    RESTITUTION_WALL = 0.72  # bounce on the walls and the ceiling
    RESTITUTION_BAR = 0.55  # bounce on the crossbars
    MAX_RESTITUTION = 0.90  # cap even with "high bounce"
    FLOOR_FRICTION = 1.7    # 1/s: exponential damping while rolling
    # 1/s: ...that slows it in the air: goes high but does not cross the pitch
    AIR_DRAG = 1.0
    MAX_SPEED = 1150        # px/s: top ball speed
    REST_SPEED = 51         # px/s: below this the vertical bounce stops
    SUBSTEP_FRACTION = 0.45  # each substep moves at most 45 % of the radius
    SPAWN = (640, 330)      # px: where the ball appears at each kickoff
    SOUND_MIN_IMPACT = 145  # px/s: softer impacts make no sound
    # px/s²: a ball resting on the crossbar rolls back into the pitch
    BAR_ROLL_ACCEL = 360


class MatchRules:
    """Times of a match."""
    DURATION = 60.0         # s: effective playing time
    KICKOFF_COUNTDOWN = 3.0  # s: countdown of the first kickoff
    GOAL_COUNTDOWN = 2.0    # s: countdown after a goal
    RESUME_COUNTDOWN = 2.0  # s: countdown when a pause ends
    GOAL_CELEBRATION = 2.3  # s: goal celebration (the ball stays in the net)
    GOLDEN_GOAL_COUNTDOWN = 3.0  # s: kickoff of the golden goal
    # s: without controls from the interface for this long -> pause
    INPUT_WATCHDOG = 0.6


# ---------------------------------------------------------------------------
# Powers
# ---------------------------------------------------------------------------
class PowerRules:
    """When and where the powers appear, and how strong they are."""
    SPAWN_MIN = 7.0         # s of effective play, at least, between pickups
    SPAWN_MAX = 10.0        # s at most between two pickups
    PICKUP_TTL = 6.0        # s a pickup lasts if the ball does not touch it
    PICKUP_RADIUS = 26      # px: pickup radius (touched with the ball)
    # px: horizontal band where pickups appear (away from the goals)
    SPAWN_X = (Arena.GOAL_DEPTH + 110, Arena.WIDTH - Arena.GOAL_DEPTH - 110)
    # px: from near the floor up to a lob height
    SPAWN_Y = (Arena.FLOOR_Y - 260, Arena.FLOOR_Y - 70)
    SPAWN_MIN_BALL_DIST = 140   # px: they never appear next to the ball
    # Attempts to find a free spot before waiting for the next turn.
    SPAWN_TRIES = 40
    SIZE_TRANSITION = 0.30  # s to complete a size change
    GOAL_TRANSITION = 0.45  # s to complete a goal size change
    BOMB_WARNING = 1.0      # s of warning before a bomb explodes
    BOMB_ZONE_X = (520, 760)    # px: band where bombs fall (near the middle)
    BOMB_BLAST_RADIUS = 250     # px: reach of the explosion
    # px/s: top push to the ball (at the centre of the explosion)
    BOMB_BALL_IMPULSE = 1150
    BOMB_PLAYER_IMPULSE = 870   # px/s: top push to a player
    BOMB_KNOCKBACK = 0.35   # s: longest time without control after a blast


# Power category (the colour rule of the project).
CATEGORY_GOOD = "good"       # helps the receiver
CATEGORY_BAD = "bad"         # harms the receiver
CATEGORY_GLOBAL = "global"   # changes the match
# RGB colour of each category (icons, signs and effect borders).
CATEGORY_COLORS = {
    CATEGORY_GOOD: (46, 204, 113),
    CATEGORY_BAD: (231, 76, 60),
    CATEGORY_GLOBAL: (155, 89, 230),
}

# target: who the power applies to
#   self       -> receiver (last player who touched the ball)
#   rival      -> the other player
#   rival_goal -> the goal the rival defends (where the receiver attacks)
#   ball       -> the ball (global)
#   match      -> one-off match effect (bombs)
# prop: property it changes. Two effects with the same (target, prop)
# replace each other; with different props they coexist.
PowerDef = collections.namedtuple(
    "PowerDef",
    "id name label category target prop value duration description")

# (id, name, sign, category, target, property, value, seconds, description)
# value: multiplier of the property (1.35 = 35 % more) or size delta.
POWERS = (
    PowerDef("speed_up", "Velocidad aumentada", "VELOCIDAD +", CATEGORY_GOOD,
             "self", "speed", 1.35, 6.0, "Te movés más rápido (×1,35)."),
    PowerDef("jump_up", "Salto aumentado", "SALTO +", CATEGORY_GOOD,
             "self", "jump", 1.25, 6.0, "Tu salto es más alto (×1,25)."),
    PowerDef("freeze_rival", "Congelar al rival", "CONGELA RIVAL",
             CATEGORY_GOOD, "rival", "frozen", None, 2.0,
             "El rival no puede moverse, saltar ni patear."),
    PowerDef("big_goal", "Arco grande", "ARCO RIVAL +", CATEGORY_GOOD,
             "rival_goal", "goal_height", 1.35, 6.0,
             "El arco rival es más alto (×1,35)."),
    PowerDef("grow", "Crecer", "CRECER", CATEGORY_GOOD,
             "self", "size", 1.25, 6.0, "Tu tamaño aumenta (×1,25)."),
    PowerDef("injured_self", "Pierna propia lesionada", "LESIÓN",
             CATEGORY_BAD, "self", "no_kick", None, 4.0,
             "No podés patear; sí moverte, saltar y cabecear."),
    PowerDef("speed_down", "Velocidad reducida", "VELOCIDAD -", CATEGORY_BAD,
             "self", "speed", 0.65, 6.0, "Te movés más lento (×0,65)."),
    PowerDef("jump_down", "Salto reducido", "SALTO -", CATEGORY_BAD,
             "self", "jump", 0.75, 6.0, "Tu salto es más bajo (×0,75)."),
    PowerDef("freeze_self", "Congelarse", "CONGELADO", CATEGORY_BAD,
             "self", "frozen", None, 2.0,
             "No podés moverte, saltar ni patear."),
    PowerDef("small_goal", "Arco pequeño", "ARCO RIVAL -", CATEGORY_BAD,
             "rival_goal", "goal_height", 0.75, 6.0,
             "El arco rival se achica (×0,75)."),
    PowerDef("shrink", "Encogerse", "ENCOGER", CATEGORY_BAD,
             "self", "size", 0.75, 6.0, "Tu tamaño disminuye (×0,75)."),
    PowerDef("injured_rival", "Pierna rival lesionada", "LESIÓN RIVAL",
             CATEGORY_GOOD, "rival", "no_kick", None, 4.0,
             "El rival no puede patear; sí moverse y cabecear."),
    PowerDef("bombs", "Bombas", "BOMBA", CATEGORY_GLOBAL,
             "match", "bomb", None, 0.0,
             "Bomba en el centro: aviso de 1 s y explosión que empuja."),
    PowerDef("low_bounce", "Pelota con poco rebote", "POCO REBOTE",
             CATEGORY_GLOBAL, "ball", "bounce", 0.45, 6.0,
             "La pelota rebota mucho menos."),
    PowerDef("big_ball", "Pelota grande", "PELOTA +", CATEGORY_GLOBAL,
             "ball", "radius", 1.35, 6.0,
             "El radio de la pelota crece (×1,35)."),
    PowerDef("high_bounce", "Pelota con mucho rebote", "MUCHO REBOTE",
             CATEGORY_GLOBAL, "ball", "bounce", 1.30, 6.0,
             "La pelota rebota más (respeta la velocidad máxima)."),
    PowerDef("small_ball", "Pelota pequeña", "PELOTA -", CATEGORY_GLOBAL,
             "ball", "radius", 0.70, 6.0,
             "El radio de la pelota se reduce (×0,70)."),
    # Cosmetic powers (F3): they only last a while and change what is drawn;
    # the simulation ignores their property ("blackout", "confusion", "fire").
    PowerDef("blackout", "Apagón", "APAGÓN", CATEGORY_GOOD, "rival",
             "blackout", None, 6.0,
             "Se apagan las luces: sólo se ve alrededor del rival."),
    PowerDef("confusion", "Confusión", "CONFUSIÓN", CATEGORY_GOOD, "rival",
             "confusion", None, 5.0,
             "El rival ve la cancha al revés y torcida."),
    PowerDef("fire", "Pelota de fuego", "FUEGO", CATEGORY_GLOBAL, "ball",
             "fire", None, 6.0,
             "La pelota arde y el aire tiembla a su alrededor."),
)
POWER_IDS = tuple(p.id for p in POWERS)
POWERS_BY_ID = {p.id: p for p in POWERS}
# Targets that need a last touch (someone who receives the power).
PERSONAL_TARGETS = ("self", "rival", "rival_goal")


# ---------------------------------------------------------------------------
# Inter-process communication
# ---------------------------------------------------------------------------
class IPC:
    """Sizes and times of the queues between the interface and simulation."""
    COMMAND_QUEUE_SIZE = 64     # commands: never dropped
    INPUT_QUEUE_SIZE = 4        # controls: replaceable (cumulative counters)
    STATE_QUEUE_SIZE = 3        # states: replaceable, "the newest wins"
    EVENT_QUEUE_SIZE = 512      # events and acknowledgements
    # s: longest wait to put a command in its queue (else a visible error)
    COMMAND_PUT_TIMEOUT = 1.0
    ACK_TIMEOUT = 3.0           # s: no acknowledgement in time -> error
    # s: if the simulation does not report READY in time -> visible error
    READY_TIMEOUT = 20.0
    IDLE_WAIT = 0.05            # s: blocking wait of the process with no match
    PAUSED_HEARTBEAT = 0.2      # s: heartbeat states while paused
    # s: how often the simulation checks that the interface is still alive
    PARENT_CHECK_EVERY = 0.5
    SHUTDOWN_BYE_TIMEOUT = 2.0  # s: wait for the goodbye message
    JOIN_TIMEOUT = 2.0          # s: wait for the process to end before forcing
    MAX_EVENTS_PER_FRAME = 400  # events the interface handles per frame
    # s: the simulation retries a reliable event if its queue is full
    EVENT_PUT_RETRY = 0.2
    # s: on shutdown, each wait for BYE (to notice if the process died)
    BYE_POLL = 0.1


# ---------------------------------------------------------------------------
# Online (room server + browser). See docs/ONLINE.md
# ---------------------------------------------------------------------------
class Online:
    """Server, client and panel settings of the online mode."""
    PORT = 8765             # TCP port of the server (web page + WebSocket)
    WS_PATH = "/ws"
    # Default server of the desktop version (the web version uses the site
    # it was loaded from); change it with --server or FDC_SERVER.
    SERVER_URL = os.environ.get("FDC_SERVER", "ws://localhost:8765/ws")
    RECONNECT_GRACE = 30.0      # s to come back before losing by forfeit
    PAUSE_MAX = 30.0            # s a requested pause lasts at most
    PUMP_HZ = 60                # cycle of the room <-> simulation bridge
    STATE_HZ = 30               # states per second sent to each browser
    PING_EVERY = 2.0            # s: the client measures the latency
    MAX_MESSAGE_BYTES = 2048    # bytes: largest message from a client
    MAX_MESSAGES_PER_SEC = 150  # more than this is abuse: disconnected
    # Simultaneous connections at most (more get "server full").
    MAX_CONNECTIONS = 64
    MAX_ROOMS = 16              # each room in play uses a simulation process
    OUTBOX_LIMIT = 400          # unsent reliable messages -> client too slow
    CLIENT_INBOX = 512          # input queue of the desktop client
    HELLO_TIMEOUT = 10.0        # s to introduce itself after connecting
    # s: shortest wait reading the hello (if the deadline almost expired)
    HELLO_MIN_WAIT = 0.1
    RETRY_EVERY = 2.0           # s between client reconnection attempts
    FIRST_RETRY_DELAY = 0.5     # s until the first retry after a drop
    # s between server pings (detects dead connections)
    KEEPALIVE_EVERY = 5.0
    KEEPALIVE_TIMEOUT = 10.0    # s without a ping reply -> connection lost
    # s of slack so a state is not skipped for a few milliseconds
    STATE_SEND_SLACK = 0.004
    RATE_WINDOW = 1.0           # s: window to count a client's messages
    # Random bytes of the session token (to come back after a drop).
    TOKEN_BYTES = 18
    # s the server waits for the rooms that were closing
    SHUTDOWN_TASKS_WAIT = 10.0
    # s between room reports to the players (online F3 panel)
    ROOM_INFO_EVERY = 1.0
    PANEL_REFRESH = 1.0         # s between updates of the server panel
    PANEL_LOG_SIZE = 30         # process events kept by the panel
    PANEL_PATH = "/status"      # public panel (technical data only)
    PANEL_FULL_PATH = "/status/full"   # panel with names (asks a password)
    # Password of the full panel view; without it, that view does not exist.
    PANEL_PASSWORD = os.environ.get("FDC_PANEL_PASSWORD", "")
    CLIENT_RECEIVE_BATCH = 400  # messages the client handles per frame
    CONNECT_TIMEOUT = 5.0       # s to open the connection (desktop client)
    CLOSE_TIMEOUT = 1.0         # s for the closing handshake (desktop client)
    # bytes: the client accepts big states (1 MiB)
    CLIENT_MAX_MESSAGE = 2 ** 20
    # s: the reader thread retries if the input queue is full
    INBOX_PUT_WAIT = 0.2


# ---------------------------------------------------------------------------
# GPU effects (optional: the game runs without them, see fdc/gpu)
# ---------------------------------------------------------------------------
class Gpu:
    """Knobs of the post-processing chain that runs on the GPU."""
    ENABLED = os.environ.get("FDC_GPU", "1") != "0"   # FDC_GPU=0 turns it off
    QUALITY = os.environ.get("FDC_GPU_QUALITY", "media")   # baja|media|alta
    QUALITIES = ("baja", "media", "alta")   # from the cheapest to the richest
    GLOW_THRESHOLD = 0.62   # from this luma (0-1) a pixel glows
    GLOW_RADIUS = 3         # px of the halo blur
    GLOW_PASSES = 2         # box blurs of the halo
    EXPOSURE = 1.08         # brightness before the gamma
    GAMMA = 1.0             # gamma curve of the composite
    VIGNETTE = 0.35         # darkening of the corners
    GLOW_STRENGTH = 0.65    # weight of the halo in the composite
    PARTICLE_GAIN = 1.0     # weight of the sparks
    LIGHT_GAIN = 0.9        # weight of the spotlights
    PARTICLES = 1200        # particles alive at most
    PARTICLE_SIZE = 2.4     # px: radius of a spark
    PARTICLE_SPEED = (60.0, 320.0)   # px/s: speed of a spark
    PARTICLE_LIFE = (0.18, 0.55)     # s: life of a spark
    PARTICLE_GRAVITY = 420.0         # px/s^2 (y grows downwards)
    PARTICLE_PER_TOUCH = 10          # sparks of a kick or a bounce
    HEAT_AMP = 2.5          # px: depth of the heat waves
    HEAT_PERIOD = 26.0      # px: wavelength of the heat waves
    HEAT_SPEED = 2.4        # rad/s: how fast the waves move
    RIPPLE_AMP = 5.0        # px: depth of the replay ripple
    RIPPLE_PERIOD = 46.0    # px: wavelength of the replay ripple
    TRAIL_ALPHA = 0.35      # s: how much of the previous frame stays
    FREEZE_LIGHT = (0.45, 0.75, 1.0)   # rgb of the ice spotlight
    FREEZE_RADIUS = 260.0   # px: radius of the ice spotlight
    BLACKOUT_VEIL = 0.82    # 0-1: how much the blackout darkens
    # 80 x 45 cells of 16 px: the grid of the spec (one cell per 16 px).
    HEATMAP_COLS = 80       # cells of the heat map, across
    HEATMAP_ROWS = 45       # cells of the heat map, down
    REPLAY_SECONDS = 20.0   # s of states kept for the replay
    REPLAY_STEP = 0.25      # s between saved states
    METRICS_FRAMES = 120    # frames averaged by the overlay
    # --- F3: cosmetic powers (all lengths in px, all times in s) -------------
    FADE_IN = 0.15          # s a power takes to reach full strength
    FADE_OUT = 0.3          # s of the smooth exit at the end of a power
    HEAD_ABOVE = 65.0       # px above the feet: centre of the head
    ICE_TINT = (0.55, 0.85, 1.0)   # rgb of the ice tint
    ICE_STRENGTH = 0.55     # weight of the tint on the image (0-1)
    ICE_EDGES = 0.9         # weight of the bright edges (0-1)
    BLACKOUT_AMBIENT = 0.06   # light left far from the heads (0-1)
    BLACKOUT_RADIUS = 150.0   # px: radius of the blackout light
    BLACKOUT_TINT = (1.0, 1.0, 1.0)   # rgb multiplier of the blackout
    CONFUSION_MAX_DEG = 6.0   # degrees of the rotation at full strength
    CONFUSION_SPEED = 2.0     # rad/s of that rotation
    FIRE_RADIUS = 140.0       # px around the ball with hot air
    FIRE_AMP = 9.0            # px: depth of that distortion
    # --- F4: night, auto exposure, shock wave, trail -------------------------
    NIGHT_LIGHTS = 6          # spotlights over the pitch at night
    NIGHT_FIRST_X = 160.0     # px: first one
    NIGHT_STEP_X = 192.0      # px between two spotlights
    NIGHT_Y = 20.0            # px: height of the spotlights
    NIGHT_RADIUS = 420.0      # px: radius of each spotlight
    NIGHT_POWER = 0.9         # intensity of each spotlight (0-1)
    NIGHT_AMBIENT = 0.15      # light between the spotlights (0-1)
    NIGHT_TINT = (1.0, 0.86, 0.66)   # warm rgb of the night lights
    AUTOEXPOSURE_TARGET = 110.0   # mean luma the night tries to reach
    AUTOEXPOSURE_MIN = 0.6        # lowest gain
    AUTOEXPOSURE_MAX = 2.5        # highest gain
    AUTOEXPOSURE_RATE = 0.1       # EMA weight of each frame (0-1)
    SHOCK_DURATION = 1.2      # s of the goal shock wave
    SHOCK_RADIUS = 900.0      # px/s: the ring grows this fast
    SHOCK_WIDTH = 90.0        # px: thickness of the ring
    SHOCK_AMP = 14.0          # px: displacement when it starts
    TRAIL_MIN_SPEED = 800.0   # px/s: from here the ball leaves a trail
    TRAIL_OFF_DELAY = 0.25    # s the trail stays after the ball slows down
    TRAIL_DECAY = 0.55        # share of the previous frame that stays (0-1)
    # --- F5: replay and VAR (the review of a close goal) ---------------------
    REPLAY_DURATION = 3.0     # s of the match shown again after a goal
    VAR_DURATION = 2.0        # s of the referee review
    VAR_CONFIRM = 0.8         # s the "goal stands" sign stays after that
    VAR_FRAMES = 6            # saved states the review looks back
    CRT_TINT = (0.80, 1.0, 0.85)   # rgb of the old television
    CRT_SCAN = 0.35           # darkening of the scan lines (0-1)
    CRT_VIGNETTE = 0.45       # darkening of the corners (0-1)
    CRT_NOISE = 0.10          # strength of the grain (0-1)
    CRT_AMOUNT = 0.9          # weight of the whole CRT look (0-1)
    CRT_ROWS = 3              # px between two scan lines
    VAR_TINT = (0.55, 1.0, 0.65)   # green of the review edges
    VAR_EDGES = 0.9           # weight of those edges over the gray (0-1)
    VAR_ZOOM = 2.2            # px factor of the zoom of the review
    # --- F6: heat map (cells of 16 px on the 1280 x 720 pitch) --------------
    HEAT_FLUSH_FRAMES = 15    # frames between two flushes to the GPU
    HEAT_FLUSH_POINTS = 256   # points kept in the host buffer at most
    HEATMAP_ALPHA = 0.55      # weight of the map over the image (0-1)
    HEATMAP_GAIN = 4.0        # cells over the maximum that saturate the map
    # --- F7: adaptive quality (CPU only), demo and measurements ---------------
    QUALITY_DOWN_MS = 18.0    # mean frame ms above this: one level down
    QUALITY_UP_MS = 11.0      # mean frame ms below this: it may go up
    QUALITY_AVG_FRAMES = 30   # frames averaged by the governor
    QUALITY_UP_FRAMES = 120   # frames below QUALITY_UP_MS needed to go up
    QUALITY_MIN_SECONDS = 3.0   # s between two level changes
    QUALITY_LEVELS = ("Q0", "Q1", "Q2", "Q3")   # richest to cheapest
    QUALITY_SCALES = (1, 2, 4, 4)   # image divisor of each level
    DEMO_SEED = 2026          # first seed of the automatic demo
    DEMO_SECONDS = 10.0       # s of each segment of the demo
    DEMO_BOT_LEVEL = 4        # skill of the two bots of the demo
    DEMO_RESTART_SECONDS = 1.0   # s from whistle to next match
    DEMO_SHOCK_EVERY = 2.5    # s between forced goal waves (segment 7)
    DEMO_REPLAY_EVERY = 4.5   # s between replays of segment 8 and 9
    MEASURE_WARMUP = 30       # frames dropped at the start of each segment
    OVERLAY_ALPHA = 190       # opacity of the overlay background (0-255)
    OVERLAY_FONT = 22         # px: minimum size of the overlay text
    OVERLAY_REFRESH = 0.25    # s between overlay text rebuilds (4 Hz)
    MEASURE_FPS = 1000.0      # milliseconds in a second (capacity of a frame)
    # --- F10: goal celebration (confetti before the replay) ------------------
    GOAL_CELEBRATION = 2.0    # s of party before the replay starts
    CONFETTI = 820            # paper bits alive at most
    CONFETTI_PER_BURST = 120  # paper bits thrown by each burst
    CONFETTI_SIZE = (2.5, 5.0)   # px: half width of a paper bit
    CONFETTI_THICK = 0.55     # share of that half width the bit is tall
    CONFETTI_SPEED = (120.0, 520.0)   # px/s: speed a bit leaves the burst
    CONFETTI_LIFE = (1.2, 2.4)        # s: life of a bit
    CONFETTI_GRAVITY = 320.0  # px/s^2 (y grows downwards)
    CONFETTI_DRAG = 0.6       # 1/s: the air slows the bits down
    CONFETTI_SWAY = (30.0, 90.0)      # px/s: sideways speed of the flutter
    CONFETTI_SPIN = (5.0, 12.0)       # rad/s: the bit turns and shows its edge
    CONFETTI_GAIN = 1.0       # 0-1: opacity of the paper over the image
    CONFETTI_FLASH = 0.30     # 0-1: white flash right after the goal
    CONFETTI_FLASH_TIME = 0.18   # s the flash takes to fade out
    # --- F10: the replay ends this long after the goal (constant) -----------
    REPLAY_AFTER_GOAL = 0.5   # s of the net the replay shows after the goal


# ---------------------------------------------------------------------------
# Optional folders to replace generated resources with own files
# ---------------------------------------------------------------------------
# assets/sprites/<character>/head.png, assets/sounds/<name>.wav, ...
ASSET_OVERRIDE_DIR = "assets"
LOG_DIR = os.path.join(ROOT_DIR, "logs")
