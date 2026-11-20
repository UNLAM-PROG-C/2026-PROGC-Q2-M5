"""Player name: chosen once at the start, valid for every mode.

It appears before the menu the first time the game opens (or if the saved
name is not valid). Later it can be changed from the main menu.
"""
import pygame

from fdc import profile
from fdc.ui import assets
from fdc.ui import layout
from fdc.ui import palette
from fdc.ui import screens
from fdc.ui import widgets

ENTER_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER)


def _name_field(rect, current):
  field = widgets.TextField(
      rect, "TU NOMBRE", profile.NAME_MAX_LEN,
      allowed=lambda ch: ch in profile.NAME_CHARS, value=current,
      placeholder=(f"entre {profile.NAME_MIN_LEN} y "
                   f"{profile.NAME_MAX_LEN} letras o números"),
      sticky=True)
  field.focus(True)
  return field


def _draw_logo(surf, t):
  screens.panel(surf, pygame.Rect(screens.LOGO_PANEL),
                alpha=screens.LOGO_PANEL_ALPHA)
  screens.draw_logo(surf, screens.LOGO_CENTER, screens.LOGO_SCALE, t)


class ProfileScreen(screens.Screen):
  """Text field for the name, with a confirm button."""
  # Name field (x, y, width, height) in px.
  FIELD = (440, 352, 400, layout.BUTTON_H)
  OK_SIZE = (300, layout.BUTTON_H)   # confirm button (width, height) in px
  OK_CENTER = (layout.CENTER_X, 470)   # centre of that button (px)
  BOX = (340, 210, 600, 330)         # question box (x, y, w, h) in px
  QUESTION_Y = 34                    # question, from the box top (px)
  EXPLANATION_Y = 78                 # explanation, from the box top (px)
  NOTE_GAP = 24                      # notice or error, below the box (px)

  def __init__(self, app, first_run=True):
    super().__init__(app)
    self.first_run = first_run
    self.field = _name_field(self.FIELD,
                             app.profile.name if app.profile else "")
    self.ok_rect = pygame.Rect((0, 0), self.OK_SIZE)
    self.ok_rect.center = self.OK_CENTER
    self.hover = False
    self.error = None
    self.back_button = screens.BackButton(self.back)
    # The first time there is nowhere to go back to.
    self.back_button.visible = not first_run

  def back(self):
    self.app.switch(screens.MenuScreen(self.app))

  def submit(self):
    name = self.field.value.strip()
    if not profile.valid_name(name):
      self.error = f"El nombre debe tener {profile.NAME_RULE}."
      self.app.audio.play("blocked")
      return
    old = self.app.profile
    # Same player, same id.
    self.app.set_profile(old.renamed(name) if old
                         else profile.Profile(name))
    self.app.audio.play("confirm")
    self.back()

  def handle_event(self, ev):
    if self.back_button.handle_event(ev):
      return
    if (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE
            and not self.first_run):
      self.app.audio.play("back")
      self.back()
      return
    if not self._field_event(ev):
      self._button_event(ev)

  def _field_event(self, ev):
    """True if the text field used the event."""
    r = self.field.handle_event(ev)
    if r == "submit":
      self.submit()
    if r:
      self.error = None if r is True else self.error
    return bool(r)

  def _button_event(self, ev):
    if ev.type == pygame.MOUSEMOTION:
      self.hover = self.ok_rect.collidepoint(ev.pos)
    elif (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1
          and self.ok_rect.collidepoint(ev.pos)):
      self.submit()
    elif ev.type == pygame.KEYDOWN and ev.key in ENTER_KEYS:
      self.submit()

  def draw(self, surf):
    surf.blit(self.app.background, (0, 0))
    screens.dim(surf, layout.VEIL_PROFILE)
    _draw_logo(surf, self.t)
    box = screens.panel(surf, pygame.Rect(self.BOX))
    self._question(surf, box)
    self.field.draw(surf, self.t)
    screens.button(surf, self.ok_rect,
                   "¡A JUGAR!" if self.first_run else "GUARDAR",
                   self.hover, True, layout.FONT_TEXT, self.t)
    self._note(surf, box)
    screens.footer(surf, "Enter: confirmar" + (
        "" if self.first_run else "  -  Esc: volver sin cambiar"))
    self.back_button.draw(surf, self.t)

  def _question(self, surf, box):
    assets.draw_text(surf, "¿CÓMO TE LLAMÁS?", layout.FONT_LARGE,
                     (layout.CENTER_X, box.top + self.QUESTION_Y),
                     palette.GOLD, kind="title", outline=palette.INK,
                     shadow=True)
    assets.draw_text(surf, "Vale para todos los modos: Mundialito, local "
                     "y online.", layout.FONT_SMALL,
                     (layout.CENTER_X, box.top + self.EXPLANATION_Y),
                     palette.INK, outline=None)

  def _note(self, surf, box):
    """Error, or the hint about repeated names."""
    pos = (layout.CENTER_X, box.bottom + self.NOTE_GAP)
    if self.error:
      assets.draw_text(surf, self.error, layout.FONT_SMALL, pos,
                       palette.RED, outline=palette.WHITE)
    else:
      assets.draw_text(surf, "Si otra persona usa el mismo nombre "
                       "online, los distingue una etiqueta (#1234).",
                       layout.FONT_SMALL, pos, palette.INK,
                       outline=palette.WHITE)
