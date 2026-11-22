"""Powers: pickups, timed effects and bombs.

Implemented rules (see also README):
* At most one pickup at a time; new ones wait for SPAWN_INTERVAL seconds of
  effective play. A pickup disappears after 8 s if the ball does not touch
  it. Half of them appear on the floor, half at lob height.
* Receiver = last player who touched the ball. Without a last touch,
  personal powers are NOT consumed (the ball goes through); global ones are.
* Effects are stored in a dictionary keyed by (target, property):
    - repeating the same effect renews its duration (same key, no stacking);
    - an opposite effect on the same property and target replaces it;
    - different properties coexist.
* Modifiers are ALWAYS recomputed from the base values, so no accumulated
  errors remain when an effect expires.
* Everything counts down only during effective play: pauses, countdowns and
  celebrations freeze timers and fuses.
* The fire power of the ball burns the first player who touches it: the
  ball goes out and that player stays BURN_DURATION s without moving.
"""
import math

from fdc import config
from fdc import protocol
from fdc.sim import physics

RULES = config.PowerRules
ARENA = config.Arena
FIRE_PROP = "fire"          # property of the burning ball
BURN_PROP = "burned"        # property of the player who touched the fire
CONFUSION_PROP = "confusion"
# Effect properties that multiply a value of the player, and its attribute.
MULTIPLIERS = (("speed", "speed_mult"), ("jump", "jump_mult"),
               ("size", "target_scale"))
# px of free space between a new pickup and a player's body.
PLAYER_CLEARANCE = 10
GOAL_CLEARANCE = 20         # px of free space between a pickup and a goal
FLOOR_CLEARANCE = 10        # px of free space between a pickup and the floor
# px of free space between a pickup and the ceiling (below the scoreboard).
CEILING_CLEARANCE = 60
BOMB_HEIGHT = 20            # px above the floor where a bomb rests
# The blast always pushes upwards at least this share.
BLAST_MIN_UPWARD = 0.35
# Test mode: the pickup appears this far (horizontally) from the ball...
TEST_SPAWN_OFFSET_X = 180
# ...and at this height above the floor (reachable with a kick).
TEST_SPAWN_HEIGHT = 200
SPAWN_RETRY = 0.5           # s: no free spot found, retry soon


class Effect:
  """A timed power effect on one target."""
  __slots__ = ("power", "target", "prop", "value", "left", "duration")

  def __init__(self, power, target, prop, value, duration):
    self.power = power
    self.target = target
    self.prop = prop
    self.value = value
    self.left = duration
    self.duration = duration


class Pickup:
  """A power on the pitch, waiting for the ball."""
  __slots__ = ("id", "power", "x", "y", "ttl")

  def __init__(self, pid, power, x, y):
    self.id = pid
    self.power = power
    self.x = x
    self.y = y
    self.ttl = RULES.PICKUP_TTL


class Bomb:
  """A bomb with its fuse burning."""
  __slots__ = ("id", "x", "y", "fuse")

  def __init__(self, bid, x, y):
    self.id = bid
    self.x = x
    self.y = y
    self.fuse = RULES.BOMB_WARNING


def resolve_targets(pdef, receiver):
  """Concrete targets ("p0", "goal1", "ball"...) of a power."""
  if pdef.target == "self":
    return [f"p{receiver}"]
  if pdef.target == "rival":
    return [f"p{1 - receiver}"]
  if pdef.target == "rival_goal":
    # The goal the rival defends: where the receiver attacks.
    return [f"goal{1 - receiver}"]
  if pdef.target == "ball":
    return ["ball"]
  return []


class PowerManager:
  """Pickups, active effects and bombs of one match."""

  def __init__(self, rng):
    self.rng = rng
    self._next_id = 1
    self.clear()

  def _new_id(self):
    self._next_id += 1
    return self._next_id

  def clear(self):
    """Clears effects, pickup and bombs (after a goal or a restart)."""
    self.effects = {}
    self.pickup = None
    self.bombs = []
    self.spawn_timer = RULES.SPAWN_INTERVAL

  # ------------------------------------------------------------- timers
  def update(self, dt, match, events):
    """Called only during effective play."""
    self._expire_effects(dt, events)
    self._refresh_burns(match)
    self._age_pickup(dt, events)
    self.spawn_timer -= dt
    if self.spawn_timer <= 0 and self.pickup is None:
      self._spawn(match, events)
    for bomb in list(self.bombs):
      bomb.fuse -= dt
      if bomb.fuse <= 0:
        self.bombs.remove(bomb)
        self._explode(bomb, match, events)

  def _expire_effects(self, dt, events):
    for key, effect in list(self.effects.items()):
      effect.left -= dt
      if effect.left <= 0:
        del self.effects[key]
        events.append((protocol.EV_POWER_EXPIRED,
                       {"power": effect.power,
                        "target": effect.target}))

  def _refresh_burns(self, match):
    """Seconds left of each burn, for the screens (the state has it)."""
    for player in match.players:
      effect = self.effects.get((f"p{player.idx}", BURN_PROP))
      if effect is not None:
        player.burned_left = effect.left

  def _age_pickup(self, dt, events):
    if self.pickup is None:
      return
    self.pickup.ttl -= dt
    if self.pickup.ttl <= 0:
      pickup = self.pickup
      self.pickup = None
      events.append((protocol.EV_PICKUP_EXPIRED, {
          "power": pickup.power, "x": pickup.x, "y": pickup.y}))

  def _spawn(self, match, events):
    pos = self._find_spawn(match)
    if pos is None:
      self.spawn_timer = SPAWN_RETRY
    else:
      power = self.rng.choice(config.POWER_IDS)
      self.place_pickup(power, pos, events)
      self.spawn_timer = RULES.SPAWN_INTERVAL

  def place_pickup(self, power, pos, events):
    self.pickup = Pickup(self._new_id(), power, pos[0], pos[1])
    events.append((protocol.EV_POWER_SPAWN, {
        "pickup": self.pickup.id, "power": power, "x": pos[0],
        "y": pos[1]}))

  def _find_spawn(self, match):
    ball = match.ball
    for _ in range(RULES.SPAWN_TRIES):
      x = self.rng.uniform(*RULES.SPAWN_X)
      y = spawn_height(self.rng)
      if math.hypot(x - ball.x, y - ball.y) < RULES.SPAWN_MIN_BALL_DIST:
        continue
      if position_is_free(x, y, match) and _clear_of_players(x, y,
                                                             match):
        return x, y
    return None

  # --------------------------------------------------------- activation
  def check_pickup(self, match, events):
    pickup = self.pickup
    if pickup is None or not _ball_touches(match.ball, pickup):
      return
    pdef = config.POWERS_BY_ID[pickup.power]
    if (pdef.target in config.PERSONAL_TARGETS
            and match.last_touch is None):
      return  # personal power without a receiver: not consumed
    self.pickup = None
    self.activate(pickup.power, match.last_touch, match, pickup.x,
                  pickup.y, events)

  def activate(self, power, receiver, match, x, y, events):
    """Applies a power to its targets. Returns False if it had none."""
    pdef = config.POWERS_BY_ID[power]
    if pdef.target in config.PERSONAL_TARGETS and receiver is None:
      return False
    targets = resolve_targets(pdef, receiver)
    self._add_effects(pdef, targets)
    if pdef.prop == "bomb":
      self._arm_bomb(events)
    events.append((protocol.EV_POWER, {
        "power": power, "receptor": receiver, "targets": targets,
        "x": x, "y": y}))
    self.apply_modifiers(match)
    return True

  def _add_effects(self, pdef, targets):
    for target in targets:
      # Same key -> renews or replaces (never multiplies).
      self.effects[(target, pdef.prop)] = Effect(
          pdef.id, target, pdef.prop, pdef.value, pdef.duration)

  def _arm_bomb(self, events):
    bomb_x = self.rng.uniform(*RULES.BOMB_ZONE_X)
    bomb = Bomb(self._new_id(), bomb_x, ARENA.FLOOR_Y - BOMB_HEIGHT)
    self.bombs.append(bomb)
    events.append((protocol.EV_BOMB_ARMED,
                   {"bomb": bomb.id, "x": bomb.x, "y": bomb.y}))

  def check_burn(self, match, user, events):
    """The fire ball burns the first player who touches it."""
    effect = self.effects.pop(("ball", FIRE_PROP), None)
    if effect is None:
      return
    self._fire_out(effect, events)
    key = f"p{user}"
    self.effects[(key, BURN_PROP)] = Effect(
        effect.power, key, BURN_PROP, None, RULES.BURN_DURATION)
    events.append((protocol.EV_BURN, {"player": user,
                                      "seconds": RULES.BURN_DURATION}))
    self.apply_modifiers(match)

  def _fire_out(self, effect, events):
    """The ball stops burning (it was touched or its time is over)."""
    events.append((protocol.EV_POWER_EXPIRED,
                   {"power": effect.power, "target": effect.target}))

  def apply_modifiers(self, match):
    """Recomputes everything from the base values."""
    for player in match.players:
      self._modify_player(player)
    for goal in match.goals:
      effect = self.effects.get((f"goal{goal.side}", "goal_height"))
      goal.set_multiplier(effect.value if effect else 1.0)
    effect = self.effects.get(("ball", "radius"))
    match.ball.set_radius_multiplier(effect.value if effect else 1.0)
    effect = self.effects.get(("ball", "bounce"))
    match.ball.bounce_mult = effect.value if effect else 1.0

  def _modify_player(self, player):
    """Base values plus the effects the match keeps on the player."""
    effects = self.effects
    key = f"p{player.idx}"
    player.clear_modifiers()
    self._set_multipliers(player, key)
    player.frozen = (key, "frozen") in effects
    player.no_kick = (key, "no_kick") in effects
    player.confused = (key, CONFUSION_PROP) in effects
    self._set_burn(player, effects.get((key, BURN_PROP)))

  def _set_multipliers(self, player, key):
    for prop, attr in MULTIPLIERS:
      effect = self.effects.get((key, prop))
      if effect is not None:
        setattr(player, attr, effect.value)

  @staticmethod
  def _set_burn(player, effect):
    """The burn of the fire power: no walk, no jump and no kick."""
    player.burned = effect is not None
    if effect is not None:
      player.burned_left = effect.left
    if (player.frozen or player.burned) and player.kick_t >= 0:
      player.kick_t = -1.0

  # -------------------------------------------------------------- bombs
  def _explode(self, bomb, match, events):
    """Pushes ball and players by distance. Keeps the last touch."""
    ball = match.ball
    push = _blast(bomb, ball.x, ball.y, RULES.BOMB_BALL_IMPULSE)
    if push:
      ball.vx += push[0]
      ball.vy += push[1]
      ball.clamp_speed()
    for player in match.players:
      _blast_player(bomb, player)
    events.append((protocol.EV_BOMB_EXPLODE, {
        "bomb": bomb.id, "x": bomb.x, "y": bomb.y,
        "radius": RULES.BOMB_BLAST_RADIUS}))

  # -------------------------------------------------------------- state
  def snapshot(self):
    """Pickup, bombs and effects for the match state."""
    pickup = self.pickup
    return {
        "pickup": None if pickup is None else {
            "id": pickup.id, "power": pickup.power, "x": pickup.x,
            "y": pickup.y, "ttl": pickup.ttl,
            "ttl_max": RULES.PICKUP_TTL},
        "bombs": [{"id": b.id, "x": b.x, "y": b.y, "fuse": b.fuse,
                   "fuse_max": RULES.BOMB_WARNING} for b in self.bombs],
        "effects": [{"power": e.power, "prop": e.prop, "target": e.target,
                     "left": e.left, "dur": e.duration}
                    for e in sorted(self.effects.values(),
                                    key=lambda e: (e.target, e.prop))],
    }


def spawn_height(rng):
  """Height of a new pickup: half on the floor, half in the air."""
  if rng.random() < RULES.SPAWN_FLOOR_SHARE:
    return RULES.SPAWN_FLOOR_Y
  return rng.uniform(*RULES.SPAWN_Y)


def position_is_free(x, y, match):
  """Away from goals, crossbars, walls and floor."""
  radius = RULES.PICKUP_RADIUS
  if (x - radius < ARENA.GOAL_DEPTH + GOAL_CLEARANCE
          or x + radius > ARENA.WIDTH - ARENA.GOAL_DEPTH - GOAL_CLEARANCE):
    return False
  if (y + radius > ARENA.FLOOR_Y - FLOOR_CLEARANCE
          or y - radius < ARENA.CEILING_Y + CEILING_CLEARANCE):
    return False
  for goal in match.goals:
    left, top, right, bottom = goal.bar_rect()
    if (left - radius < x < right + radius
            and top - radius < y < bottom + radius):
      return False
  return True


def _clear_of_players(x, y, match):
  """True if (x, y) leaves room for a pickup next to every player."""
  for player in match.players:
    for cx, cy, cr in player.circles():
      if (math.hypot(x - cx, y - cy)
              < cr + RULES.PICKUP_RADIUS + PLAYER_CLEARANCE):
        return False
  return True


def _blast(bomb, cx, cy, strength):
  """(push x, push y, falloff) of a blast on a point, or None if far."""
  dx, dy = cx - bomb.x, cy - bomb.y
  distance = math.hypot(dx, dy)
  if distance >= RULES.BOMB_BLAST_RADIUS:
    return None
  falloff = 1.0 - distance / RULES.BOMB_BLAST_RADIUS
  if distance > physics.EPSILON:
    nx, ny = dx / distance, dy / distance
  else:
    nx, ny = 0.0, -1.0
  ny = min(ny, -BLAST_MIN_UPWARD)     # always pushes upwards a bit
  length = math.hypot(nx, ny)
  return (nx / length * strength * falloff,
          ny / length * strength * falloff, falloff)


def _blast_player(bomb, player):
  push = _blast(bomb, player.x, player.y - player.height() / 2,
                RULES.BOMB_PLAYER_IMPULSE)
  if push:
    player.vx += push[0]
    player.vy += push[1]
    player.on_ground = False
    player.knockback = RULES.BOMB_KNOCKBACK * push[2]


def _ball_touches(ball, pickup):
  return (math.hypot(ball.x - pickup.x, ball.y - pickup.y)
          <= ball.radius + RULES.PICKUP_RADIUS)


def default_test_spawn(match):
  """Fixed, reachable position for the test mode."""
  ball_x = match.ball.x
  if ball_x < ARENA.WIDTH / 2:
    x = ball_x + TEST_SPAWN_OFFSET_X
  else:
    x = ball_x - TEST_SPAWN_OFFSET_X
  x = physics.clamp(x, *RULES.SPAWN_X)
  return x, ARENA.FLOOR_Y - TEST_SPAWN_HEIGHT - config.BallSpec.RADIUS
