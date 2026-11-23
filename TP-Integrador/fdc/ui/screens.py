"""General screens: boot, menu, controls, powers legend and error.

Light retro style: cream bevelled panels, buttons with a ► cursor and an
own pixel art font. The match screens (selection, play, result) are in
match_screens.py.

State pattern: each screen is a state of the App; app.switch() changes the
current one and every screen answers the same calls (handle_event, update,
draw...).

Measures are px in the 1280 x 720 logical resolution. The common ones are
in layout.py; the ones of each screen, at the top of its class.
"""
import math

import pygame

from fdc import config
from fdc.ui import assets
from fdc.ui import characters
from fdc.ui import icons
from fdc.ui import input as ui_input
from fdc.ui import layout
from fdc.ui import palette
from fdc.ui import pixelfont
from fdc.ui import retro
from fdc.ui import sprites

UP_KEYS = (pygame.K_w, pygame.K_UP)
DOWN_KEYS = (pygame.K_s, pygame.K_DOWN)
OK_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_p)
BACK_KEYS = (pygame.K_ESCAPE, pygame.K_BACKSPACE)

# --- menus
MENU_W = 360                       # px: width of the buttons of a menu
MENU_GAP = 14                      # px between buttons of a menu
# --- logo
LOGO_BOB_HZ = 2                    # the logo goes up and down twice a second
LOGO_BOB_PX = 4                    # px the logo rises
LOGO_TAGLINE_SIZE = 18             # font size of the tagline (at scale 1)
LOGO_TAGLINE_GAP = 56              # px between logo and tagline (at scale 1)
# Translucent box behind the logo (menu, name): x, y, width, height in px.
LOGO_PANEL = (360, 20, 560, 150)
LOGO_PANEL_ALPHA = 225             # opacity of that box
LOGO_CENTER = (layout.CENTER_X, 72)  # centre of the logo in the menu (px)
LOGO_SCALE = 0.9                   # scale of the logo in the menu
# --- footer
FOOTER_H = 36                      # px: height of the footer band
FOOTER_ALPHA = 220                 # opacity of the footer band
FOOTER_LINE = 2                    # px: top line of the band
# --- drawn keys
KEYCAP_MIN_W = 44                  # px: minimum width of a key
KEYCAP_PADDING = 24                # px of air around the key name
KEYCAP_H = 36                      # px: height of a key
# --- LED board of the result
SCOREBOARD_H = 110                 # px: height of the board
SCOREBOARD_INSET = 8               # px between the frame and the LED screen
SCOREBOARD_LED_SCALE = 9           # size of the LED dots of the result
FALLBACK_FPS = float(config.UI_FPS)  # FPS shown while there are no samples


class Screen:
  """Base state: every screen overrides what it needs."""

  def __init__(self, app):
    self.app = app
    self.t = 0.0

  def enter(self):
    """Called when the screen becomes the current one."""

  def leave(self):
    """Called when another screen replaces it."""

  def handle_event(self, ev):
    """A pygame event (keyboard, mouse...)."""

  def on_link(self, msgs, state):
    """Messages and the last state from the simulation."""

  def on_net(self, msg):
    """Message from the online server (one at a time, in order)."""

  def on_focus_lost(self):
    """The window lost the keyboard focus."""

  def update(self, dt):
    self.t += dt

  def draw(self, surf):
    """Draws the whole screen."""

  def debug_info(self):
    """Extra lines of the F3 panel."""
    return {}


# ---------------------------------------------------------------------------
# Retro widgets
# ---------------------------------------------------------------------------
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def button(surf, rect, label, active=False, enabled=True,
           size=layout.FONT_TEXT, t=0.0):
  """Retro button: bevel, shadow and a blinking ► cursor when chosen."""
  face = palette.GOLD if active else palette.CREAM
  if not enabled:
    face = palette.CREAM_DARK
  r = pygame.Rect(rect)
  if active:
    r = r.move(0, -layout.BOB_PX if int(t * layout.BOB_HZ) % 2 else 0)
  retro.bevel_box(surf, r, face)
  assets.draw_text(surf, label, size, r.center,
                   palette.INK if enabled else palette.INK_SOFT,
                   outline=None)
  if active and int(t * layout.BLINK_HZ) % 2 == 0:
    _cursor(surf, r, size)


def _cursor(surf, r, size):
  assets.draw_text(surf, "►", size, (r.left - layout.CURSOR_GAP, r.centery),
                   palette.INK, outline=palette.WHITE)


def _left_click(ev):
  return ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1


def _play(audio, name):
  if audio:
    audio.play(name)


class BackButton:
  """Back button of the top left corner (mouse). Esc does the same."""
  WIDTH = 176                    # px: width of the button
  TOP = 12                       # px from the top of the screen
  # Place of the button.
  RECT = pygame.Rect(layout.SCREEN_MARGIN, TOP, WIDTH, layout.BUTTON_SMALL_H)

  def __init__(self, action, label="◄ VOLVER", rect=None):
    self.action = action
    self.label = label
    self.rect = pygame.Rect(rect or self.RECT)
    self.hover = False
    self.visible = True

  def handle_event(self, ev):
    """True if the event was a click on the button (action done)."""
    if not self.visible:
      return False
    if ev.type == pygame.MOUSEMOTION:
      self.hover = self.rect.collidepoint(ev.pos)
    elif _left_click(ev) and self.rect.collidepoint(ev.pos):
      self.action()
      return True
    return False

  def draw(self, surf, t=0.0):
    if self.visible:
      button(surf, self.rect, self.label, self.hover, True,
             layout.FONT_SMALL, t)


class Menu:
  """Vertical list of buttons. Keyboard (both players) and mouse."""

  # pylint: disable-next=too-many-arguments,too-many-positional-arguments
  def __init__(self, items, center, width=MENU_W, height=layout.BUTTON_H,
               gap=MENU_GAP, size=layout.FONT_TEXT):
    self.items = list(items)        # [(text, callback)]
    self.center = center
    self.w, self.h, self.gap, self.size = width, height, gap, size
    self.sel = 0
    self.t = 0.0
    self.enabled = True

  def rects(self):
    n = len(self.items)
    total = n * self.h + (n - 1) * self.gap
    y0 = self.center[1] - total / 2
    out = []
    for i in range(n):
      r = pygame.Rect(0, 0, self.w, self.h)
      r.midtop = (self.center[0], y0 + i * (self.h + self.gap))
      out.append(r)
    return out

  def handle_event(self, ev, audio=None):
    """True if the menu used the event."""
    if not self.enabled:
      return False
    if ev.type == pygame.KEYDOWN:
      return self._key(ev.key, audio)
    if ev.type == pygame.MOUSEMOTION:
      self._hover(ev.pos, audio)
    elif _left_click(ev):
      return self._click(ev.pos, audio)
    return False

  def _key(self, key, audio):
    if key in UP_KEYS or key in DOWN_KEYS:
      step = -1 if key in UP_KEYS else 1
      self.sel = (self.sel + step) % len(self.items)
      _play(audio, "select")
      return True
    if key in OK_KEYS:
      _play(audio, "confirm")
      self.items[self.sel][1]()
      return True
    return False

  def _hover(self, pos, audio):
    for i, r in enumerate(self.rects()):
      if r.collidepoint(pos) and self.sel != i:
        self.sel = i
        _play(audio, "select")

  def _click(self, pos, audio):
    for i, r in enumerate(self.rects()):
      if r.collidepoint(pos):
        self.sel = i
        _play(audio, "confirm")
        self.items[i][1]()
        return True
    return False

  def update(self, dt):
    self.t += dt

  def draw(self, surf):
    for i, (r, (label, _)) in enumerate(zip(self.rects(), self.items)):
      button(surf, r, label, i == self.sel and self.enabled,
             self.enabled, self.size, self.t)


_overlays = {}


def dim(surf, alpha=layout.VEIL_PROFILE, color=palette.CREAM):
  """Light veil over the stadium (keeps the bright palette)."""
  key = (surf.get_size(), alpha, color)
  s = _overlays.get(key)
  if s is None:
    s = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    s.fill((*color, alpha))
    _overlays[key] = s
  surf.blit(s, (0, 0))


def panel(surf, rect, face=palette.CREAM, border=palette.INK, alpha=None):
  """Retro panel; returns its usable area."""
  return retro.panel(surf, rect, face, border, alpha)


def title(surf, txt, center, size=layout.FONT_TITLE_L, color=palette.GOLD):
  """Big title with outline and shadow."""
  assets.draw_text(surf, txt, size, center, color, kind="title",
                   outline=palette.INK, shadow=True)


def draw_logo(surf, center, scale=1.0, t=0.0):
  """Name of the game and its tagline, hopping."""
  y = center[1] + (LOGO_BOB_PX if int(t * LOGO_BOB_HZ) % 2 else 0)
  assets.draw_text(surf, config.GAME_NAME.upper(),
                   int(layout.FONT_BANNER * scale), (center[0], y),
                   palette.GOLD, kind="title", outline=palette.INK,
                   shadow=True)
  assets.draw_text(surf, config.GAME_TAGLINE, int(LOGO_TAGLINE_SIZE * scale),
                   (center[0], y + LOGO_TAGLINE_GAP * scale), palette.INK,
                   outline=palette.WHITE)


def footer(surf, txt):
  """Cream band at the bottom with a hint."""
  r = pygame.Rect(0, layout.SCREEN_H - FOOTER_H, layout.SCREEN_W, FOOTER_H)
  s = pygame.Surface(r.size, pygame.SRCALPHA)
  s.fill((*palette.CREAM, FOOTER_ALPHA))
  surf.blit(s, r)
  pygame.draw.rect(surf, palette.INK,
                   (0, r.top, layout.SCREEN_W, FOOTER_LINE))
  assets.draw_text(surf, txt, layout.FONT_SMALL, r.center, palette.INK,
                   outline=None)


def keycap(surf, center, label, size=layout.FONT_SMALL):
  """Key drawn as a retro button."""
  w = max(KEYCAP_MIN_W, assets.text_width(label, size) + KEYCAP_PADDING)
  r = pygame.Rect(0, 0, w, KEYCAP_H)
  r.center = center
  retro.bevel_box(surf, r, palette.WHITE)
  assets.draw_text(surf, label, size, r.center, palette.INK, outline=None)
  return r


def scoreboard(surf, center, width, score_text):
  """Board with the result in LED dots (end of match screens)."""
  box = pygame.Rect(0, 0, width, SCOREBOARD_H)
  box.center = center
  pygame.draw.rect(surf, palette.INK,
                   box.move(layout.SHADOW_OFFSET, layout.SHADOW_OFFSET))
  pygame.draw.rect(surf, palette.STRUCT_DARK, box)
  pygame.draw.rect(surf, palette.INK, box, layout.FRAME_LINE)
  shrink = -SCOREBOARD_INSET - SCOREBOARD_INSET
  led = box.inflate(shrink, shrink)
  pygame.draw.rect(surf, palette.LED_BG, led)
  score = pixelfont.render_led(score_text, SCOREBOARD_LED_SCALE,
                               palette.LED_ON, palette.LED_OFF)
  surf.blit(score, score.get_rect(center=led.center))


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def bouncing_ball(app, surf, t, x, ground_y, height, hz, spin):
  """The game ball bouncing: it rises 'height' px; 'hz' sets the rhythm
    and 'spin' the turn (degrees/s)."""
  y = ground_y - abs(math.sin(t * hz)) * height
  app.ball_sprite.draw(surf, x, y, config.BallSpec.RADIUS, t * spin)


def wrapped_lines(surf, lines, size, inner, padding, line_h, gap):
  """Paragraphs wrapped to the width of 'inner', from its top left."""
  y = inner.top + padding
  for ln in lines:
    for sub in assets.wrap(ln, size, inner.width - 2 * padding):
      assets.draw_text(surf, sub, size, (inner.left + padding, y),
                       palette.INK, anchor="topleft", outline=None)
      y += line_h
    y += gap


# ---------------------------------------------------------------------------
# Boot: waits for READY from the simulation (without blocking the window)
# ---------------------------------------------------------------------------
class BootScreen(Screen):
  """Warms up the portraits and waits until the simulation is ready."""
  LOGO_CENTER = (layout.CENTER_X, 230)   # logo (px)
  MESSAGE_Y = 420                    # message about the simulation start
  BALL_GROUND_Y = 480                # bouncing ball: floor (px)
  BALL_HOP = 30                      # px it rises
  BALL_HOP_HZ = 5                    # bounces per second (one way)
  BALL_SPIN = 400                    # degrees per second it turns
  STATUS_Y = 540                     # line about the READY confirmation

  def __init__(self, app):
    super().__init__(app)
    self.to_warm = list(characters.CHARACTER_IDS)

  def update(self, dt):
    super().update(dt)
    if self.to_warm:       # portraits, one per frame: the window responds
      self.app.sprites.portrait(self.to_warm.pop(0))
    elif self.app.link is None or self.app.link.ready:
      self.app.switch(self.app.first_screen())

  def draw(self, surf):
    surf.blit(self.app.background, (0, 0))
    dim(surf, layout.VEIL_BOOT)
    draw_logo(surf, self.LOGO_CENTER, 1.0, self.t)
    waiting = self.app.link is not None and not self.app.link.ready
    assets.draw_text(surf, ("Iniciando el proceso de simulación..."
                            if waiting else "Preparando personajes..."),
                     layout.FONT_TEXT,
                     (layout.CENTER_X, self.MESSAGE_Y), palette.INK,
                     outline=palette.WHITE)
    bouncing_ball(self.app, surf, self.t, layout.CENTER_X,
                  self.BALL_GROUND_Y, self.BALL_HOP, self.BALL_HOP_HZ,
                  self.BALL_SPIN)
    self._status(surf, self.app.link, waiting)

  def _status(self, surf, link, waiting):
    """READY line (only with a simulation process)."""
    if link is None:
      return
    text = (f"Esperando la confirmación READY ({self.t:.1f} s de "
            f"{config.IPC.READY_TIMEOUT:.0f} s)" if waiting
            else "Simulación lista")
    assets.draw_text(surf, text, layout.FONT_SMALL,
                     (layout.CENTER_X, self.STATUS_Y), palette.INK_SOFT,
                     outline=None)


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------
class MenuScreen(Screen):
  """Main menu with the logo, two mascots and a bouncing ball."""
  MENU_CENTER = (layout.CENTER_X, 440)   # centre of the button list (px)
  PLAYER_TOP = 12                    # px: player name button, top right
  PLAYER_PADDING = 40                # px of air around the name
  # The two mascots: (character, x, looking right = 1 / left = -1).
  MASCOTS = (("messi", 230, 1), ("pele", 1050, -1))
  MASCOT_SCALE = 1.6                 # size of the mascots
  BALL_GROUND_Y = 590                # bouncing ball in the middle: floor
  BALL_HOP = 150                     # px it rises
  BALL_HOP_HZ = 2.6                  # bounces per second (one way)
  BALL_SPIN = 200                    # degrees per second it turns

  def __init__(self, app):
    super().__init__(app)
    items = [
        ("Jugar", lambda: app.switch(PlayMenuScreen(app))),
        ("Controles", lambda: app.switch(ControlsScreen(app))),
        ("Poderes", lambda: app.switch(LegendScreen(app))),
        ("Opciones", lambda: app.switch(OptionsScreen(app))),
        ("DEMO", app.start_demo),
        ("Presentación", app.start_presentation),
        ("Salir", app.quit),
    ]
    self.menu = Menu(items, self.MENU_CENTER)
    self.player_hover = False

  def player_label(self):
    if not self.app.profile:
      return ""
    return f"{self.app.profile.name.upper()}  (CAMBIAR)"

  def player_rect(self):
    """Player name button, top right (its width depends on the name)."""
    width = (assets.text_width(self.player_label(), layout.FONT_SMALL)
             + self.PLAYER_PADDING)
    r = pygame.Rect(0, 0, width, layout.BUTTON_SMALL_H)
    r.topright = (layout.SCREEN_W - layout.SCREEN_MARGIN, self.PLAYER_TOP)
    return r

  def enter(self):
    self.app.audio.crowd(False)

  def change_name(self):
    # pylint: disable-next=import-outside-toplevel
    from fdc.ui import profile_screen  # Circular: it imports this module.
    self.app.audio.play("confirm")
    self.app.switch(profile_screen.ProfileScreen(self.app,
                                                 first_run=False))

  def handle_event(self, ev):
    if ev.type == pygame.MOUSEMOTION:
      self.player_hover = self.player_rect().collidepoint(ev.pos)
    name_click = (_left_click(ev)
                  and self.player_rect().collidepoint(ev.pos))
    if name_click or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_n):
      self.change_name()
    elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
      self._escape()
    else:
      self.menu.handle_event(ev, self.app.audio)

  def _escape(self):
    """Esc takes the cursor to the quit button (it does not close)."""
    self.menu.sel = len(self.menu.items) - 1
    self.app.audio.play("select")

  def update(self, dt):
    super().update(dt)
    self.menu.update(dt)

  def draw(self, surf):
    surf.blit(self.app.background, (0, 0))
    dim(surf, layout.VEIL_MENU)
    self._mascots(surf)
    panel(surf, pygame.Rect(LOGO_PANEL), alpha=LOGO_PANEL_ALPHA)
    draw_logo(surf, LOGO_CENTER, LOGO_SCALE, self.t)
    self.menu.draw(surf)
    if self.app.profile is not None:  # player: click (or N) to rename
      button(surf, self.player_rect(), self.player_label(),
             self.player_hover, True, layout.FONT_SMALL, self.t)
    footer(surf, self._footer_text())

  def _mascots(self, surf):
    for i, (cid, x, f) in enumerate(self.MASCOTS):
      ang, bob = sprites.idle_pose(self.t, i)
      img, (fx, fy) = self.app.sprites.player(
          cid, f, ang, bob, config.PLAYER_COLORS[i], False,
          self.MASCOT_SCALE)
      surf.blit(img, (x - fx, config.Arena.FLOOR_Y - fy))
    bouncing_ball(self.app, surf, self.t, layout.CENTER_X,
                  self.BALL_GROUND_Y, self.BALL_HOP, self.BALL_HOP_HZ,
                  self.BALL_SPIN)

  def _footer_text(self):
    badge = "  -  MODO PRUEBA" if self.app.options.test_mode else ""
    key = ui_input.key_label
    return (f"N: cambiar nombre  -  {key(config.DEBUG_PANEL_KEY)}: "
            f"depuración  -  {key(config.FULLSCREEN_KEY)}: pantalla "
            f"completa  -  {key(config.MUTE_KEY)}: silencio{badge}")


# ---------------------------------------------------------------------------
# Submenus: play -> tournament / multiplayer -> local / online
# ---------------------------------------------------------------------------
class SubMenuScreen(Screen):
  """Menu with a title over the stadium. Esc goes back."""
  TITLE = ""
  SUBTITLE = ""
  MENU_CENTER = (layout.CENTER_X, 420)   # centre of the button list (px)
  TITLE_Y = 120                      # title (px)
  SUBTITLE_Y = 176                   # explanation below the title (px)

  def __init__(self, app, items):
    super().__init__(app)
    self.menu = Menu(items, self.MENU_CENTER)

  def back(self):
    self.app.switch(MenuScreen(self.app))

  def handle_event(self, ev):
    if ev.type == pygame.KEYDOWN and ev.key in BACK_KEYS:
      self.app.audio.play("back")
      self.back()
      return
    self.menu.handle_event(ev, self.app.audio)

  def update(self, dt):
    super().update(dt)
    self.menu.update(dt)

  def draw(self, surf):
    surf.blit(self.app.background, (0, 0))
    dim(surf, layout.VEIL_SUBMENU)
    title(surf, self.TITLE, (layout.CENTER_X, self.TITLE_Y),
          layout.FONT_TITLE_XL)
    if self.SUBTITLE:
      assets.draw_text(surf, self.SUBTITLE, layout.FONT_SMALL,
                       (layout.CENTER_X, self.SUBTITLE_Y), palette.INK,
                       outline=palette.WHITE)
    self.menu.draw(surf)
    footer(surf, "Esc: volver")


class PlayMenuScreen(SubMenuScreen):
  """Tournament (against the computer) or multiplayer."""
  TITLE = "JUGAR"
  SUBTITLE = ("Mundialito: vos contra la computadora.  "
              "Multijugador: dos personas.")

  def __init__(self, app):
    super().__init__(app, [("Mundialito", self.tournament),
                           ("Multijugador", self.multiplayer),
                           ("Volver", self.back)])

  def tournament(self):
    # pylint: disable-next=import-outside-toplevel
    from fdc.ui import tournament_screens  # Circular: imports this.
    tournament_screens.open_tournament(self.app)

  def multiplayer(self):
    self.app.switch(MultiplayerMenuScreen(self.app))


class MultiplayerMenuScreen(SubMenuScreen):
  """Local (same keyboard) or online.

    It also holds the online prediction switch: on by default, off with the
    third button or with "--sin-prediccion" when the connection makes the
    own player look odd.
    """
  TITLE = "MULTIJUGADOR"
  SUBTITLE = ("Local: dos personas en el mismo teclado.  "
              "Online: cada uno desde su casa.  "
              "Predicción: el jugador propio se mueve al instante.")
  PREDICTION_ITEM = 2         # position of the switch in the menu

  def __init__(self, app):
    super().__init__(app, [("Local", self.local), ("Online", self.online),
                           ("", self.cycle_prediction),
                           ("Volver", self.back)])
    self.refresh()

  def back(self):
    self.app.switch(PlayMenuScreen(self.app))

  def refresh(self):
    """The third button always names the state of the prediction."""
    on = getattr(self.app, "prediction", config.Online.PREDICT_ENABLED)
    label = "Predicción online: " + ("SÍ" if on else "NO")
    self.menu.items[self.PREDICTION_ITEM] = (label, self.cycle_prediction)

  def cycle_prediction(self):
    """Turns the online prediction on or off."""
    on = getattr(self.app, "prediction", config.Online.PREDICT_ENABLED)
    self.app.prediction = not on
    self.refresh()

  def local(self):
    # pylint: disable-next=import-outside-toplevel
    from fdc.ui import match_screens  # Circular: it imports this module.
    self.app.switch(match_screens.SelectScreen(self.app))

  def online(self):
    # pylint: disable-next=import-outside-toplevel
    from fdc.ui import online_screens  # Circular: it imports this module.
    self.app.switch(online_screens.OnlineHomeScreen(self.app))


class OptionsScreen(SubMenuScreen):
  """Video options: toggle the full effects chain."""
  TITLE = "OPCIONES"
  SUBTITLE = "FULL: todos los efectos.  SIN EFECTOS: más fluido en CPU."

  def __init__(self, app):
    super().__init__(app, [("", self.cycle), ("Volver", self.back)])
    self.refresh()

  def refresh(self):
    """The first button always names the mode in use."""
    self.menu.items[0] = (f"CALIDAD: {self.mode_name()}", self.cycle)

  def mode_name(self):
    """The name of the active mode."""
    return self.app.postfx.quality_mode_name()

  def cycle(self):
    """Next mode of the chain (F10 does the same inside a match)."""
    self.app.cycle_quality()
    self.refresh()

  def update(self, dt):
    super().update(dt)
    self.refresh()


class InfoScreen(Screen):
  """Screen that only shows information: Esc, Enter or the back button
    return to the home screen."""

  def __init__(self, app):
    super().__init__(app)
    self.back_button = BackButton(self.back)

  def back(self):
    self.app.audio.play("back")
    self.app.switch(self.app.home())

  def handle_event(self, ev):
    if self.back_button.handle_event(ev):
      return
    if ev.type == pygame.KEYDOWN and (ev.key in BACK_KEYS
                                      or ev.key in OK_KEYS):
      self.back()


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
class ControlsScreen(InfoScreen):
  """Keys of each player and general hints."""
  ACTION_NAMES = (("left", "Izquierda"), ("right", "Derecha"),
                  ("jump", "Saltar"), ("kick", "Patear"))
  TITLE_Y = 52                       # title (px)
  PLAYER_PANEL = (460, 290)          # box of each player (w, h) in px
  PLAYER_PANEL_X = (350, 930)        # horizontal centre of each box (px)
  PLAYER_PANEL_Y = 265               # vertical centre of the boxes (px)
  COLOR_BAR_H = 8                    # band with the player colour (px)
  HEADER_Y = 34                      # player header, from the box top
  FIRST_ACTION_Y = 84                # first action, from the box top
  ACTION_STEP = 48                   # px between actions
  ACTION_NAME_X = 20                 # action name, from the left edge
  KEY_X = 96                         # key centre, from the right edge
  INFO_PANEL = (1080, 240)           # box of hints (w, h) in px
  INFO_TOP = 428                     # top edge of that box (px)
  INFO_PADDING = 10                  # px of air inside the box
  INFO_LINE_H = 24                   # px between lines of the hints
  PARAGRAPH_GAP = 6                  # extra px between paragraphs

  def draw(self, surf):
    surf.blit(self.app.background, (0, 0))
    dim(surf, layout.VEIL_LIST)
    title(surf, "CONTROLES", (layout.CENTER_X, self.TITLE_Y))
    for i in (0, 1):
      self._player_panel(surf, i)
    info = pygame.Rect((0, 0), self.INFO_PANEL)
    info.midtop = (layout.CENTER_X, self.INFO_TOP)
    wrapped_lines(surf, _control_hints(), layout.FONT_SMALL,
                  panel(surf, info), self.INFO_PADDING, self.INFO_LINE_H,
                  self.PARAGRAPH_GAP)
    footer(surf, "Esc o Enter: volver")
    self.back_button.draw(surf, self.t)

  def _player_panel(self, surf, i):
    r = pygame.Rect((0, 0), self.PLAYER_PANEL)
    r.center = (self.PLAYER_PANEL_X[i], self.PLAYER_PANEL_Y)
    inner = panel(surf, r)
    color = config.PLAYER_COLORS[i]
    pygame.draw.rect(surf, color, (inner.left, inner.top, inner.width,
                                   self.COLOR_BAR_H))
    side = "izquierda" if i == 0 else "derecha"
    assets.draw_text(surf, f"JUGADOR {i + 1} ({side})", layout.FONT_TEXT,
                     (r.centerx, inner.top + self.HEADER_Y), color,
                     outline=palette.INK)
    self._actions(surf, inner, i)

  def _actions(self, surf, inner, i):
    for k, (action, name) in enumerate(self.ACTION_NAMES):
      y = inner.top + self.FIRST_ACTION_Y + k * self.ACTION_STEP
      assets.draw_text(surf, name, layout.FONT_TEXT,
                       (inner.left + self.ACTION_NAME_X, y), palette.INK,
                       anchor="midleft", outline=None)
      keycap(surf, (inner.right - self.KEY_X, y),
             ui_input.key_label(config.PLAYER_KEYS[i][action]))


def _control_hints():
  key = ui_input.key_label
  return [
      f"{key(config.PAUSE_KEY)}: pausa  -  {key(config.DEBUG_PANEL_KEY)}: "
      f"panel de depuración  -  {key(config.FULLSCREEN_KEY)}: pantalla "
      f"completa  -  {key(config.MUTE_KEY)}: silencio.",
      *CONTROL_HINTS]


# Fixed hints of the controls screen (after the line with the keys).
CONTROL_HINTS = (
    "Menús: W/S o flechas arriba/abajo; Enter, Espacio o P para elegir "
    "(también con el mouse).",
    "Elegir personaje: J1 con A/D y Espacio (W cancela); J2 con flechas "
    "y P (flecha arriba cancela).",
    "Mundialito y Online: valen las dos combinaciones. Online, Esc pide "
    "pausa (tras el próximo gol).",
    "Cabecear es tocar la pelota con la cabeza; la patada sale hacia "
    "donde mira el personaje.",
    "Aviso: muchos teclados no registran más de 3 o 4 teclas a la vez "
    "(\"ghosting\"). Si alguna combinación no responde es una limitación "
    "del teclado; las teclas se cambian en fdc/config.py.",
)


# ---------------------------------------------------------------------------
# Powers legend
# ---------------------------------------------------------------------------
class LegendScreen(InfoScreen):
  """Card of each power with its icon, description and duration."""
  TITLE_Y = 34                       # title (px)
  LEGEND_X0 = 150                    # x of the first colour legend text
  LEGEND_STEP = 380                  # px between the three legend texts
  LEGEND_Y = 84                      # vertical centre of the legend (px)
  SWATCH = 24                        # px: colour square of the legend
  SWATCH_GAP = 30                    # px between the square and its text
  RULE_Y = 114                       # line explaining how powers work
  ROWS = 9                           # powers per column
  CARD = (608, 54)                   # card of each power (w, h) in px
  CARD_X0 = 24                       # x of the first column (px)
  CARD_COL_STEP = 624                # px between columns
  CARD_Y0 = 134                      # y of the first card (px)
  CARD_ROW_STEP = 60                 # px between cards
  CATEGORY_BAR_W = 6                 # band with the category colour (px)
  ICON_SIZE = 48                     # px: icon of the power
  ICON_X = 12                        # icon, from the left edge of the card
  ICON_Y = 3                         # icon, from the top edge
  TEXT_X = 66                        # name and description, from the left
  NAME_Y = 6                         # name, from the top edge
  DESCRIPTION_Y = 26                 # description, from the top edge
  DURATION_MARGIN = 10               # duration, from the right edge
  LEGEND = ((config.CATEGORY_GOOD, "Verde: beneficia al receptor"),
            (config.CATEGORY_BAD, "Rojo: lo perjudica"),
            (config.CATEGORY_GLOBAL, "Violeta: cambia el partido"))

  def draw(self, surf):
    surf.blit(self.app.background, (0, 0))
    dim(surf, layout.VEIL_BOOT)
    title(surf, "PODERES", (layout.CENTER_X, self.TITLE_Y),
          layout.FONT_TITLE)
    self._legend(surf)
    for i, p in enumerate(config.POWERS):
      self._card(surf, i, p)
    footer(surf, "Esc o Enter: volver  -  Repetir un poder renueva su "
           "duración; uno opuesto lo reemplaza")
    self.back_button.draw(surf, self.t)

  def _legend(self, surf):
    """Meaning of the three colours and how powers are taken."""
    for k, (cat, label) in enumerate(self.LEGEND):
      self._legend_item(surf, k, cat, label)
    assets.draw_text(surf, "Se activan cuando la PELOTA toca el objeto. "
                     "Receptor = último jugador que la tocó.",
                     layout.FONT_SMALL, (layout.CENTER_X, self.RULE_Y),
                     palette.INK, outline=palette.WHITE)

  def _legend_item(self, surf, k, cat, label):
    x = self.LEGEND_X0 + k * self.LEGEND_STEP
    box = pygame.Rect(x - self.SWATCH_GAP, self.LEGEND_Y - self.SWATCH // 2,
                      self.SWATCH, self.SWATCH)
    retro.bevel_box(surf, box, config.CATEGORY_COLORS[cat], shadow=False)
    assets.draw_text(surf, label, layout.FONT_SMALL, (x, self.LEGEND_Y),
                     palette.INK, anchor="midleft", outline=palette.WHITE)

  def _card(self, surf, i, p):
    col, row = (0, i) if i < self.ROWS else (1, i - self.ROWS)
    r = pygame.Rect((self.CARD_X0 + col * self.CARD_COL_STEP,
                     self.CARD_Y0 + row * self.CARD_ROW_STEP), self.CARD)
    inner = retro.bevel_box(surf, r, palette.CREAM)
    color = config.CATEGORY_COLORS[p.category]
    pygame.draw.rect(surf, color, (inner.left, inner.top,
                                   self.CATEGORY_BAR_W, inner.height))
    surf.blit(icons.power_icon(p.id, self.ICON_SIZE),
              (inner.left + self.ICON_X, inner.top + self.ICON_Y))
    self._card_texts(surf, inner, p, color)

  def _card_texts(self, surf, inner, p, color):
    x = inner.left + self.TEXT_X
    assets.draw_text(surf, p.name, layout.FONT_SMALL,
                     (x, inner.top + self.NAME_Y), palette.INK,
                     anchor="topleft", outline=None)
    assets.draw_text(surf, p.description, layout.FONT_SMALL,
                     (x, inner.top + self.DESCRIPTION_Y), palette.INK_SOFT,
                     anchor="topleft", outline=None)
    dur = ("puntual" if p.duration <= 0
           else f"{p.duration:g} s".replace(".", ","))
    assets.draw_text(surf, dur, layout.FONT_SMALL,
                     (inner.right - self.DURATION_MARGIN,
                      inner.top + self.NAME_Y), color, anchor="topright",
                     outline=palette.INK)


# ---------------------------------------------------------------------------
# Simulation error
# ---------------------------------------------------------------------------
class ErrorScreen(Screen):
  """The simulation failed: message, technical detail and retry."""
  TRACE_LINES = 3                    # last lines of the technical error
  TRACE_MAX_CHARS = 110              # characters per line of that error
  # Retry and quit buttons (px).
  MENU_CENTER = (layout.CENTER_X, 560)
  MENU_W = 300                       # width of those buttons (px)
  BOX = (1040, 340)                  # message box (w, h) in px
  BOX_TOP = 80                       # top edge of the box (px)
  TITLE_Y = 36                       # title, from the box top
  MESSAGE_Y = 96                     # first message line, from the box top
  MESSAGE_MARGIN = 40                # px of air beside the message
  MESSAGE_LINE_H = 32                # px between message lines
  TRACE_GAP = 8                      # px between message and the detail
  HINT_BOTTOM = 18                   # hint, from the box bottom edge

  def __init__(self, app, message, detail=""):
    super().__init__(app)
    self.message = message
    tb = [ln for ln in (detail or "").strip().splitlines() if ln.strip()]
    self.detail = tb[-self.TRACE_LINES:] if tb else []
    items = [("Reintentar", self.retry), ("Salir", app.quit)]
    self.menu = Menu(items, self.MENU_CENTER, width=self.MENU_W)

  def enter(self):
    self.app.audio.crowd(False)
    self.app.input.capture = False

  def retry(self):
    self.app.restart_simulation()

  def handle_event(self, ev):
    self.menu.handle_event(ev, self.app.audio)

  def update(self, dt):
    super().update(dt)
    self.menu.update(dt)

  def draw(self, surf):
    surf.blit(self.app.background, (0, 0))
    dim(surf, layout.VEIL_ERROR)
    r = pygame.Rect((0, 0), self.BOX)
    r.midtop = (layout.CENTER_X, self.BOX_TOP)
    inner = panel(surf, r, face=palette.ERROR_PANEL, border=palette.RED)
    self._texts(surf, inner)
    assets.draw_text(surf, self._hint(), layout.FONT_SMALL,
                     (layout.CENTER_X, inner.bottom - self.HINT_BOTTOM),
                     palette.INK, outline=None)
    self.menu.draw(surf)

  def _texts(self, surf, inner):
    title(surf, "PROBLEMA CON LA SIMULACIÓN",
          (layout.CENTER_X, inner.top + self.TITLE_Y),
          layout.FONT_TITLE_S, palette.RED)
    y = inner.top + self.MESSAGE_Y
    width = inner.width - self.MESSAGE_MARGIN
    for ln in assets.wrap(self.message, layout.FONT_TEXT, width):
      assets.draw_text(surf, ln, layout.FONT_TEXT, (layout.CENTER_X, y),
                       palette.INK, outline=None)
      y += self.MESSAGE_LINE_H
    self._detail(surf, y + self.TRACE_GAP)

  def _detail(self, surf, y):
    """Last lines of the technical error."""
    for ln in self.detail:
      assets.draw_text(surf, ln[:self.TRACE_MAX_CHARS], layout.FONT_SMALL,
                       (layout.CENTER_X, y), palette.INK_SOFT,
                       outline=None)
      y += layout.TEXT_LINE_H

  def _hint(self):
    return ("La interfaz sigue funcionando: podés reintentar (se lanza "
            "un proceso nuevo) o salir.")


def fps_value(clock):
  """Measured FPS, or the target while there are no samples."""
  v = clock.get_fps()
  return v if v > 0 else FALLBACK_FPS
