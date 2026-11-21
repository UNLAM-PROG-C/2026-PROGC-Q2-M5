"""Desktop quality shortcut, contextual help and mode confirmation."""
import pygame

from fdc.ui import assets
from fdc.ui import layout
from fdc.ui import palette

HINT = "F10: SIN EFECTOS / FULL · F1: ayuda"
HELP = "F2: pasos CUDA · F4: CPU/GPU en FULL"
DEMO_HELP = " · Tab: siguiente · Esc: salir"
NOTICE_MS = 3000  # Duration of the confirmation in milliseconds.
MARGIN = 8        # Pixels between the chips and the screen edge.
GAP = 6           # Pixels between neighboring chips.
PAD_X = 8         # Horizontal inset of a chip in pixels.
PAD_Y = 4         # Vertical inset of a chip in pixels.
FOOTER_SPACE = 30  # Pixels reserved for the menu's own footer.


class QualityControls:
  """Show the shortcuts without entering the playing field or scoreboard."""

  def __init__(self):
    self.show_help = False
    self.message = ""
    self.expires = 0

  def toggle_help(self):
    """F1: show or hide the extra shortcuts."""
    self.show_help = not self.show_help

  def announce(self, mode_name):
    """Confirm the new mode for NOTICE_MS."""
    self.message = f"Calidad: {mode_name}"
    self.expires = pygame.time.get_ticks() + NOTICE_MS

  def notice(self):
    """The confirmation text while it lasts, else empty."""
    return self.message if pygame.time.get_ticks() < self.expires else ""

  def draw(self, surf, demo=False, menu=False):
    """Draw the chips at the bottom right; return the area they cover."""
    right = surf.get_width() - MARGIN
    bottom = surf.get_height() - (FOOTER_SPACE if menu else MARGIN)
    hint = _chip(surf, HINT, (right, bottom))
    message = self.notice()
    bounds = hint.union(_chip(surf, message, (hint.left - GAP, bottom))) \
        if message else hint
    if not self.show_help:
      return bounds
    label = HELP + (DEMO_HELP if demo else "")
    return bounds.union(_chip(surf, label, (right, hint.top - GAP)))


def _chip(surf, label, bottomright):
  """One text chip anchored at `bottomright`; return its rect."""
  image = assets.text(label, layout.FONT_SMALL, palette.HUD_TEXT)
  rect = image.get_rect().inflate(2 * PAD_X, 2 * PAD_Y)
  rect.bottomright = bottomright
  pygame.draw.rect(surf, palette.HUD_BACKGROUND, rect)
  surf.blit(image, image.get_rect(center=rect.center))
  return rect
