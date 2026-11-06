"""Timings of the effects chain (per stage and per frame).

The overlay of the game and the measurement script read from here. Times
are milliseconds; the buffer keeps the last `config.Gpu.METRICS_FRAMES`
frames so the numbers do not jump.
"""
import collections

from fdc import config

STAGES = ("glow", "composite", "particles", "lights", "heat", "trail",
          "histogram", "shock", "fire", "confusion", "confusion_rot",
          "ice_edges", "ice_tint", "blackout", "night", "exposure")
PER_SECOND = 1000.0     # milliseconds in a second
DECIMALS = 3            # decimals of the stage times
FPS_DECIMALS = 1        # decimals of the frames per second


class Metrics:
    """Milliseconds per stage and per frame (a ring buffer each)."""

    def __init__(self, frames=None):
        size = frames or config.Gpu.METRICS_FRAMES
        self.size = size
        self.stage = {name: collections.deque(maxlen=size) for name in STAGES}
        self.frames = collections.deque(maxlen=size)
        self.skipped = 0       # frames the chain did not touch

    def add(self, name, milliseconds):
        """One sample of a stage (ignored if the stage is not known)."""
        if name in self.stage:
            self.stage[name].append(milliseconds)

    def frame(self, milliseconds):
        """One sample of the whole chain."""
        self.frames.append(milliseconds)

    def skip(self):
        """The chain did not run this frame (paused, menu...)."""
        self.skipped += 1

    def average(self, name):
        """Mean of a stage, 0 if it has no samples."""
        return _mean(self.stage.get(name, ()))

    def total(self):
        """Mean of the whole chain."""
        return _mean(self.frames)

    def fps(self):
        """Frames per second implied by the mean frame time."""
        total = self.total()
        return PER_SECOND / total if total > 0 else 0.0

    def clear(self):
        """Forgets the frames measured so far."""
        self.frames.clear()
        for values in self.stage.values():
            values.clear()

    def summary(self):
        """{stage: ms} plus 'frame', 'fps' and 'frames'."""
        data = {name: round(self.average(name), DECIMALS) for name in STAGES}
        data["frame"] = round(self.total(), DECIMALS)
        data["fps"] = round(self.fps(), FPS_DECIMALS)
        data["frames"] = len(self.frames)
        return data


def _mean(values):
    """Mean of an iterable of numbers (0 if empty)."""
    values = list(values)
    return sum(values) / len(values) if values else 0.0
