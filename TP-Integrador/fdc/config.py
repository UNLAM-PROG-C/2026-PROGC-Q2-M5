"""Configuración central del juego.

Este módulo NO importa pygame: lo usan tanto la interfaz como el proceso de
simulación. Todo lo que sea "un número para ajustar" vive acá, para poder
cambiar nombre, teclas, física o poderes sin tocar la lógica.

Unidades: píxeles de la resolución lógica (1280 x 720) y segundos.
"""
import os
from collections import namedtuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Identidad
# ---------------------------------------------------------------------------
GAME_NAME = "Futbol De Cabeza"
GAME_TAGLINE = "Duelo de cabezones - 2 jugadores - 1 teclado"
PROTOCOL_VERSION = 1

# ---------------------------------------------------------------------------
# Pantalla (resolución lógica de referencia; la ventana escala con SCALED
# conservando la proporción y agregando bandas si hace falta)
# ---------------------------------------------------------------------------
LOGICAL_WIDTH = 1280
LOGICAL_HEIGHT = 720
UI_FPS = 60

# ---------------------------------------------------------------------------
# Controles. Se guardan como nombres de tecla de pygame (pygame.key.key_code)
# para que este módulo no dependa de pygame. Índice 0 = J1, 1 = J2.
# ---------------------------------------------------------------------------
PLAYER_KEYS = (
    {"left": "a", "right": "d", "jump": "w", "kick": "space"},
    {"left": "left", "right": "right", "jump": "up", "kick": "p"},
)
PAUSE_KEY = "escape"
DEBUG_PANEL_KEY = "f3"
FULLSCREEN_KEY = "f11"
MUTE_KEY = "m"
# Teclas del modo de prueba (sólo activas con --prueba)
TEST_PREV_POWER_KEY = "f5"
TEST_NEXT_POWER_KEY = "f6"
TEST_SPAWN_POWER_KEY = "f7"
TEST_GIVE_P1_KEY = "f8"
TEST_GIVE_P2_KEY = "f9"
TEST_CRASH_SIM_KEY = "f12"

PLAYER_LABELS = ("J1", "J2")
# Personajes disponibles (la apariencia está en fdc/ui/characters.py; la
# simulación NO usa esta lista para calcular nada: todos juegan igual).
CHARACTER_IDS = ("messi", "maradona", "pele", "cr7", "henry", "neymar", "mbappe")
# Colores de identificación de cada jugador (contorno e indicador). Se eligieron
# para no confundirse con ninguna camiseta ni con las categorías de poderes.
PLAYER_COLORS = ((255, 138, 30), (255, 64, 160))

# ---------------------------------------------------------------------------
# Cancha
# ---------------------------------------------------------------------------
class Arena:
    WIDTH = 1280
    HEIGHT = 720
    FLOOR_Y = 646          # línea donde apoyan los botines y rebota la pelota
    CEILING_Y = 0          # techo invisible: la pelota no sale de la pantalla
    GOAL_DEPTH = 112       # profundo: aunque un jugador se meta, la pelota puede cruzar la línea
    GOAL_HEIGHT = 250      # un jugador saltando desde el piso no llega al travesaño
    BAR_THICKNESS = 10     # grosor del travesaño (cápsula con punta redonda)
    GOAL_MIN_HEIGHT = 150  # límites de seguridad para los poderes de arco
    GOAL_MAX_HEIGHT = 340


# ---------------------------------------------------------------------------
# Física. Paso fijo: la simulación avanza siempre de a PHYSICS_DT, sin
# importar a cuántos cuadros por segundo dibuje la interfaz.
# ---------------------------------------------------------------------------
PHYSICS_HZ = 120
PHYSICS_DT = 1.0 / PHYSICS_HZ
STATE_EVERY_TICKS = 2          # se publica un estado cada 2 pasos (60 por s)
MAX_CATCHUP_STEPS = 6          # si la simulación se atrasa, no intenta "recuperar" más


class PlayerSpec:
    """Capacidades base: idénticas para los siete personajes.

    El jugador es una cabeza grande con un botín debajo (estilo "cabezones"):
    un círculo de cabeza y un círculo chico de botín para chocar con la pelota
    y con el otro jugador, y una caja para piso, paredes y travesaños.
    Balance medido con simulaciones (ver README): los jugadores son rápidos en
    relación con la pelota para que siempre se pueda volver a defender.
    """
    HEAD_RADIUS = 41
    HEAD_OFFSET_Y = 65      # centro de la cabeza medido desde la suela
    BODY_RADIUS = 12        # botín
    BODY_OFFSET_Y = 12
    HALF_WIDTH = 34         # caja para chocar con piso, paredes y travesaños
    HEIGHT = 106
    SPAWN_X = (340, 940)

    MOVE_SPEED = 340
    GROUND_ACCEL = 3400     # aceleración rápida...
    GROUND_DECEL = 4600     # ...y frenado fuerte: poco deslizamiento
    AIR_ACCEL = 2500
    AIR_DECEL = 1500
    JUMP_SPEED = 697        # ~128 px: la cabeza queda por debajo del travesaño
    HEAD_JUMP_BOOST = 1.3   # saltando desde la cabeza del rival (~216 px): se llega arriba del arco
    GRAVITY = 1900
    MAX_FALL_SPEED = 1500
    COYOTE_TIME = 0.07      # margen para saltar justo al salir de un borde
    JUMP_BUFFER = 0.10      # una pulsación apenas antes de aterrizar cuenta

    KICK_DURATION = 0.22    # duración total de la animación
    KICK_ACTIVE = (0.03, 0.17)  # ventana en la que el pie golpea
    KICK_COOLDOWN = 0.32    # recuperación entre patadas (configurable)
    KICK_BUFFER = 0.08
    KICK_REACH_X = 27       # centro del pie respecto del centro del jugador
    KICK_REACH_Y = 14
    KICK_RADIUS = 22
    KICK_POWER = 920
    KICK_LIFT = 1.30        # patada alta (~52°): la pelota "vuela" hasta la altura de los poderes
    KICK_CARRY = 0.25       # fracción de la velocidad del jugador que hereda

    HEAD_RESTITUTION = 0.60
    BODY_RESTITUTION = 0.45
    HEADER_BOOST = 34       # empujón extra si la cabeza va hacia la pelota
    KNOCKBACK_CONTROL = 0.25  # control horizontal mientras dura un empujón
    # True: el personaje mira hacia donde se movió por última vez y patea en esa
    # dirección. False: siempre mira hacia el arco rival.
    FACE_MOVEMENT = True


class BallSpec:
    RADIUS = 17
    GRAVITY = 850            # pelota flotante...
    RESTITUTION_FLOOR = 0.60
    RESTITUTION_WALL = 0.72
    RESTITUTION_BAR = 0.55
    MAX_RESTITUTION = 0.90   # tope aun con "mucho rebote"
    FLOOR_FRICTION = 1.7     # amortiguación exponencial al rodar (1/s)
    AIR_DRAG = 1.0           # ...que frena en el aire: sube alto pero no cruza toda la cancha
    MAX_SPEED = 1150
    REST_SPEED = 51          # por debajo, el rebote vertical se anula
    SUBSTEP_FRACTION = 0.45  # cada subpaso mueve como máximo 45 % del radio
    SPAWN = (640, 330)
    SOUND_MIN_IMPACT = 145   # impactos más suaves no generan sonido
    BAR_ROLL_ACCEL = 360     # una pelota quieta sobre el travesaño rueda hacia la cancha


class MatchRules:
    DURATION = 60.0          # tiempo efectivo
    KICKOFF_COUNTDOWN = 3.0
    GOAL_COUNTDOWN = 2.0
    RESUME_COUNTDOWN = 2.0
    GOAL_CELEBRATION = 2.3
    INPUT_WATCHDOG = 0.6     # sin controles de la interfaz por este tiempo -> pausa


# ---------------------------------------------------------------------------
# Poderes
# ---------------------------------------------------------------------------
class PowerRules:
    SPAWN_MIN = 7.0
    SPAWN_MAX = 10.0
    PICKUP_TTL = 6.0
    PICKUP_RADIUS = 26
    SPAWN_X = (Arena.GOAL_DEPTH + 110, Arena.WIDTH - Arena.GOAL_DEPTH - 110)
    SPAWN_Y = (Arena.FLOOR_Y - 260, Arena.FLOOR_Y - 70)   # a ras del piso o para un globo
    SPAWN_MIN_BALL_DIST = 140
    SPAWN_TRIES = 40
    SIZE_TRANSITION = 0.30   # segundos para completar un cambio de tamaño
    GOAL_TRANSITION = 0.45
    BOMB_WARNING = 1.0
    BOMB_ZONE_X = (520, 760)
    BOMB_BLAST_RADIUS = 250
    BOMB_BALL_IMPULSE = 1150
    BOMB_PLAYER_IMPULSE = 870
    BOMB_KNOCKBACK = 0.35


# categoría -> color de la regla del proyecto
CATEGORY_GOOD = "verde"      # beneficia al receptor
CATEGORY_BAD = "rojo"        # perjudica al receptor
CATEGORY_GLOBAL = "violeta"  # modifica el partido
CATEGORY_COLORS = {
    CATEGORY_GOOD: (46, 204, 113),
    CATEGORY_BAD: (231, 76, 60),
    CATEGORY_GLOBAL: (155, 89, 230),
}

# target: a quién se aplica
#   self       -> receptor (último que tocó la pelota)
#   rival      -> el otro jugador
#   rival_goal -> el arco que defiende el rival (donde ataca el receptor)
#   ball       -> la pelota (global)
#   match      -> efecto puntual del partido (bombas)
# prop: propiedad que modifica. Dos efectos con el mismo (objetivo, prop) se
# reemplazan; con props distintas conviven.
PowerDef = namedtuple(
    "PowerDef", "id name label category target prop value duration description")

POWERS = (
    PowerDef("speed_up", "Velocidad aumentada", "VELOCIDAD +", CATEGORY_GOOD,
             "self", "speed", 1.35, 6.0, "Te movés más rápido (×1,35)."),
    PowerDef("jump_up", "Salto aumentado", "SALTO +", CATEGORY_GOOD,
             "self", "jump", 1.25, 6.0, "Tu salto es más alto (×1,25)."),
    PowerDef("freeze_rival", "Congelar al rival", "CONGELA RIVAL", CATEGORY_GOOD,
             "rival", "frozen", None, 2.0, "El rival no puede moverse, saltar ni patear."),
    PowerDef("big_goal", "Arco grande", "ARCO RIVAL +", CATEGORY_GOOD,
             "rival_goal", "goal_height", 1.35, 6.0, "El arco rival es más alto (×1,35)."),
    PowerDef("grow", "Crecer", "CRECER", CATEGORY_GOOD,
             "self", "size", 1.25, 6.0, "Tu tamaño aumenta (×1,25)."),
    PowerDef("injured_self", "Pierna propia lesionada", "LESIÓN", CATEGORY_BAD,
             "self", "no_kick", None, 4.0, "No podés patear; sí moverte, saltar y cabecear."),
    PowerDef("speed_down", "Velocidad reducida", "VELOCIDAD -", CATEGORY_BAD,
             "self", "speed", 0.65, 6.0, "Te movés más lento (×0,65)."),
    PowerDef("jump_down", "Salto reducido", "SALTO -", CATEGORY_BAD,
             "self", "jump", 0.75, 6.0, "Tu salto es más bajo (×0,75)."),
    PowerDef("freeze_self", "Congelarse", "CONGELADO", CATEGORY_BAD,
             "self", "frozen", None, 2.0, "No podés moverte, saltar ni patear."),
    PowerDef("small_goal", "Arco pequeño", "ARCO RIVAL -", CATEGORY_BAD,
             "rival_goal", "goal_height", 0.75, 6.0, "El arco rival se achica (×0,75)."),
    PowerDef("shrink", "Encogerse", "ENCOGER", CATEGORY_BAD,
             "self", "size", 0.75, 6.0, "Tu tamaño disminuye (×0,75)."),
    PowerDef("injured_rival", "Pierna rival lesionada", "LESIÓN RIVAL", CATEGORY_GOOD,
             "rival", "no_kick", None, 4.0, "El rival no puede patear; sí moverse y cabecear."),
    PowerDef("bombs", "Bombas", "BOMBA", CATEGORY_GLOBAL,
             "match", "bomb", None, 0.0, "Bomba en el centro: aviso de 1 s y explosión que empuja."),
    PowerDef("low_bounce", "Pelota con poco rebote", "POCO REBOTE", CATEGORY_GLOBAL,
             "ball", "bounce", 0.45, 6.0, "La pelota rebota mucho menos."),
    PowerDef("big_ball", "Pelota grande", "PELOTA +", CATEGORY_GLOBAL,
             "ball", "radius", 1.35, 6.0, "El radio de la pelota crece (×1,35)."),
    PowerDef("high_bounce", "Pelota con mucho rebote", "MUCHO REBOTE", CATEGORY_GLOBAL,
             "ball", "bounce", 1.30, 6.0, "La pelota rebota más (respeta la velocidad máxima)."),
    PowerDef("small_ball", "Pelota pequeña", "PELOTA -", CATEGORY_GLOBAL,
             "ball", "radius", 0.70, 6.0, "El radio de la pelota se reduce (×0,70)."),
)
POWER_IDS = tuple(p.id for p in POWERS)
POWERS_BY_ID = {p.id: p for p in POWERS}
PERSONAL_TARGETS = ("self", "rival", "rival_goal")  # necesitan un último toque

# ---------------------------------------------------------------------------
# Comunicación entre procesos
# ---------------------------------------------------------------------------
class IPC:
    COMMAND_QUEUE_SIZE = 64     # órdenes: nunca se descartan
    INPUT_QUEUE_SIZE = 4        # controles: reemplazables (contadores acumulados)
    STATE_QUEUE_SIZE = 3        # estados: reemplazables, "el último gana"
    EVENT_QUEUE_SIZE = 512      # eventos y confirmaciones
    COMMAND_PUT_TIMEOUT = 1.0
    ACK_TIMEOUT = 3.0           # sin confirmación en este tiempo -> error visible
    READY_TIMEOUT = 20.0
    IDLE_WAIT = 0.05            # espera bloqueante del proceso sin partido
    PAUSED_HEARTBEAT = 0.2      # estados de latido mientras está en pausa
    PARENT_CHECK_EVERY = 0.5
    SHUTDOWN_BYE_TIMEOUT = 2.0  # espera del mensaje de despedida
    JOIN_TIMEOUT = 2.0          # espera de fin del proceso antes de forzar
    MAX_EVENTS_PER_FRAME = 400

# ---------------------------------------------------------------------------
# Rutas opcionales para reemplazar recursos generados por archivos propios
# ---------------------------------------------------------------------------
ASSET_OVERRIDE_DIR = "assets"   # assets/sprites/<personaje>/cabeza.png, assets/sonidos/<nombre>.wav
LOG_DIR = os.path.join(ROOT_DIR, "logs")
