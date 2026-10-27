"""State interpolation in the online client.

The server sends about 30 snapshots per second and the screen draws 60:
without smoothing, movement would look jumpy (and worse with network jitter).
The client draws "a little in the past", between the last two snapshots.

It is presentation only: the server simulation still decides everything.
"""
from fdc import config

TELEPORT = 160.0     # px: a bigger jump (kickoff, goal) is not smoothed
HALF_TURN = 180.0    # degrees
FULL_TURN = 360.0    # degrees
# s: shorter gaps between states are ignored (they arrived together)...
MIN_GAP = 0.005
# s: ...and so are longer ones (a network hiccup must not slow smoothing).
MAX_GAP = 0.2
# Weight of each new gap in the average arrival rhythm.
GAP_SMOOTHING = 0.2


def _lerp(a, b, k):
    return a + (b - a) * k


def _lerp_angle(a, b, k):
    """Angles in degrees (the ball spins without limit: the short way)."""
    d = (b - a + HALF_TURN) % FULL_TURN - HALF_TURN
    return a + d * k


def _near(a, b):
    """True if two positions are close enough to be smoothed."""
    return abs(a["x"] - b["x"]) <= TELEPORT and abs(a["y"] - b["y"]) <= TELEPORT


class Interpolator:
    """Keeps the last two states and blends them for drawing."""

    def __init__(self):
        self.prev = None
        self.cur = None
        self.t_cur = 0.0
        # Expected rhythm until the real one is measured.
        self.interval = 1 / config.Online.STATE_HZ

    def reset(self):
        self.prev = self.cur = None

    def push(self, state, now):
        """Stores a newer state. Returns False for old or repeated ones."""
        if self.cur is not None and state.get("seq", 0) <= self.cur.get(
                "seq", 0):
            return False
        if self.cur is not None:
            gap = min(MAX_GAP, max(MIN_GAP, now - self.t_cur))
            # Smooth average of the real rhythm.
            self.interval += (gap - self.interval) * GAP_SMOOTHING
        self.prev, self.cur = self.cur, state
        self.t_cur = now
        return True

    def sample(self, now):
        """State to draw at `now` (blended between the last two)."""
        a, b = self.prev, self.cur
        if (b is None or a is None or b.get("paused")
                or a.get("phase") != b.get("phase")):
            return b
        k = min(1.0, max(0.0, (now - self.t_cur) / self.interval))
        if k >= 1.0:
            return b
        out = dict(b)
        out["players"] = [_blend_player(pa, pb, k)
                          for pa, pb in zip(a["players"], b["players"])]
        if _near(a["ball"], b["ball"]):
            out["ball"] = _blend_ball(a["ball"], b["ball"], k)
        return out


def _blend_player(pa, pb, k):
    if not _near(pa, pb):
        return pb
    player = dict(pb)
    player["x"] = _lerp(pa["x"], pb["x"], k)
    player["y"] = _lerp(pa["y"], pb["y"], k)
    return player


def _blend_ball(ba, bb, k):
    ball = dict(bb)
    ball["x"] = _lerp(ba["x"], bb["x"], k)
    ball["y"] = _lerp(ba["y"], bb["y"], k)
    ball["angle"] = _lerp_angle(ba["angle"], bb["angle"], k)
    return ball
