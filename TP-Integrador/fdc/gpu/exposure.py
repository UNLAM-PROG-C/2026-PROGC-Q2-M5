"""Auto exposure of the night mode (F4): the gain follows the mean luma.

The mean comes from the 256-bin histogram of `k_luma_hist`. The gain is an
exponential moving average towards `target / mean`, clamped, and it is used
on the NEXT frame (one frame of latency, documented in the spec).
"""
from fdc import config

G = config.Gpu
MIN_MEAN = 1.0          # below this the frame is black: keep the gain


class AutoExposure:
  """Gain of the night: EMA towards a target mean luma."""

  def __init__(self, gain=1.0):
    self.gain = gain

  def target(self, mean):
    """Gain the frame asks for (clamped)."""
    if mean <= MIN_MEAN:
      return self.gain
    wanted = G.AUTOEXPOSURE_TARGET / mean
    return min(G.AUTOEXPOSURE_MAX, max(G.AUTOEXPOSURE_MIN, wanted))

  def update(self, mean):
    """Moves the gain one step towards the target; returns it."""
    self.gain += G.AUTOEXPOSURE_RATE * (self.target(mean) - self.gain)
    return self.gain

  def reset(self):
    """Back to 1.0 (new match or night off)."""
    self.gain = 1.0
