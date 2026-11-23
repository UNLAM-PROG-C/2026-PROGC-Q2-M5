"""Derived effects of the moment: what the chain draws, from the state (F3).

`derive` is a pure function: the same match state, the same viewer and the
same night setting always give the same `FxParams`.
No pygame and no numpy here, so the rules are tested without a window.

Perspective: `viewer` is 0 or 1 for a single player (tournament, online)
and None on a shared screen, where every power that hits one player is
drawn on top of that player only. The confusion is the exception: the
twisted pitch is drawn for every viewer, while only the rival walks
backwards (the simulation does that).
"""
from fdc import config

G = config.Gpu
FULL = 1.0              # maximum strength of an effect
ICE_PROP = "frozen"     # the property of both freeze powers
BURN_PROP = "burned"    # the property of a player burnt by the fire power
BLACKOUT_PROP = "blackout"
CONFUSION_PROP = "confusion"
FIRE_PROP = "fire"
PLAYER_PREFIX = "p"     # effect target of a player: "p0", "p1"
ICE_W = 104            # px x player scale
ICE_EXTRA_H = 16       # px x scale above the normal player height
ICE_SINK = 4           # px that the base extends below the feet
ICE_GROW = 0.15        # s to grow the block from the feet


class FxParams:
  """Everything the chain needs to know of one frame (see spec §5)."""

  __slots__ = ("ice", "ice_boxes", "blackout", "confusion", "fire", "night",
               "burned")

  def __init__(self, night=False):
    self.ice = 0.0            # 0-1: ice tint and bright edges
    self.ice_boxes: tuple = ()  # (x0, y0, x1, y1) of frozen players
    self.blackout = ()        # points (x, y) that keep their light
    self.confusion = 0.0      # 0-1: inverted and rotated image
    self.fire = None          # (x, y, radius) of the hot air
    self.burned: tuple = ()   # points (x, y) of the burnt players
    self.night = night        # the local night mode is on

  def __eq__(self, other):
    return (isinstance(other, FxParams)
            and all(getattr(self, name) == getattr(other, name)
                    for name in self.__slots__))

  def __repr__(self):
    fields = ", ".join(f"{name}={getattr(self, name)!r}"
                       for name in self.__slots__)
    return f"FxParams({fields})"


def derive(state, viewer, night=False):
  """Effects of a frame from the state, viewer and night setting."""
  state = state or {}
  players = state.get("players") or ()
  params = FxParams(night=bool(night))
  effects = state.get("effects") or ()
  params.ice_boxes = _ice_boxes(players, effects)
  for effect in effects:
    _add_power(params, effect, players, viewer)
  params.fire = _fire(params.fire, state)
  return params


def _ice_boxes(players, effects):
  timers = {e.get("target"): e for e in effects if e.get("prop") == ICE_PROP}
  return tuple(ice_box(p, timers.get(f"p{i}"))
               for i, p in enumerate(players) if p and p.get("frozen"))


def ice_box(player, effect=None):
  """Bounds of the growing block, in logical pixels (right/bottom open)."""
  scale = player.get("scale", 1.0)
  width = _snap(ICE_W * scale)
  height = (config.PlayerSpec.HEIGHT + ICE_EXTRA_H) * scale
  growth = _ice_growth(effect)
  left = _snap(player["x"] - width / 2)
  bottom = _snap(player["y"] + ICE_SINK)
  return left, bottom - _snap(height * growth), left + width, bottom


def _ice_growth(effect):
  if effect is None:
    return FULL
  elapsed = effect.get("dur", 0.0) - effect.get("left", 0.0)
  return _fade(elapsed, ICE_GROW) if effect.get("dur") else FULL


def _snap(value):
  return int(value) // config.ART_PIXEL * config.ART_PIXEL


def _add_power(params, effect, players, viewer):
  """Applies one effect of the state to `params`."""
  prop = effect.get("prop")
  strength = _strength(effect)
  if strength <= 0:
    return
  if prop == FIRE_PROP:
    params.fire = True          # the place is filled from the ball
    return
  index = _target_index(effect.get("target"))
  if _player(players, index) is None:
    return
  _set_power(params, prop, strength, players, index, viewer)


def _set_power(params, prop, strength, players, index, viewer):
  """Parameter of one power, with the perspective of the viewer."""
  if prop == ICE_PROP:
    if viewer == index and players[index].get("frozen"):
      params.ice = max(params.ice, strength)
  elif prop == BLACKOUT_PROP and _seen_by(viewer, index):
    params.blackout = _blackout_points(players, index, viewer)
  elif prop == CONFUSION_PROP:
    # Both players see the twisted pitch: whoever took the power must
    # see its effect too, as on the shared screen of the presentation.
    params.confusion = strength
  elif prop == BURN_PROP:
    # Both players see the embers: the burnt player is on the pitch.
    params.burned = params.burned + (_feet(_player(players, index)),)



def _seen_by(viewer, index):
  """True if player `index` is the viewer (or the screen is shared)."""
  return viewer is None or viewer == index


def _blackout_points(players, index, viewer):
  """Points that keep their light: the affected player or every player."""
  if viewer is not None:
    return (_head(_player(players, index)),)
  return tuple(_head(player) for player in players if player)


def _fire(current, state):
  """Hot air around the ball while the fire power lasts."""
  if current is None:
    return None
  ball = state.get("ball") or {}
  x, y = float(ball.get("x") or 0.0), float(ball.get("y") or 0.0)
  return (x, y, G.FIRE_RADIUS)


def _strength(effect):
  """Fade in at the start and out at the end (0-1)."""
  duration = float(effect.get("dur") or 0.0)
  left = float(effect.get("left") or 0.0)
  if duration <= 0:
    return FULL
  up = _fade(duration - left, G.FADE_IN)
  down = _fade(left, G.FADE_OUT)
  return max(0.0, min(up, down))


def _fade(seconds, span):
  """0 before the span, 1 after it."""
  if span <= 0:
    return FULL
  return min(FULL, max(0.0, seconds / span))


def _target_index(target):
  """Player index of a "p0"/"p1" target; None for any other target."""
  if not isinstance(target, str) or not target.startswith(PLAYER_PREFIX):
    return None
  digits = target[len(PLAYER_PREFIX):]
  return int(digits) if digits.isdigit() else None


def _player(players, index):
  """The player dictionary at `index`, or None."""
  if index is None or index < 0 or index >= len(players):
    return None
  return players[index]


def _head(player):
  """Centre of the head: a bit above the feet."""
  return (float(player.get("x") or 0.0),
          float(player.get("y") or 0.0) - G.HEAD_ABOVE)


def _feet(player):
  """(x, y) of the feet of a player (where its burn starts)."""
  return (float(player.get("x") or 0.0), float(player.get("y") or 0.0))


def night_lights():
  """The six warm spotlights of the night mode: (x, y, radius, power)."""
  return tuple((G.NIGHT_FIRST_X + i * G.NIGHT_STEP_X, G.NIGHT_Y,
                G.NIGHT_RADIUS, G.NIGHT_POWER)
               for i in range(G.NIGHT_LIGHTS))


def light_array(points, radius, power):
  """Lights (x, y, radius, power) for the kernel, from (x, y) points."""
  return [(point[0], point[1], radius, power) for point in points]
