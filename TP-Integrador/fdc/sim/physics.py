"""Match physics: entities and collisions.

Decisions:
* Fixed step (config.PHYSICS_DT). The ball is also split into substeps so it
  never moves more than a fraction of its radius: it never goes through
  heads, bodies or crossbars even at top speed.
* Players are "kinematic" against the ball (they push it without slowing
  down); between them they separate with equal masses.
* Shape of a player: a head circle + a body circle for the ball and the
  other player; a box (AABB) for the floor, the walls and the crossbars.
* The crossbar is a horizontal capsule: its round tip is the post-crossbar
  corner. The back wall works as the back post.
"""
import math

from fdc import config

ARENA = config.Arena
BallSpec = config.BallSpec
PlayerSpec = config.PlayerSpec
# Radius of the crossbar capsule (half of its thickness).
HALF_BAR = ARENA.BAR_THICKNESS / 2.0

# --- internal physics constants (the "game" values are in config.py)
# Smallest distance to normalize a vector (avoids dividing by zero).
EPSILON = 1e-6
# px the crossbar goes on behind the wall: the ball cannot sneak by the tip.
BAR_BEYOND_WALL = 40.0
# Almost vertical collision between players (bigger |ny|): one falls on the
# other's head.
STACK_NORMAL = 0.8
# Side push added in that case so it slides and does not stay on top.
STACK_SLIDE_BIAS = 0.45
# From this vertical component, the one below (standing on the floor) does
# not move.
SUPPORT_NORMAL = 0.3
# px/s: the head must move to the ball at least this fast to add the header.
HEADER_MIN_APPROACH = 40.0
# Top ball substeps per physics step (even when it goes very fast).
MAX_BALL_SUBSTEPS = 16
# px: margin to consider the ball resting on the crossbar.
BAR_REST_TOLERANCE = 2.0
# px/s: faster than this (rising or falling) it is not resting.
BAR_REST_MAX_VY = 120.0
# px of height difference between ball and foot that change the lift by 1.
KICK_HEIGHT_SCALE = 60.0
# The kick lift drops at most this much (ball far below the foot)...
KICK_LIFT_MIN_CHANGE = -0.35
KICK_LIFT_MAX_CHANGE = 0.5      # ...and rises at most this much (above it)
# Share of their size the goal and the ball change with the size powers.
SIZE_POWER_CHANGE = 0.35
# Scale change of a player with the grow/shrink powers.
PLAYER_SCALE_CHANGE = 0.25
# px: tolerances when checking contacts with the floor and the heads.
FLOOR_TOLERANCE = 0.5
HEAD_LANDING_MARGIN = 2.0       # px: landing on a head from slightly below
HEAD_LANDING_DEPTH = 1.0        # px: sinking allowed into a head
RISING_MARGIN = 1.0             # px/s: rising faster than the one below
# Largest side push per step when a size or goal change makes an overlap.
MAX_PUSH_PER_STEP = 8.0
# How far from the centre of the head a player can stand on it.
HEAD_STAND_FRACTION = 0.8
SEPARATION_PASSES = 2           # passes to separate two players
UP = (0.0, -1.0)                # normal used when two centres coincide
RIGHT = (1.0, 0.0)              # same, for two players


def clamp(value, low, high):
    """`value` limited to [low, high]."""
    return low if value < low else high if value > high else value


def approach(value, target, delta):
    """Moves `value` towards `target` by at most `delta`."""
    if value < target:
        return min(value + delta, target)
    return max(value - delta, target)


def sign(value):
    return (value > 0) - (value < 0)


def _normal(dx, dy, distance, default):
    """Unit vector (dx, dy) / distance, or `default` if it is too short."""
    if distance > EPSILON:
        return dx / distance, dy / distance
    return default


# ---------------------------------------------------------------------------
# Goal
# ---------------------------------------------------------------------------
class Goal:
    """side 0 = left goal (P1 defends it); side 1 = right goal (P2)."""

    # px/s: the goal changes 35 % of its height (the power change) in
    # GOAL_TRANSITION s.
    RATE = (ARENA.GOAL_HEIGHT * SIZE_POWER_CHANGE
            / config.PowerRules.GOAL_TRANSITION)

    def __init__(self, side):
        self.side = side
        self.base_height = float(ARENA.GOAL_HEIGHT)
        self.reset()

    def reset(self):
        self.height = self.base_height
        self.target_height = self.base_height

    @property
    def mouth_x(self):
        if self.side == 0:
            return ARENA.GOAL_DEPTH
        return ARENA.WIDTH - ARENA.GOAL_DEPTH

    @property
    def toward_field(self):
        return 1 if self.side == 0 else -1

    def bar_y(self):
        """Height (y) of the axis of the crossbar capsule."""
        return ARENA.FLOOR_Y - self.height - HALF_BAR

    def bar_segment(self):
        """(x0, y, x1, y) of the crossbar axis."""
        y = self.bar_y()
        if self.side == 0:
            return (-BAR_BEYOND_WALL, y, float(self.mouth_x), y)
        return (float(self.mouth_x), y, ARENA.WIDTH + BAR_BEYOND_WALL, y)

    def bar_rect(self):
        """(left, top, right, bottom) box of the crossbar for players."""
        y = self.bar_y()
        if self.side == 0:
            return (0.0, y - HALF_BAR, self.mouth_x + HALF_BAR, y + HALF_BAR)
        return (self.mouth_x - HALF_BAR, y - HALF_BAR, float(ARENA.WIDTH),
                y + HALF_BAR)

    def set_multiplier(self, mult):
        self.target_height = clamp(self.base_height * mult,
                                   ARENA.GOAL_MIN_HEIGHT,
                                   ARENA.GOAL_MAX_HEIGHT)

    def update(self, dt):
        # Gradual change: the crossbar slides, it does not teleport.
        self.height = approach(self.height, self.target_height,
                               self.RATE * dt)

    def ball_inside(self, ball):
        """The ball crossed the goal line COMPLETELY below the crossbar."""
        if ball.y <= self.bar_y():
            return False
        if self.side == 0:
            return ball.x + ball.radius < self.mouth_x
        return ball.x - ball.radius > self.mouth_x


# ---------------------------------------------------------------------------
# Ball
# ---------------------------------------------------------------------------
class Ball:
    """Position, speed, size and spin of the ball."""

    # px/s: the radius changes 35 % (big or small ball) in SIZE_TRANSITION s.
    RADIUS_RATE = (BallSpec.RADIUS * SIZE_POWER_CHANGE
                   / config.PowerRules.SIZE_TRANSITION)

    def __init__(self):
        self.base_radius = float(BallSpec.RADIUS)
        self.bounce_mult = 1.0
        self.reset()

    def reset(self, x=BallSpec.SPAWN[0], y=BallSpec.SPAWN[1]):
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.radius = self.target_radius = self.base_radius
        self.angle = 0.0
        self.bounce_mult = 1.0

    def restitution(self, base):
        return min(base * self.bounce_mult, BallSpec.MAX_RESTITUTION)

    def set_radius_multiplier(self, mult):
        self.target_radius = self.base_radius * mult

    def update_size(self, dt):
        self.radius = approach(self.radius, self.target_radius,
                               self.RADIUS_RATE * dt)

    def clamp_speed(self):
        speed = math.hypot(self.vx, self.vy)
        if speed > BallSpec.MAX_SPEED:
            factor = BallSpec.MAX_SPEED / speed
            self.vx *= factor
            self.vy *= factor

    @property
    def on_floor(self):
        return self.y + self.radius >= ARENA.FLOOR_Y - FLOOR_TOLERANCE


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
class Player:
    """One player: position, speed, kick, size and power modifiers."""

    # 1/s: the scale changes 0.25 (grow or shrink) in SIZE_TRANSITION s.
    SCALE_RATE = PLAYER_SCALE_CHANGE / config.PowerRules.SIZE_TRANSITION

    def __init__(self, idx):
        self.idx = idx
        self.reset()

    def reset(self):
        self.x = float(PlayerSpec.SPAWN_X[self.idx])
        self.y = float(ARENA.FLOOR_Y)
        self.vx = self.vy = 0.0
        self.facing = 1 if self.idx == 0 else -1
        self.on_ground = True
        self.prev_y = self.y
        self._reset_actions()
        self.scale = self.target_scale = 1.0
        self.stride = 0.0           # distance walked (to animate the steps)
        self.knockback = 0.0
        self.celebrating = False
        self.on_head = None         # index of the player whose head it is on
        self.clear_modifiers()

    def _reset_actions(self):
        """Jump and kick timers and buffers."""
        self.coyote = self.jump_buffer = 0.0
        self.kick_t = -1.0          # time since the kick started (-1: none)
        self.kick_cooldown = self.kick_buffer = 0.0
        self.kick_hit = False       # a kick hits at most once
        self.ball_ignore = 0.0      # after kicking, the ball ignores it

    def clear_modifiers(self):
        self.speed_mult = 1.0
        self.jump_mult = 1.0
        self.frozen = False
        self.no_kick = False
        self.target_scale = 1.0

    # --- geometry (always derived from scale: graphics and collisions agree)
    def head(self):
        scale = self.scale
        return (self.x, self.y - PlayerSpec.HEAD_OFFSET_Y * scale,
                PlayerSpec.HEAD_RADIUS * scale)

    def body(self):
        scale = self.scale
        return (self.x, self.y - PlayerSpec.BODY_OFFSET_Y * scale,
                PlayerSpec.BODY_RADIUS * scale)

    def circles(self):
        return (self.head(), self.body())

    def half_width(self):
        return PlayerSpec.HALF_WIDTH * self.scale

    def height(self):
        return PlayerSpec.HEIGHT * self.scale

    def foot(self):
        scale = self.scale
        return (self.x + self.facing * PlayerSpec.KICK_REACH_X * scale,
                self.y - PlayerSpec.KICK_REACH_Y * scale,
                PlayerSpec.KICK_RADIUS * scale)

    def kick_active(self):
        low, high = PlayerSpec.KICK_ACTIVE
        return low <= self.kick_t <= high

    def kick_progress(self):
        if self.kick_t >= 0:
            return self.kick_t / PlayerSpec.KICK_DURATION
        return -1.0

    def update_size(self, dt):
        self.scale = approach(self.scale, self.target_scale,
                              self.SCALE_RATE * dt)


# ---------------------------------------------------------------------------
# Player control and movement
# ---------------------------------------------------------------------------
def control_player(p, dt, move_dir, jump_pressed, kick_pressed, out_events):
    """Applies the player's intention. out_events gets (kind, idx) tuples."""
    _buffer_presses(p, jump_pressed, kick_pressed)
    can_act = not p.frozen
    if not can_act:
        # Frozen: no voluntary actions (gravity and collisions go on).
        move_dir = 0
        p.jump_buffer = 0.0
        if p.kick_t >= 0:
            p.kick_t = -1.0
    _walk(p, dt, move_dir)
    _jump(p, dt, can_act)
    _kick(p, dt, can_act, out_events)


def _buffer_presses(p, jump_pressed, kick_pressed):
    """A press is remembered for a moment (it counts a bit early)."""
    if jump_pressed:
        p.jump_buffer = PlayerSpec.JUMP_BUFFER
    if kick_pressed:
        p.kick_buffer = PlayerSpec.KICK_BUFFER


def _walk(p, dt, move_dir):
    target = move_dir * PlayerSpec.MOVE_SPEED * p.speed_mult
    if move_dir and PlayerSpec.FACE_MOVEMENT:
        p.facing = move_dir
    if p.on_ground:
        rate = (PlayerSpec.GROUND_ACCEL if target and p.vx * target >= 0
                else PlayerSpec.GROUND_DECEL)
    else:
        rate = PlayerSpec.AIR_ACCEL if target else PlayerSpec.AIR_DECEL
    if p.knockback > 0:
        rate *= PlayerSpec.KNOCKBACK_CONTROL
        p.knockback = max(0.0, p.knockback - dt)
    p.vx = approach(p.vx, target, rate * dt)


def _jump(p, dt, can_act):
    """Jump: only from the ground (with a small margin), never double."""
    if p.on_ground:
        p.coyote = PlayerSpec.COYOTE_TIME
    else:
        p.coyote = max(0.0, p.coyote - dt)
    if can_act and p.jump_buffer > 0 and (p.on_ground or p.coyote > 0):
        # From the rival's head the jump is a bit higher (reaches the bar).
        boost = PlayerSpec.HEAD_JUMP_BOOST if p.on_head is not None else 1.0
        p.vy = -PlayerSpec.JUMP_SPEED * p.jump_mult * boost
        p.on_ground = False
        p.coyote = 0.0
        p.jump_buffer = 0.0
    p.jump_buffer = max(0.0, p.jump_buffer - dt)


def _kick(p, dt, can_act, out_events):
    """Kick: one per press, with a recovery time."""
    _kick_timers(p, dt)
    if p.kick_buffer > 0 and p.kick_t < 0 and p.kick_cooldown <= 0:
        p.kick_buffer = 0.0
        if can_act and not p.no_kick:
            p.kick_t = 0.0
            p.kick_hit = False
            p.kick_cooldown = PlayerSpec.KICK_COOLDOWN
            out_events.append(("kick", p.idx))
        else:
            out_events.append(("kick_blocked", p.idx))
    p.kick_buffer = max(0.0, p.kick_buffer - dt)


def _kick_timers(p, dt):
    if p.kick_t >= 0:
        p.kick_t += dt
        if p.kick_t > PlayerSpec.KICK_DURATION:
            p.kick_t = -1.0
    p.kick_cooldown = max(0.0, p.kick_cooldown - dt)
    p.ball_ignore = max(0.0, p.ball_ignore - dt)


def integrate_player(p, dt, goals):
    """Moves a player one step: gravity, floor, crossbars and walls."""
    p.vy = min(p.vy + PlayerSpec.GRAVITY * dt, PlayerSpec.MAX_FALL_SPEED)
    p.prev_y = p.y
    prev_bottom = p.y
    prev_top = p.y - p.height()
    p.x += p.vx * dt
    p.y += p.vy * dt
    _land_on_floor(p)
    for goal in goals:
        _resolve_player_bar(p, goal, prev_bottom, prev_top)
    clamp_player_walls(p)
    if p.on_ground:
        p.stride += abs(p.vx) * dt


def _land_on_floor(p):
    p.on_ground = False
    if p.y >= ARENA.FLOOR_Y:
        p.y = float(ARENA.FLOOR_Y)
        if p.vy > 0:
            p.vy = 0.0
        p.on_ground = True


def _head_surface(low, x):
    """Height (y) of the top of the head of `low` at position x."""
    hx, hy, hr = low.head()
    dx = x - hx
    if abs(dx) > hr * HEAD_STAND_FRACTION:
        return None
    return hy - math.sqrt(hr * hr - dx * dx)


def land_on_heads(players):
    """The other player's head works as a floor: a player can land standing
    on it and jump from there. It does not "carry" it: if the one below
    moves, or the one on top walks to the edge, the one on top falls (nobody
    gets stuck or sits forever on the rival)."""
    for top in players:
        low = players[1 - top.idx]
        was_on = top.on_head == low.idx
        top.on_head = None
        on_floor = top.y >= ARENA.FLOOR_Y - FLOOR_TOLERANCE
        if on_floor or top.vy < low.vy - RISING_MARGIN:
            continue                    # on the floor, or rising (just jumped)
        _stand_on_head(top, low, was_on)


def _stand_on_head(top, low, was_on):
    surface = _head_surface(low, top.x)
    if surface is None:
        return
    landing = was_on or top.prev_y <= surface + HEAD_LANDING_MARGIN
    if landing and top.y >= surface - HEAD_LANDING_DEPTH:
        top.y = surface
        top.vy = low.vy
        top.on_ground = True
        top.on_head = low.idx
        clamp_player_walls(top)


def _resolve_player_bar(p, goal, prev_bottom, prev_top):
    left, top, right, bottom = goal.bar_rect()
    half_width, height = p.half_width(), p.height()
    if not _overlaps_bar(p, (left, top, right, bottom), half_width, height):
        return
    if not _bar_top_or_bottom(p, top, bottom, prev_bottom, prev_top):
        _push_out_of_bar(p, goal, left, right, half_width)


def _bar_top_or_bottom(p, top, bottom, prev_bottom, prev_top):
    """Landing on the crossbar or hitting it from below. True if so."""
    if prev_bottom <= top + FLOOR_TOLERANCE and p.vy >= 0:
        p.y = top                       # lands on the crossbar
        p.vy = 0.0
        p.on_ground = True
        return True
    if prev_top >= bottom - FLOOR_TOLERANCE and p.vy < 0:
        p.y = bottom + p.height()       # head hits the bottom of the bar
        p.vy = 0.0
        return True
    return False


def _overlaps_bar(p, rect, half_width, height):
    left, top, right, bottom = rect
    return not (p.x + half_width <= left or p.x - half_width >= right
                or p.y <= top or p.y - height >= bottom)


def _push_out_of_bar(p, goal, left, right, half_width):
    """Side overlap (or the goal/player changed size): the player is moved
    towards the pitch, gradually if the overlap is big."""
    d = goal.toward_field
    need = (right + half_width - p.x) if d > 0 else (p.x - (left - half_width))
    p.x += d * min(need, MAX_PUSH_PER_STEP)
    if p.vx * d < 0:
        p.vx = 0.0


def clamp_player_walls(p):
    """Keeps the player inside the side walls and above the floor."""
    half_width = p.half_width()
    if p.x - half_width < 0:
        p.x = half_width
        if p.vx < 0:
            p.vx = 0.0
    elif p.x + half_width > ARENA.WIDTH:
        p.x = ARENA.WIDTH - half_width
        if p.vx > 0:
            p.vx = 0.0
    if p.y > ARENA.FLOOR_Y:
        p.y = float(ARENA.FLOOR_Y)


def collide_players(a, b):
    """Separates two players so they never overlap or get stuck."""
    if a.on_head == b.idx or b.on_head == a.idx:
        return                          # one is standing on the other
    for _ in range(SEPARATION_PASSES):
        for circle_a in a.circles():
            for circle_b in b.circles():
                _separate(a, b, circle_a, circle_b)
        clamp_player_walls(a)
        clamp_player_walls(b)


def _separate(a, b, circle_a, circle_b):
    dx, dy = circle_b[0] - circle_a[0], circle_b[1] - circle_a[1]
    reach = circle_a[2] + circle_b[2]
    dist2 = dx * dx + dy * dy
    if dist2 >= reach * reach:
        return
    distance = math.sqrt(dist2)
    nx, ny = _normal(dx, dy, distance, RIGHT)
    if abs(ny) > STACK_NORMAL:
        nx, ny = _slide_off(a, b, nx, ny)
    _push_apart(a, b, nx, ny, reach - distance)
    _exchange_speed(a, b, nx, ny)


def _slide_off(a, b, nx, ny):
    """One falls on the other's head: deterministic side bias so it slides
    instead of staying on top."""
    side = sign(b.x - a.x) or (1 if a.idx == 0 else -1)
    nx += STACK_SLIDE_BIAS * side
    length = math.hypot(nx, ny)
    return nx / length, ny / length


def _push_apart(a, b, nx, ny, depth):
    weight = 0.5
    if a.on_ground and ny < -SUPPORT_NORMAL:
        weight = 0.0   # a is below and supported: b moves
    elif b.on_ground and ny > SUPPORT_NORMAL:
        weight = 1.0
    a.x -= nx * depth * weight
    a.y -= ny * depth * weight
    b.x += nx * depth * (1 - weight)
    b.y += ny * depth * (1 - weight)


def _exchange_speed(a, b, nx, ny):
    rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
    if rel < 0:
        a.vx += nx * rel * 0.5
        a.vy += ny * rel * 0.5
        b.vx -= nx * rel * 0.5
        b.vy -= ny * rel * 0.5


# ---------------------------------------------------------------------------
# Ball against the world and the players
# ---------------------------------------------------------------------------
def _collide_ball_world(ball, goals, touches):
    _ball_floor(ball, touches)
    _ball_ceiling(ball, touches)
    _ball_side_walls(ball, touches)
    for goal in goals:
        _ball_crossbar(ball, goal, touches)


def _ball_floor(ball, touches):
    if ball.y + ball.radius > ARENA.FLOOR_Y:
        ball.y = ARENA.FLOOR_Y - ball.radius
        if ball.vy > 0:
            impact = ball.vy
            ball.vy = -ball.vy * ball.restitution(BallSpec.RESTITUTION_FLOOR)
            if abs(ball.vy) < BallSpec.REST_SPEED:
                ball.vy = 0.0
            touches.append(("floor", impact))


def _ball_ceiling(ball, touches):
    radius = ball.radius
    if ball.y - radius < ARENA.CEILING_Y:
        ball.y = ARENA.CEILING_Y + radius
        if ball.vy < 0:
            touches.append(("wall", -ball.vy))
            ball.vy = -ball.vy * ball.restitution(BallSpec.RESTITUTION_WALL)


def _ball_side_walls(ball, touches):
    radius = ball.radius
    if ball.x - radius < 0:
        ball.x = radius
        if ball.vx < 0:
            touches.append(("wall", -ball.vx))
            ball.vx = -ball.vx * ball.restitution(BallSpec.RESTITUTION_WALL)
    elif ball.x + radius > ARENA.WIDTH:
        ball.x = ARENA.WIDTH - radius
        if ball.vx > 0:
            touches.append(("wall", ball.vx))
            ball.vx = -ball.vx * ball.restitution(BallSpec.RESTITUTION_WALL)


def _ball_crossbar(ball, goal, touches):
    ax, ay, bx, _ = goal.bar_segment()
    normal = _push_ball_out(ball, (clamp(ball.x, ax, bx), ay, HALF_BAR))
    if normal is None:
        return
    nx, ny = normal
    vn = ball.vx * nx + ball.vy * ny
    if vn < 0:
        _reflect(ball, vn, nx, ny,
                 ball.restitution(BallSpec.RESTITUTION_BAR))
        touches.append(("bar", -vn))


def _reflect(ball, vn, nx, ny, e):
    """Bounces the ball off a surface with normal (nx, ny)."""
    ball.vx -= (1 + e) * vn * nx
    ball.vy -= (1 + e) * vn * ny


def _collide_ball_circle(ball, circle, player, e, boost):
    """Returns None if there is no contact, or the impact speed (>= 0)."""
    normal = _push_ball_out(ball, circle)
    if normal is None:
        return None
    nx, ny = normal
    vn = (ball.vx - player.vx) * nx + (ball.vy - player.vy) * ny
    if vn >= 0:
        return 0.0
    _reflect(ball, vn, nx, ny, e)
    if boost and (player.vx * nx + player.vy * ny) > HEADER_MIN_APPROACH:
        ball.vx += nx * boost
        ball.vy += ny * boost
    return -vn


def _push_ball_out(ball, circle):
    """Moves the ball out of a circle; returns the normal or None."""
    cx, cy, cr = circle
    dx, dy = ball.x - cx, ball.y - cy
    reach = ball.radius + cr
    dist2 = dx * dx + dy * dy
    if dist2 >= reach * reach:
        return None
    nx, ny = _normal(dx, dy, math.sqrt(dist2), UP)
    ball.x = cx + nx * reach
    ball.y = cy + ny * reach
    return nx, ny


def step_ball(ball, players, goals, dt, contacts, touches):
    """Advances the ball one fixed step, split according to its speed.

    contacts gets (player idx, kind, impact) to decide the last touch.
    touches gets (kind, impact) of bounces against the world (sound only).
    """
    _ball_forces(ball, dt)
    count = _substep_count(ball, dt)
    for _ in range(count):
        _ball_substep(ball, players, goals, dt / count, contacts, touches)
    if ball.on_floor:
        ball.vx *= math.exp(-BallSpec.FLOOR_FRICTION * dt)
    for goal in goals:
        _roll_off_crossbar(ball, goal, dt)
    ball.clamp_speed()
    ball.angle -= math.degrees(ball.vx * dt / max(ball.radius, 1.0))


def _ball_forces(ball, dt):
    ball.vy += BallSpec.GRAVITY * dt
    drag = math.exp(-BallSpec.AIR_DRAG * dt)
    ball.vx *= drag
    ball.vy *= drag
    ball.clamp_speed()


def _substep_count(ball, dt):
    speed = math.hypot(ball.vx, ball.vy)
    max_move = max(1.0, BallSpec.SUBSTEP_FRACTION * ball.radius)
    steps = int(math.ceil(speed * dt / max_move))
    return max(1, min(MAX_BALL_SUBSTEPS, steps))


def _ball_substep(ball, players, goals, h, contacts, touches):
    ball.x += ball.vx * h
    ball.y += ball.vy * h
    _collide_ball_world(ball, goals, touches)
    for p in players:
        if p.ball_ignore <= 0:   # a ball just kicked does not touch its kicker
            _ball_on_player(ball, p, contacts)
    # The world has priority: the ball never stays inside a post.
    _collide_ball_world(ball, goals, touches)
    _unsqueeze(ball, players)


def _ball_on_player(ball, p, contacts):
    impact = _collide_ball_circle(ball, p.head(), p,
                                  PlayerSpec.HEAD_RESTITUTION,
                                  PlayerSpec.HEADER_BOOST)
    if impact is not None:
        contacts.append((p.idx, "head", impact))
    impact = _collide_ball_circle(ball, p.body(), p,
                                  PlayerSpec.BODY_RESTITUTION, 0.0)
    if impact is not None:
        contacts.append((p.idx, "body", impact))


def _roll_off_crossbar(ball, goal, dt):
    """Resting on the crossbar: a slight slope to the pitch, so it is never
    out of reach above the goal."""
    ax, ay, bx, _ = goal.bar_segment()
    resting = (abs(ball.y + ball.radius - (ay - HALF_BAR))
               < BAR_REST_TOLERANCE)
    if ax <= ball.x <= bx and resting and abs(ball.vy) < BAR_REST_MAX_VY:
        ball.vx += goal.toward_field * BallSpec.BAR_ROLL_ACCEL * dt


def _unsqueeze(ball, players):
    """If the ball got squeezed between a player and the world, the player
    gives way."""
    for p in players:
        if p.ball_ignore > 0:
            continue
        for cx, cy, cr in p.circles():
            dx, dy = cx - ball.x, cy - ball.y
            reach = ball.radius + cr
            dist2 = dx * dx + dy * dy
            if dist2 < (reach - 0.5) ** 2:
                push = sign(dx) or (1 if p.idx == 1 else -1)
                p.x += push * min(reach - math.sqrt(dist2), MAX_PUSH_PER_STEP)
                clamp_player_walls(p)


def apply_kick(ball, p):
    """Kick hit: its direction follows where the player faces."""
    _, foot_y, _ = p.foot()
    dy = ball.y - foot_y
    lift = PlayerSpec.KICK_LIFT + clamp(-dy / KICK_HEIGHT_SCALE,
                                         KICK_LIFT_MIN_CHANGE,
                                         KICK_LIFT_MAX_CHANGE)
    nx, ny = float(p.facing), -lift
    length = math.hypot(nx, ny)
    vx = nx / length * PlayerSpec.KICK_POWER + p.vx * PlayerSpec.KICK_CARRY
    vy = (ny / length * PlayerSpec.KICK_POWER
          + min(p.vy, 0.0) * PlayerSpec.KICK_CARRY)
    return vx, vy


def ball_hits_foot(ball, p):
    """True if the ball touches the foot circle of the player."""
    foot_x, foot_y, foot_r = p.foot()
    dx, dy = ball.x - foot_x, ball.y - foot_y
    reach = ball.radius + foot_r
    return dx * dx + dy * dy < reach * reach
