"""Heat map of the match (F6): where the ball and the players were.

The chain records the positions while the match is played and, every
`HEAT_FLUSH_FRAMES` frames, sends them to the backend (`k_heat_accumulate`,
one thread per point, `atomicAdd` because many points fall in the same cell).
The grid stays on the device during the match: the host only receives it at
the end (`heat_download`), so the result screen can draw any channel with
`k_heat_render` over the image of the pitch.

Channels: 0 the ball, 1 the first player and 2 the second one.
"""
import numpy as np

from fdc import config
from fdc import protocol

G = config.Gpu
ARENA = config.Arena
BALL = 0                # channel of the ball
PLAYER = 1              # first player (the second one is PLAYER + 1)
CHANNELS = 3            # ball, player 0 and player 1
PLAYERS = 2             # players of a match
NO_HEAT = 0             # biggest cell when nothing was recorded


class HeatmapRecorder:
    """Positions of the ball and of the players over the whole match."""

    def __init__(self, cols=G.HEATMAP_COLS, rows=G.HEATMAP_ROWS):
        self.cols = cols
        self.rows = rows
        self.cell_w = ARENA.WIDTH / cols    # px of one cell, across
        self.cell_h = ARENA.HEIGHT / rows   # px of one cell, down
        self.grids = np.zeros((CHANNELS, rows, cols), np.uint32)
        self.maxes = np.zeros(CHANNELS, np.uint32)
        self.pending = _empty()             # points not sent yet, per channel
        self.frames = 0                     # frames since the last flush
        self.recorded = 0                   # points fed in the whole match
        self.started = False                # the backend already has the grid
        self.dirty = False                  # the host copy is out of date

    def feed(self, state):
        """Records the ball and the players of one match state."""
        if not playing(state):
            return
        self.frames += 1
        for channel, point in points(state):
            self.pending[channel].append(point)
            self.recorded += 1

    def due(self):
        """True if a channel is full or enough frames went by."""
        return (max(len(cells) for cells in self.pending)
                >= G.HEAT_FLUSH_POINTS
                or self.frames >= G.HEAT_FLUSH_FRAMES)

    def flush(self, ops):
        """Sends the buffered points to the backend (accumulates them)."""
        if ops is not None and any(self.pending):
            if not self.started:
                ops.heat_reset(self.cols, self.rows)
                self.started = True
            for channel, cells in enumerate(self.pending):
                if cells:
                    ops.heat_accumulate(channel, np.asarray(cells,
                                                            np.float32),
                                        self.cols, self.rows, self.cell_w,
                                        self.cell_h)
            self.dirty = True
        self.pending = _empty()
        self.frames = 0

    def snapshot(self, ops):
        """Brings the grid and the maximums back (only when they changed)."""
        if ops is not None and self.started and self.dirty:
            self.grids, self.maxes = ops.heat_download(self.cols, self.rows)
            self.dirty = False
        return self.grids

    def grid(self, channel):
        """Flat grid of one channel (the kernel reads it that way)."""
        return self.grids[channel].reshape(-1)

    def top(self, channel):
        """Biggest cell of that channel (the kernel normalises with it)."""
        return int(self.maxes[channel])

    def render(self, ops, image, channel, alpha=G.HEATMAP_ALPHA):
        """Image of the pitch with the heat of one channel over it."""
        self.snapshot(ops)
        if self.top(channel) <= NO_HEAT:
            return image
        return ops.heat_render(image, self.grids, self.maxes, self.cols,
                               self.rows, channel, alpha, G.HEATMAP_GAIN)

    def clear(self):
        """New match: empty grids and buffer (the backend resets its own)."""
        self.grids = np.zeros((CHANNELS, self.rows, self.cols), np.uint32)
        self.maxes = np.zeros(CHANNELS, np.uint32)
        self.pending = _empty()
        self.frames = 0
        self.recorded = 0
        self.started = False
        self.dirty = False


def _empty():
    """Empty list of points for each channel."""
    return [[] for _ in range(CHANNELS)]


def playing(state):
    """True if the match is being played (not paused, not in the countdown)."""
    if not state:
        return False
    return (not state.get("paused")
            and state.get("phase") == protocol.PHASE_PLAYING)


def points(state):
    """(channel, (x, y)) of the ball and of the players of one state."""
    ball = state.get("ball") or {}
    yield BALL, (float(ball.get("x") or 0.0), float(ball.get("y") or 0.0))
    for index, player in enumerate(state.get("players") or ()):
        if index < PLAYERS:
            yield (PLAYER + index, (float(player.get("x") or 0.0),
                                    float(player.get("y") or 0.0)))
