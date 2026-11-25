"""Blackout strategies: the same `draw` call, one per quality mode.

FULL lets the effects chain darken the frame (CUDA or NumPy, pixel by
pixel). The plain mode uses `SimpleBlackout`: one dark pygame surface with a
round hole of light around every player, built once and reused. It is a
handful of shapes instead of a million pixels, so it costs almost nothing.
"""
import pygame

from fdc import config
from fdc.gpu import effects_state

RULES = config.SimpleBlackout


class ChainBlackout:
  """FULL: the effects chain already darkened the frame; nothing to do."""

  def draw(self, screen, state, viewer):
    """Nothing to draw: the chain did it."""
    del screen, state, viewer


class SimpleBlackout:
  """Plain mode: dark veil over the pitch, light only around the players."""

  def __init__(self):
    self.veil = None        # the one dark surface, reused every frame
    self.builds = 0         # times the surface was created (see tests)

  def draw(self, screen, state, viewer):
    """Darkens `screen` while the blackout lasts (no effect otherwise)."""
    lights = _lights(state, viewer)
    if not lights:
      return
    veil = self._get_veil(screen.get_size())
    veil.fill(RULES.VEIL)
    _punch_holes(veil, lights)
    screen.blit(veil, (0, 0))

  def _get_veil(self, size):
    """The dark surface; it is only rebuilt if the window size changes."""
    if self.veil is None or self.veil.get_size() != size:
      self.veil = pygame.Surface(size, pygame.SRCALPHA)
      self.builds += 1
    return self.veil


def _lights(state, viewer):
  """(x, y, radius) of every light: the heads and, if lit, the ball."""
  points = effects_state.derive(state, viewer).blackout
  if not points:
    return ()
  lights = [(x, y, RULES.PLAYER_RADIUS) for x, y in points]
  ball = (state or {}).get("ball")
  if ball:
    lights.append((ball["x"], ball["y"], RULES.BALL_RADIUS))
  return lights


def _punch_holes(veil, lights):
  """Soft rim first (all lights), then the clear centres on top."""
  for x, y, radius in lights:
    _circle(veil, RULES.RIM, x, y, radius * RULES.RIM_GROWTH)
  for x, y, radius in lights:
    _circle(veil, RULES.CLEAR, x, y, radius)


def _circle(veil, colour, x, y, radius):
  pygame.draw.circle(veil, colour, (int(x), int(y)), int(radius))
