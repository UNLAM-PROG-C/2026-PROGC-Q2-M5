"""Untimed local match and manually timed effects for a live presentation."""
import math
import time

import pygame

from fdc import config
from fdc.gpu import quality
from fdc.sim import physics
from fdc.ui import assets
from fdc.ui import layout
from fdc.ui import match_screens
from fdc.ui import palette

RULES = config.Presentation
REPLAY = "replay"
NIGHT = "night"
OFF_KEY = pygame.K_0
SHORTCUTS = {
    pygame.K_1: ("freeze_rival", "Hielo"),
    pygame.K_2: ("fire", "Fuego"),
    pygame.K_3: (REPLAY, "Repetición"),
    pygame.K_4: ("confusion", "Confusión"),
    pygame.K_5: ("blackout", "Apagón"),
    pygame.K_6: (NIGHT, "Noche"),
}
LEGEND = " · ".join(f"{pygame.key.name(k)} {label}"
                    for k, (_, label) in SHORTCUTS.items()) + " · 0 Apagar"
DURATIONS = {REPLAY: config.MatchRules.GOAL_REPLAY, NIGHT: RULES.NIGHT_DURATION}


class ManualEffects:
  """Independent deadlines: CPU speed and the match clock do not matter."""

  def __init__(self):
    self.now = time.monotonic
    self.ends = {}

  def activate(self, effect):
    self.ends[effect] = self.now() + _duration(effect)

  def left(self, effect):
    now = self.now()
    return max(0.0, self.ends.get(effect, now) - now)

  def clear(self):
    self.ends.clear()

  def powers(self):
    """Display-only copies of the standard power effect parameters."""
    active = []
    for effect in self.ends.keys() & config.POWERS_BY_ID.keys():
      left = self.left(effect)
      if left:
        active.append(_effect_snapshot(effect, left))
    return active

  def status(self):
    return " · ".join(self._labels()) or "Sin efectos activos"

  def _labels(self):
    for name, label in SHORTCUTS.values():
      remaining = self.left(name)
      if remaining:
        yield f"{label}: {math.ceil(remaining)} s"


def _duration(effect):
  if effect in DURATIONS:
    return DURATIONS[effect]
  return config.POWERS_BY_ID[effect].duration


def _effect_snapshot(effect, left):
  power = config.POWERS_BY_ID[effect]
  target = "ball" if power.target == "ball" else f"p{RULES.TARGET_PLAYER}"
  return {"power": effect, "prop": power.prop, "target": target,
          "left": left, "dur": power.duration}


class PresentationScreen(match_screens.MatchScreen):
  """Two local people, with post-processing under the presenter's control."""

  def __init__(self, app):
    super().__init__(app, app.last_characters or RULES.DEFAULT_CHARACTERS)
    self.effects = ManualEffects()
    self.clip = None
    chain = self.app.postfx
    self.was_night = chain.night
    self.original_quality = _quality_settings(chain)

  def presentation(self):
    """Do not hold goals for an automatic replay."""
    return False

  def to_menu(self):
    self.app.end_presentation()

  def leave(self):
    self._clear_effects()
    chain = self.app.postfx
    chain.clear()
    chain.night = self.was_night
    _restore_quality(chain, self.original_quality)
    super().leave()

  def _start(self, cmd):
    self._clear_effects()
    super()._start(cmd)

  def _on_event(self, m):
    # Retain the ordinary match cues, but not the automatic GPU effects.
    self._dispatch_event(m)

  def _test_key(self, key):
    """Debug pickups are not part of a presentation."""

  def _skip(self):
    """Manual replays only end by time or with the clear key."""
    return False

  def _hotkey(self, key):
    if key == OFF_KEY:
      self._clear_effects()
    elif key in SHORTCUTS:
      self._activate(SHORTCUTS[key][0])
    else:
      return super()._hotkey(key)
    return True

  def _activate(self, effect):
    if not self._ensure_full():
      return
    if effect == REPLAY and not self._start_clip():
      self.toast("Todavía no hay jugadas para repetir", palette.HUD_TEXT)
      return
    self.effects.activate(effect)

  def _ensure_full(self):
    chain = self.app.postfx
    if chain.enabled:
      return True
    if self.original_quality is None:
      self.toast("Efectos no disponibles", palette.HUD_TEXT)
      return False
    chain.allowed = True  # The override only lasts for this presentation.
    chain.chosen_mode = True
    chain.set_quality_mode(quality.FULL)
    self.app.quality_controls.announce(chain.quality_mode_name())
    return True

  def _start_clip(self):
    if not self.effects.left(REPLAY):
      self.clip = self.replay_history.frames(DURATIONS[REPLAY])
    return self.app.postfx.start_driven_replay(self.clip, DURATIONS[REPLAY])

  def _clear_effects(self):
    self.effects.clear()
    self.clip = None
    self.app.postfx.night = False
    self.app.postfx.skip()

  def controls(self, active):
    controls = super().controls(active)
    if active and self.effects.left("confusion"):
      _reverse_horizontal(controls[RULES.TARGET_PLAYER])
    return controls

  def update(self, dt):
    if not self.app.postfx.enabled:
      self._clear_effects()
    super().update(dt)

  def draw(self, surf):
    self._sync_postfx()
    super().draw(surf)
    _draw_hud(surf, self.effects.status())

  def postfx_state(self, st):
    powers = self.effects.powers()
    return dict(st, effects=powers) if powers else st

  def _sync_postfx(self):
    chain = self.app.postfx
    chain.night = bool(self.effects.left(NIGHT))
    left = self.effects.left(REPLAY)
    if left:
      chain.drive_replay(1.0 - left / DURATIONS[REPLAY])
    elif self.clip is not None:
      chain.end_goal_replay()
      self.clip = None


def _quality_settings(chain):
  if hasattr(chain, "set_quality_mode"):
    return chain.allowed, chain.chosen_mode, chain.quality_mode
  return None


def _restore_quality(chain, settings):
  if settings is not None and _quality_settings(chain) != settings:
    chain.allowed, chain.chosen_mode, mode = settings
    chain.set_quality_mode(mode)


def _reverse_horizontal(controls):
  left, right, _, _ = controls
  direction = physics.effective_direction(int(right) - int(left), True)
  controls[:2] = [direction < 0, direction > 0]


def _draw_hud(surf, status):
  bottom = _draw_chip(surf, LEGEND, RULES.HUD_TOP)
  _draw_chip(surf, status, bottom + RULES.HUD_ROW_GAP)


def _draw_chip(surf, label, top):
  image = assets.text(label, layout.FONT_SMALL, palette.HUD_TEXT)
  rect = image.get_rect().inflate(*RULES.HUD_PADDING)
  rect.midtop = (surf.get_width() // 2, top)
  pygame.draw.rect(surf, palette.HUD_BACKGROUND, rect)
  surf.blit(image, image.get_rect(center=rect.center))
  return rect.bottom
