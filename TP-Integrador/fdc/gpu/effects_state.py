"""Derived effects of the moment: what the chain draws, from the state (F3).

`derive` is a pure function: the same match state, the same viewer and the
same clock always give the same `FxParams` (the event effects such as the
goal shock wave come in as a list of `EventFx`, also with their own clock).
No pygame and no numpy here, so the rules are tested without a window.

Perspective: `viewer` is 0 or 1 for a single player (tournament, online)
and None on a shared screen, where every power that hits one player is
drawn on top of that player only.
"""
import math

from fdc import config
from fdc import protocol

G = config.Gpu
FULL = 1.0              # maximum strength of an effect
NO_TIME = 0.0           # start of the clock in the tests
SHOCK_KIND = "shock"    # EventFx kind of the goal shock wave
SHOCK_EVENT = protocol.EV_GOAL
ICE_PROP = "frozen"     # the property of both freeze powers
BLACKOUT_PROP = "blackout"
CONFUSION_PROP = "confusion"
FIRE_PROP = "fire"
PLAYER_PREFIX = "p"     # effect target of a player: "p0", "p1"


class FxParams:
    """Everything the chain needs to know of one frame (see spec §5)."""

    __slots__ = ("ice", "blackout", "confusion", "fire", "night", "shock",
                 "trail", "crt", "var", "heat_channel")

    def __init__(self, night=False):
        self.ice = 0.0            # 0-1: ice tint and bright edges
        self.blackout = ()        # points (x, y) that keep their light
        self.confusion = 0.0      # 0-1: inverted and rotated image
        self.fire = None          # (x, y, radius) of the hot air
        self.night = night        # the local night mode is on
        self.shock = None         # (x, y, age) of the goal wave
        self.trail = 0.0          # 0-1: the ball leaves a trail
        self.crt = 0.0            # 0-1: CRT bands (F5)
        self.var = None           # replay frame (F5)
        self.heat_channel = None  # player of the heat map (F6)

    def __eq__(self, other):
        return (isinstance(other, FxParams)
                and all(getattr(self, name) == getattr(other, name)
                        for name in self.__slots__))

    def __repr__(self):
        fields = ", ".join(f"{name}={getattr(self, name)!r}"
                           for name in self.__slots__)
        return f"FxParams({fields})"


class EventFx:
    """An effect that starts with an event and lasts `duration` seconds."""

    __slots__ = ("kind", "x", "y", "start", "duration")

    def __init__(self, kind, x, y, start, duration):
        self.kind = kind
        self.x = x
        self.y = y
        self.start = start
        self.duration = duration

    def age(self, now):
        """Seconds since it started (never negative)."""
        return max(0.0, now - self.start)

    def alive(self, now):
        """True while it is still drawn."""
        return self.age(now) < self.duration

    def intensity(self, now):
        """1 at the start, 0 at the end (linear)."""
        if self.duration <= 0:
            return 0.0
        return max(0.0, FULL - self.age(now) / self.duration)


class TrailGate:
    """Hysteresis of the trail: on above the speed, off after a delay.

    The rest of the derivation is pure, but keeping the trail a moment
    after the ball slows down needs one bit of memory: this object.
    """

    def __init__(self, off_delay=G.TRAIL_OFF_DELAY):
        self.off_delay = off_delay
        self.active = False
        self.off_left = 0.0

    def update(self, speed, dt):
        """New state after a frame with the ball at `speed` for `dt` s."""
        if speed >= G.TRAIL_MIN_SPEED:
            self.active = True
            self.off_left = self.off_delay
        elif self.active:
            self.off_left -= dt
            self.active = self.off_left > 0
        return self.active

    def reset(self):
        """Forgets the state (new match)."""
        self.active = False
        self.off_left = 0.0


def derive(state, viewer, now, events=(), night=False):
    """Effects of one frame: a pure function of the state and the clock."""
    state = state or {}
    players = state.get("players") or ()
    params = FxParams(night=bool(night))
    for effect in state.get("effects") or ():
        _add_power(params, effect, players, viewer)
    params.fire = _fire(params.fire, state)
    params.shock = _newest_shock(events, now)
    params.trail = ball_speed(state) >= G.TRAIL_MIN_SPEED and FULL or 0.0
    return params


def ball_speed(state):
    """Speed of the ball in px/s (0 if there is no ball)."""
    ball = state.get("ball") or {}
    return math.hypot(float(ball.get("vx") or 0.0),
                      float(ball.get("vy") or 0.0))


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


def _newest_shock(events, now):
    """(x, y, age) of the newest shock wave still alive, else None."""
    alive = [fx for fx in events
             if fx.kind == SHOCK_KIND and fx.alive(now)]
    if not alive:
        return None
    fx = max(alive, key=lambda item: item.start)
    return (fx.x, fx.y, fx.age(now))


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


def night_lights():
    """The six warm spotlights of the night mode: (x, y, radius, power)."""
    return tuple((G.NIGHT_FIRST_X + i * G.NIGHT_STEP_X, G.NIGHT_Y,
                  G.NIGHT_RADIUS, G.NIGHT_POWER)
                 for i in range(G.NIGHT_LIGHTS))


def light_array(points, radius, power):
    """Lights (x, y, radius, power) for the kernel, from (x, y) points."""
    return [(point[0], point[1], radius, power) for point in points]
