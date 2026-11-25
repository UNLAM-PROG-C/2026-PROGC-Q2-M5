"""Controls of both players (on the main pygame thread).

KEYDOWN/KEYUP events are recorded instead of asking get_pressed(), so
everything can be released when the window loses focus (otherwise a player
could keep walking with a "stuck" key).

Jumps and kicks are counted: each KEYDOWN increments a counter that travels
in every controls snapshot. So the simulation can keep only the latest
snapshot without losing a short press.
"""
import pygame

from fdc import config

ACTIONS = ("left", "right", "jump", "kick")
# Key names shown on screen.
KEY_NAMES = {"left": "Flecha izq.", "right": "Flecha der.",
             "up": "Flecha arriba", "down": "Flecha abajo", "escape": "Esc",
             "space": "Espacio", "return": "Enter"}
KEY_SHORT = {"left": "Izq", "right": "Der", "up": "Arriba", "down": "Abajo"}


def key_code(name):
  return pygame.key.key_code(name)


def key_label(name, short=False):
  """Readable Spanish name (no glyphs common fonts lack)."""
  if short and name in KEY_SHORT:
    return KEY_SHORT[name]
  return KEY_NAMES.get(name, name.upper())


class InputTracker:
  """Keys held and cumulative press counters of each player."""

  def __init__(self, bindings=config.PLAYER_KEYS):
    self.bindings = bindings
    self.keymap = {}
    for idx, keys in enumerate(bindings):
      for action, name in keys.items():
        self.keymap[key_code(name)] = (idx, action)
    self.held = [dict.fromkeys(ACTIONS, False) for _ in bindings]
    self.jumps = [0 for _ in bindings]
    self.kicks = [0 for _ in bindings]
    self.capture = False   # presses only count during a match

  def handle_event(self, ev):
    """Records a game key. True if the event was one of them."""
    if ev.type not in (pygame.KEYDOWN, pygame.KEYUP):
      return False
    hit = self.keymap.get(ev.key)
    if hit is None:
      return False
    idx, action = hit
    down = ev.type == pygame.KEYDOWN
    self.held[idx][action] = down
    if down and self.capture:
      self._count(idx, action)
    return True

  def _count(self, idx, action):
    if action == "jump":
      self.jumps[idx] += 1
    elif action == "kick":
      self.kicks[idx] += 1

  def release_all(self):
    for held in self.held:
      for action in held:
        held[action] = False

  def snapshot_single(self, active=True):
    """One person using EITHER set of keys (tournament): held keys
        combined and counters added."""
    h0, h1 = self.held[0], self.held[1]
    left = active and (h0["left"] or h1["left"])
    right = active and (h0["right"] or h1["right"])
    return [left, right, self.jumps[0] + self.jumps[1],
            self.kicks[0] + self.kicks[1]]

  def snapshot(self, active=True):
    """[[left, right, jumps, kicks], ...]; active=False: no moving."""
    out = []
    for i, held in enumerate(self.held):
      if active:
        out.append([held["left"], held["right"], self.jumps[i],
                    self.kicks[i]])
      else:
        out.append([False, False, self.jumps[i], self.kicks[i]])
    return out
