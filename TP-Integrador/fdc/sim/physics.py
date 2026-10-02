"""Física del partido: entidades y colisiones.

Decisiones:
* Paso fijo (config.PHYSICS_DT). La pelota además se subdivide en subpasos
  para que nunca avance más de una fracción de su radio: así no atraviesa
  cabezas, cuerpos ni travesaños aunque viaje a velocidad máxima.
* Los jugadores son "cinemáticos" frente a la pelota (la empujan sin frenarse);
  entre ellos se separan con masas iguales.
* Forma de un jugador: círculo de cabeza + círculo de cuerpo para la pelota y
  para el otro jugador; una caja (AABB) para piso, paredes y travesaños.
* El travesaño es una cápsula horizontal: su punta redondeada es la esquina
  poste-travesaño. La pared del fondo actúa como poste trasero.
"""
import math

from ..config import Arena, BallSpec as BS, PlayerSpec as PS, PowerRules

HALF_BAR = Arena.BAR_THICKNESS / 2.0   # radio de la cápsula del travesaño (mitad de su grosor)

# --- constantes internas de la física (los valores "del juego" están en config.py)
EPSILON = 1e-6              # distancia mínima para normalizar un vector (evita dividir por cero)
BAR_BEYOND_WALL = 40.0      # px que el travesaño sigue por detrás de la pared: la pelota no se cuela por la punta
STACK_NORMAL = 0.8          # choque casi vertical entre jugadores (|ny| mayor): uno cae sobre la cabeza del otro
STACK_SLIDE_BIAS = 0.45     # empujón lateral que se suma en ese caso para que se deslice y no quede apoyado
SUPPORT_NORMAL = 0.3        # desde esta componente vertical, el de abajo (apoyado en el piso) no se mueve
HEADER_MIN_APPROACH = 40.0  # px/s: la cabeza tiene que ir hacia la pelota al menos así para sumar el cabezazo
MAX_BALL_SUBSTEPS = 16      # tope de subpasos de la pelota por paso de física (aunque vaya muy rápido)
BAR_REST_TOLERANCE = 2.0    # px: margen para considerar que la pelota está apoyada sobre el travesaño
BAR_REST_MAX_VY = 120.0     # px/s: más rápido que esto (subiendo o cayendo) no se considera apoyada
KICK_HEIGHT_SCALE = 60.0    # px de diferencia de altura entre pelota y pie que cambian la elevación en 1
KICK_LIFT_MIN_CHANGE = -0.35  # la elevación de la patada baja como mucho esto (pelota muy por debajo del pie)
KICK_LIFT_MAX_CHANGE = 0.5    # y sube como mucho esto (pelota por encima del pie)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def approach(value, target, delta):
    if value < target:
        return min(value + delta, target)
    return max(value - delta, target)


def sign(v):
    return (v > 0) - (v < 0)


# ---------------------------------------------------------------------------
# Arco
# ---------------------------------------------------------------------------
class Goal:
    """side 0 = arco izquierdo (lo defiende J1); side 1 = derecho (J2)."""

    # px/s: el arco cambia el 35 % de su alto (el cambio de los poderes) en GOAL_TRANSITION s
    RATE = Arena.GOAL_HEIGHT * 0.35 / PowerRules.GOAL_TRANSITION

    def __init__(self, side):
        self.side = side
        self.base_height = float(Arena.GOAL_HEIGHT)
        self.reset()

    def reset(self):
        self.height = self.base_height
        self.target_height = self.base_height

    @property
    def mouth_x(self):
        return Arena.GOAL_DEPTH if self.side == 0 else Arena.WIDTH - Arena.GOAL_DEPTH

    @property
    def toward_field(self):
        return 1 if self.side == 0 else -1

    def bar_y(self):
        """Altura (y) del eje de la cápsula del travesaño."""
        return Arena.FLOOR_Y - self.height - HALF_BAR

    def bar_segment(self):
        y = self.bar_y()
        if self.side == 0:
            return (-BAR_BEYOND_WALL, y, float(self.mouth_x), y)
        return (float(self.mouth_x), y, Arena.WIDTH + BAR_BEYOND_WALL, y)

    def bar_rect(self):
        y = self.bar_y()
        if self.side == 0:
            return (0.0, y - HALF_BAR, self.mouth_x + HALF_BAR, y + HALF_BAR)
        return (self.mouth_x - HALF_BAR, y - HALF_BAR, float(Arena.WIDTH), y + HALF_BAR)

    def set_multiplier(self, mult):
        self.target_height = clamp(self.base_height * mult,
                                   Arena.GOAL_MIN_HEIGHT, Arena.GOAL_MAX_HEIGHT)

    def update(self, dt):
        # transición gradual: el travesaño se desliza, no se teletransporta
        self.height = approach(self.height, self.target_height, self.RATE * dt)

    def ball_inside(self, ball):
        """La pelota cruzó COMPLETAMENTE la línea de gol por debajo del travesaño."""
        if ball.y <= self.bar_y():
            return False
        if self.side == 0:
            return ball.x + ball.radius < self.mouth_x
        return ball.x - ball.radius > self.mouth_x


# ---------------------------------------------------------------------------
# Pelota
# ---------------------------------------------------------------------------
class Ball:
    # px/s: el radio cambia el 35 % (pelota grande o chica) en SIZE_TRANSITION s
    RADIUS_RATE = BS.RADIUS * 0.35 / PowerRules.SIZE_TRANSITION

    def __init__(self):
        self.base_radius = float(BS.RADIUS)
        self.bounce_mult = 1.0
        self.reset()

    def reset(self, x=BS.SPAWN[0], y=BS.SPAWN[1]):
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.radius = self.target_radius = self.base_radius
        self.angle = 0.0
        self.bounce_mult = 1.0

    def restitution(self, base):
        return min(base * self.bounce_mult, BS.MAX_RESTITUTION)

    def set_radius_multiplier(self, mult):
        self.target_radius = self.base_radius * mult

    def update_size(self, dt):
        self.radius = approach(self.radius, self.target_radius, self.RADIUS_RATE * dt)

    def clamp_speed(self):
        sp = math.hypot(self.vx, self.vy)
        if sp > BS.MAX_SPEED:
            k = BS.MAX_SPEED / sp
            self.vx *= k
            self.vy *= k

    @property
    def on_floor(self):
        return self.y + self.radius >= Arena.FLOOR_Y - 0.5


# ---------------------------------------------------------------------------
# Jugador
# ---------------------------------------------------------------------------
class Player:
    # 1/s: la escala del jugador cambia 0.25 (agrandar o encoger) en SIZE_TRANSITION s
    SCALE_RATE = 0.25 / PowerRules.SIZE_TRANSITION

    def __init__(self, idx):
        self.idx = idx
        self.reset()

    def reset(self):
        self.x = float(PS.SPAWN_X[self.idx])
        self.y = float(Arena.FLOOR_Y)
        self.vx = self.vy = 0.0
        self.facing = 1 if self.idx == 0 else -1
        self.on_ground = True
        self.coyote = 0.0
        self.jump_buffer = 0.0
        self.kick_t = -1.0          # tiempo transcurrido de la patada (-1: no patea)
        self.kick_cooldown = 0.0
        self.kick_buffer = 0.0
        self.kick_hit = False       # una patada golpea como máximo una vez
        self.scale = self.target_scale = 1.0
        self.stride = 0.0           # distancia recorrida (para animar pasos)
        self.knockback = 0.0
        self.celebrating = False
        self.on_head = None         # índice del jugador sobre cuya cabeza está parado
        self.ball_ignore = 0.0      # tras patear, la pelota no choca con quien pateó
        self.prev_y = self.y
        self.clear_modifiers()

    def clear_modifiers(self):
        self.speed_mult = 1.0
        self.jump_mult = 1.0
        self.frozen = False
        self.no_kick = False
        self.target_scale = 1.0

    # --- geometría (siempre derivada de scale: gráficos y colisiones juntos)
    def head(self):
        s = self.scale
        return self.x, self.y - PS.HEAD_OFFSET_Y * s, PS.HEAD_RADIUS * s

    def body(self):
        s = self.scale
        return self.x, self.y - PS.BODY_OFFSET_Y * s, PS.BODY_RADIUS * s

    def circles(self):
        return (self.head(), self.body())

    def half_width(self):
        return PS.HALF_WIDTH * self.scale

    def height(self):
        return PS.HEIGHT * self.scale

    def foot(self):
        s = self.scale
        return (self.x + self.facing * PS.KICK_REACH_X * s,
                self.y - PS.KICK_REACH_Y * s, PS.KICK_RADIUS * s)

    def kick_active(self):
        lo, hi = PS.KICK_ACTIVE
        return lo <= self.kick_t <= hi

    def kick_progress(self):
        return self.kick_t / PS.KICK_DURATION if self.kick_t >= 0 else -1.0

    def update_size(self, dt):
        self.scale = approach(self.scale, self.target_scale, self.SCALE_RATE * dt)


# ---------------------------------------------------------------------------
# Control y movimiento de jugadores
# ---------------------------------------------------------------------------
def control_player(p, dt, move_dir, jump_pressed, kick_pressed, out_events):
    """Aplica la intención del jugador. out_events recibe tuplas (tipo, datos)."""
    if jump_pressed:
        p.jump_buffer = PS.JUMP_BUFFER
    if kick_pressed:
        p.kick_buffer = PS.KICK_BUFFER

    can_act = not p.frozen
    if not can_act:
        # congelado: sin acciones voluntarias (gravedad y choques siguen)
        move_dir = 0
        p.jump_buffer = 0.0
        if p.kick_t >= 0:
            p.kick_t = -1.0

    target = move_dir * PS.MOVE_SPEED * p.speed_mult
    if move_dir and PS.FACE_MOVEMENT:
        p.facing = move_dir
    if p.on_ground:
        rate = PS.GROUND_ACCEL if target and p.vx * target >= 0 else PS.GROUND_DECEL
    else:
        rate = PS.AIR_ACCEL if target else PS.AIR_DECEL
    if p.knockback > 0:
        rate *= PS.KNOCKBACK_CONTROL
        p.knockback = max(0.0, p.knockback - dt)
    p.vx = approach(p.vx, target, rate * dt)

    # salto: sólo desde el suelo (con un pequeño margen), nunca doble
    if p.on_ground:
        p.coyote = PS.COYOTE_TIME
    else:
        p.coyote = max(0.0, p.coyote - dt)
    if can_act and p.jump_buffer > 0 and (p.on_ground or p.coyote > 0):
        # desde la cabeza del rival se salta un poco más (así se llega al travesaño)
        boost = PS.HEAD_JUMP_BOOST if p.on_head is not None else 1.0
        p.vy = -PS.JUMP_SPEED * p.jump_mult * boost
        p.on_ground = False
        p.coyote = 0.0
        p.jump_buffer = 0.0
    p.jump_buffer = max(0.0, p.jump_buffer - dt)

    # patada: una por pulsación, con recuperación
    if p.kick_t >= 0:
        p.kick_t += dt
        if p.kick_t > PS.KICK_DURATION:
            p.kick_t = -1.0
    p.kick_cooldown = max(0.0, p.kick_cooldown - dt)
    p.ball_ignore = max(0.0, p.ball_ignore - dt)
    if p.kick_buffer > 0 and p.kick_t < 0 and p.kick_cooldown <= 0:
        p.kick_buffer = 0.0
        if can_act and not p.no_kick:
            p.kick_t = 0.0
            p.kick_hit = False
            p.kick_cooldown = PS.KICK_COOLDOWN
            out_events.append(("kick", p.idx))
        else:
            out_events.append(("kick_blocked", p.idx))
    p.kick_buffer = max(0.0, p.kick_buffer - dt)



def integrate_player(p, dt, goals):
    p.vy = min(p.vy + PS.GRAVITY * dt, PS.MAX_FALL_SPEED)
    p.prev_y = p.y
    prev_bottom = p.y
    prev_top = p.y - p.height()
    p.x += p.vx * dt
    p.y += p.vy * dt
    p.on_ground = False
    if p.y >= Arena.FLOOR_Y:
        p.y = float(Arena.FLOOR_Y)
        if p.vy > 0:
            p.vy = 0.0
        p.on_ground = True
    for g in goals:
        _resolve_player_bar(p, g, prev_bottom, prev_top)
    clamp_player_walls(p)
    if p.on_ground:
        p.stride += abs(p.vx) * dt


# empuje lateral máximo por paso cuando un cambio de tamaño/arco genera solape
MAX_PUSH_PER_STEP = 8.0
HEAD_STAND_FRACTION = 0.8   # qué tan lejos del centro de la cabeza se puede apoyar


def _head_surface(low, x):
    """Altura (y) de la parte de arriba de la cabeza de 'low' en la posición x."""
    hx, hy, hr = low.head()
    dx = x - hx
    if abs(dx) > hr * HEAD_STAND_FRACTION:
        return None
    return hy - math.sqrt(hr * hr - dx * dx)


def land_on_heads(players):
    """La cabeza del otro jugador funciona como piso: se puede caer parado sobre
    ella y saltar desde ahí. No la "lleva": si el de abajo se corre, o el de
    arriba camina hacia el borde, el de arriba cae (nadie queda trabado ni
    puede quedarse sentado para siempre sobre el rival)."""
    for top in players:
        low = players[1 - top.idx]
        was_on = top.on_head == low.idx
        top.on_head = None
        if top.y >= Arena.FLOOR_Y - 0.5 or top.vy < low.vy - 1.0:
            continue                    # en el piso, o subiendo (acaba de saltar)
        surface = _head_surface(low, top.x)
        if surface is None:
            continue
        if (was_on or top.prev_y <= surface + 2.0) and top.y >= surface - 1.0:
            top.y = surface
            top.vy = low.vy
            top.on_ground = True
            top.on_head = low.idx
            clamp_player_walls(top)


def _resolve_player_bar(p, goal, prev_bottom, prev_top):
    x0, y0, x1, y1 = goal.bar_rect()
    hw, h = p.half_width(), p.height()
    if p.x + hw <= x0 or p.x - hw >= x1 or p.y <= y0 or p.y - h >= y1:
        return
    if prev_bottom <= y0 + 0.5 and p.vy >= 0:
        # aterriza sobre el travesaño
        p.y = y0
        p.vy = 0.0
        p.on_ground = True
        return
    if prev_top >= y1 - 0.5 and p.vy < 0:
        # cabezazo contra la parte inferior
        p.y = y1 + h
        p.vy = 0.0
        return
    # solape lateral (o porque el arco/jugador cambió de tamaño): se lo
    # desplaza hacia la cancha, gradualmente si el solape es grande
    d = goal.toward_field
    need = (x1 + hw - p.x) if d > 0 else (p.x - (x0 - hw))
    p.x += d * min(need, MAX_PUSH_PER_STEP)
    if p.vx * d < 0:
        p.vx = 0.0


def clamp_player_walls(p):
    hw = p.half_width()
    if p.x - hw < 0:
        p.x = hw
        if p.vx < 0:
            p.vx = 0.0
    elif p.x + hw > Arena.WIDTH:
        p.x = Arena.WIDTH - hw
        if p.vx > 0:
            p.vx = 0.0
    if p.y > Arena.FLOOR_Y:
        p.y = float(Arena.FLOOR_Y)


def collide_players(a, b):
    """Separa a dos jugadores sin que se atraviesen ni queden trabados."""
    if a.on_head == b.idx or b.on_head == a.idx:
        return                          # uno está parado sobre el otro
    for _ in range(2):
        for ca in a.circles():
            for cb in b.circles():
                dx, dy = cb[0] - ca[0], cb[1] - ca[1]
                rr = ca[2] + cb[2]
                d2 = dx * dx + dy * dy
                if d2 >= rr * rr:
                    continue
                d = math.sqrt(d2)
                if d > EPSILON:
                    nx, ny = dx / d, dy / d
                else:
                    nx, ny = (1.0, 0.0)
                if abs(ny) > STACK_NORMAL:
                    # uno cae sobre la cabeza del otro: sesgo lateral determinista
                    # para que se deslice en vez de quedar apoyado
                    side = sign(b.x - a.x) or (1 if a.idx == 0 else -1)
                    nx += STACK_SLIDE_BIAS * side
                    n = math.hypot(nx, ny)
                    nx, ny = nx / n, ny / n
                pen = rr - d
                wa = 0.5
                if a.on_ground and ny < -SUPPORT_NORMAL:
                    wa = 0.0   # a está abajo y apoyado: se mueve b
                elif b.on_ground and ny > SUPPORT_NORMAL:
                    wa = 1.0
                a.x -= nx * pen * wa
                a.y -= ny * pen * wa
                b.x += nx * pen * (1 - wa)
                b.y += ny * pen * (1 - wa)
                rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
                if rel < 0:
                    a.vx += nx * rel * 0.5
                    a.vy += ny * rel * 0.5
                    b.vx -= nx * rel * 0.5
                    b.vy -= ny * rel * 0.5
        clamp_player_walls(a)
        clamp_player_walls(b)


# ---------------------------------------------------------------------------
# Pelota contra mundo y jugadores
# ---------------------------------------------------------------------------
def _collide_ball_world(ball, goals, touches):
    r = ball.radius
    if ball.y + r > Arena.FLOOR_Y:
        ball.y = Arena.FLOOR_Y - r
        if ball.vy > 0:
            impact = ball.vy
            ball.vy = -ball.vy * ball.restitution(BS.RESTITUTION_FLOOR)
            if abs(ball.vy) < BS.REST_SPEED:
                ball.vy = 0.0
            touches.append(("floor", impact))
    if ball.y - r < Arena.CEILING_Y:
        ball.y = Arena.CEILING_Y + r
        if ball.vy < 0:
            touches.append(("wall", -ball.vy))
            ball.vy = -ball.vy * ball.restitution(BS.RESTITUTION_WALL)
    if ball.x - r < 0:
        ball.x = r
        if ball.vx < 0:
            touches.append(("wall", -ball.vx))
            ball.vx = -ball.vx * ball.restitution(BS.RESTITUTION_WALL)
    elif ball.x + r > Arena.WIDTH:
        ball.x = Arena.WIDTH - r
        if ball.vx > 0:
            touches.append(("wall", ball.vx))
            ball.vx = -ball.vx * ball.restitution(BS.RESTITUTION_WALL)
    for g in goals:
        ax, ay, bx, _ = g.bar_segment()
        px = clamp(ball.x, ax, bx)
        dx, dy = ball.x - px, ball.y - ay
        rr = r + HALF_BAR
        d2 = dx * dx + dy * dy
        if d2 >= rr * rr:
            continue
        d = math.sqrt(d2)
        if d > EPSILON:
            nx, ny = dx / d, dy / d
        else:
            nx, ny = 0.0, -1.0
        ball.x = px + nx * rr
        ball.y = ay + ny * rr
        vn = ball.vx * nx + ball.vy * ny
        if vn < 0:
            e = ball.restitution(BS.RESTITUTION_BAR)
            ball.vx -= (1 + e) * vn * nx
            ball.vy -= (1 + e) * vn * ny
            touches.append(("bar", -vn))


def _collide_ball_circle(ball, cx, cy, cr, pvx, pvy, e, boost):
    """Devuelve None si no hay contacto, o la velocidad de impacto (>= 0)."""
    dx, dy = ball.x - cx, ball.y - cy
    rr = ball.radius + cr
    d2 = dx * dx + dy * dy
    if d2 >= rr * rr:
        return None
    d = math.sqrt(d2)
    if d > EPSILON:
        nx, ny = dx / d, dy / d
    else:
        nx, ny = 0.0, -1.0
    ball.x = cx + nx * rr
    ball.y = cy + ny * rr
    rvx, rvy = ball.vx - pvx, ball.vy - pvy
    vn = rvx * nx + rvy * ny
    if vn >= 0:
        return 0.0
    ball.vx -= (1 + e) * vn * nx
    ball.vy -= (1 + e) * vn * ny
    if boost and (pvx * nx + pvy * ny) > HEADER_MIN_APPROACH:
        ball.vx += nx * boost
        ball.vy += ny * boost
    return -vn


def step_ball(ball, players, goals, dt, contacts, touches):
    """Avanza la pelota un paso fijo, subdividido según su velocidad.

    contacts recibe (idx_jugador, tipo, impacto) para decidir el último toque.
    touches recibe (tipo, impacto) de rebotes contra el mundo (sólo sonido).
    """
    ball.vy += BS.GRAVITY * dt
    drag = math.exp(-BS.AIR_DRAG * dt)
    ball.vx *= drag
    ball.vy *= drag
    ball.clamp_speed()
    speed = math.hypot(ball.vx, ball.vy)
    max_move = max(1.0, BS.SUBSTEP_FRACTION * ball.radius)
    n = max(1, min(MAX_BALL_SUBSTEPS, int(math.ceil(speed * dt / max_move))))
    h = dt / n
    for _ in range(n):
        ball.x += ball.vx * h
        ball.y += ball.vy * h
        _collide_ball_world(ball, goals, touches)
        for p in players:
            if p.ball_ignore > 0:
                continue                 # la pelota recién pateada sale sin rozar a su pateador
            hx, hy, hr = p.head()
            imp = _collide_ball_circle(ball, hx, hy, hr, p.vx, p.vy,
                                       PS.HEAD_RESTITUTION, PS.HEADER_BOOST)
            if imp is not None:
                contacts.append((p.idx, "head", imp))
            bx, by, br = p.body()
            imp = _collide_ball_circle(ball, bx, by, br, p.vx, p.vy,
                                       PS.BODY_RESTITUTION, 0.0)
            if imp is not None:
                contacts.append((p.idx, "body", imp))
        # el mundo tiene prioridad: la pelota nunca queda dentro de un poste
        _collide_ball_world(ball, goals, touches)
        _unsqueeze(ball, players)
    if ball.on_floor:
        ball.vx *= math.exp(-BS.FLOOR_FRICTION * dt)
    for g in goals:
        # apoyada sobre el travesaño: leve pendiente hacia la cancha, para que
        # nunca quede inalcanzable arriba del arco
        ax, ay, bx, _ = g.bar_segment()
        resting = abs(ball.y + ball.radius - (ay - HALF_BAR)) < BAR_REST_TOLERANCE
        if ax <= ball.x <= bx and resting and abs(ball.vy) < BAR_REST_MAX_VY:
            ball.vx += g.toward_field * BS.BAR_ROLL_ACCEL * dt
    ball.clamp_speed()
    ball.angle -= math.degrees(ball.vx * dt / max(ball.radius, 1.0))


def _unsqueeze(ball, players):
    """Si la pelota quedó apretada entre un jugador y el mundo, cede el jugador."""
    for p in players:
        if p.ball_ignore > 0:
            continue
        for cx, cy, cr in p.circles():
            dx, dy = cx - ball.x, cy - ball.y
            rr = ball.radius + cr
            d2 = dx * dx + dy * dy
            if d2 < (rr - 0.5) ** 2:
                d = math.sqrt(d2)
                push = sign(dx) or (1 if p.idx == 1 else -1)
                p.x += push * min(rr - d, MAX_PUSH_PER_STEP)
                clamp_player_walls(p)


def apply_kick(ball, p):
    """Golpe de la patada: dirección según la orientación del jugador."""
    fx, fy, _ = p.foot()
    dy = ball.y - fy
    lift = PS.KICK_LIFT + clamp(-dy / KICK_HEIGHT_SCALE, KICK_LIFT_MIN_CHANGE, KICK_LIFT_MAX_CHANGE)
    nx, ny = float(p.facing), -lift
    n = math.hypot(nx, ny)
    vx = nx / n * PS.KICK_POWER + p.vx * PS.KICK_CARRY
    vy = ny / n * PS.KICK_POWER + min(p.vy, 0.0) * PS.KICK_CARRY
    return vx, vy


def ball_hits_foot(ball, p):
    fx, fy, fr = p.foot()
    dx, dy = ball.x - fx, ball.y - fy
    rr = ball.radius + fr
    return dx * dx + dy * dy < rr * rr
