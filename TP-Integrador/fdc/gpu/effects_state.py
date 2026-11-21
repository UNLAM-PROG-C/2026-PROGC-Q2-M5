"""Derived effects of the moment: what the chain draws, from the state (F3).

`derive` is a pure function: the same match state, the same viewer and the
same night setting always give the same `FxParams`.
No pygame and no numpy here, so the rules are tested without a window.

Perspective: `viewer` is 0 or 1 for a single player (tournament, online)
and None on a shared screen, where every power that hits one player is
drawn on top of that player only.
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


class FxParams:
  """Everything the chain needs to know of one frame (see spec §5)."""

  __slots__ = ("ice", "blackout", "confusion", "fire", "night", "burned")

  def __init__(self, night=False):
    self.ice = 0.0            # 0-1: ice tint and bright edges
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
  for effect in state.get("effects") or ():
    _add_power(params, effect, players, viewer)
  params.fire = _fire(params.fire, state)
  return params


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
    _set_ice(params, strength if _seen_by(viewer, index) else 0.0)
  elif prop == BLACKOUT_PROP and _seen_by(viewer, index):
    params.blackout = _blackout_points(players, index, viewer)
  elif prop == CONFUSION_PROP and _seen_by(viewer, index):
    params.confusion = strength
  elif prop == BURN_PROP:
    # Both players see the embers: the burnt player is on the pitch.
    params.burned = params.burned + (_feet(_player(players, index)),)


def _set_ice(params, strength):
  params.ice = max(params.ice, strength)


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
