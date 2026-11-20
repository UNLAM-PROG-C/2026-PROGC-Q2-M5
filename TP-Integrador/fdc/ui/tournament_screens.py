"""Tournament screens (one player against the computer, local only).

Flow: choose a character -> tournament bracket -> match -> result -> ...
The progress lives in app.tournament while the game is open:
  * finishing a match and going to the menu does NOT lose the progress (it
    continues from the play menu);
  * going to the menu from the PAUSE of a match is quitting: the tournament
    is lost.
"""
import random

import pygame

from fdc import bot
from fdc import config
from fdc import protocol
from fdc import tournament as cup
from fdc.ui import assets
from fdc.ui import characters
from fdc.ui import layout
from fdc.ui import match_screens
from fdc.ui import palette
from fdc.ui import retro
from fdc.ui import screens
from fdc.ui import sprites

CHARACTER_IDS = characters.CHARACTER_IDS
HUMAN = cup.HUMAN_SLOT
BOT = cup.BOT_SLOT
RUNNER_UP = 2                      # place of the one who loses the final
BOT_SEED_RANGE = 10 ** 9           # possible bot seeds when --seed is not set
MENU_W = 420                       # width of the tournament buttons (px)
MENU_BUTTON_H = 50                 # height of those buttons (px)
MENU_GAP = 10                      # px between those buttons
TITLE_Y = 40                       # tournament title (px)
CONFIRM_KEYS = (pygame.K_SPACE, pygame.K_p, pygame.K_RETURN,
                pygame.K_KP_ENTER)
LEFT_KEYS = (pygame.K_a, pygame.K_LEFT)
RIGHT_KEYS = (pygame.K_d, pygame.K_RIGHT)

# --- the cup, in native px (drawn small and scaled without smoothing)
TROPHY_SIZE = (26, 44)             # canvas of the cup (width, height)
TROPHY_GOLD = (240, 190, 40)       # gold
TROPHY_GOLD_DARK = (190, 135, 20)  # gold in shade (outlines)
TROPHY_GOLD_LIGHT = (255, 236, 140)  # shines
TROPHY_GREEN = (40, 140, 70)       # green bands of the base
TROPHY_GLOBE = (13, 9)             # centre of the globe on top
TROPHY_GLOBE_R = 8                 # radius of the globe (with outline)
# Lines of the globe (horizontal and vertical), native px.
TROPHY_MERIDIANS = (((6, 9), (20, 9)), ((13, 2), (13, 16)))
TROPHY_GLOBE_SHINE = (9, 4, 3, 2)  # shine of the globe (x, y, w, h)
# Body: trapeze that narrows downwards, native px.
TROPHY_BODY = [(7, 15), (19, 15), (16, 30), (10, 30)]
TROPHY_SPIRALS_Y = (19, 23, 27)    # height of the spirals of the body
TROPHY_SPIRAL_X = (9, 17)          # the spirals go from x = 9 to x = 17...
TROPHY_SPIRAL_RISE = 2             # ...rising 2 px
TROPHY_BODY_SHINE = (11, 17, 1, 10)  # vertical shine of the body
# The base, from top to bottom: (colour, (x, y, width, height)).
TROPHY_BASE = ((TROPHY_GOLD, (7, 30, 12, 3)), (TROPHY_GREEN, (6, 33, 14, 3)),
               (TROPHY_GOLD, (6, 36, 14, 2)), (TROPHY_GREEN, (5, 38, 16, 3)),
               (TROPHY_GOLD_DARK, (5, 41, 16, 2)))
TROPHY_SCALE = 4                   # default scale of the cup
RULES = ("Sólo avanzás si ganás. Si perdés, quedás eliminado.",
         "Cada rival es más difícil que el anterior.",
         "Si el partido termina empatado: gol de oro.",
         "Jugás a la DERECHA: valen A/D/W + Espacio",
         "y también las flechas + P.")


def _name(cid):
  return characters.short_name(characters.CHARACTERS_BY_ID[cid])


def _title(surf):
  screens.title(surf, "MUNDIALITO", (layout.CENTER_X, TITLE_Y),
                layout.FONT_TITLE_L)


def _stage_color(i):
  """Band of a stage: groups, knockout or the final."""
  if i < cup.GROUP_STAGES:
    return palette.GREEN
  return palette.RED if i == len(cup.STAGES) - 1 else palette.BLUE


def _to_play_menu(app):
  app.audio.play("back")
  app.switch(screens.PlayMenuScreen(app))


def open_tournament(app):
  """Entry from the play menu: continues the tournament or starts one."""
  t = getattr(app, "tournament", None)
  if t is not None and not t.finished:
    app.switch(HubScreen(app))
  else:
    app.tournament = None
    app.switch(PickScreen(app))


def draw_trophy(surf, center, k=TROPHY_SCALE):
  """World Cup in pixel art (drawn at native size, scaled k times)."""
  s = pygame.Surface(TROPHY_SIZE, pygame.SRCALPHA)
  _globe(s)
  _cup_body(s)
  for color, rect in TROPHY_BASE:
    pygame.draw.rect(s, color, rect)
  w, h = TROPHY_SIZE
  img = pygame.transform.scale(s, (w * k, h * k))
  surf.blit(img, img.get_rect(center=center))


def _cup_body(s):
  pygame.draw.polygon(s, TROPHY_GOLD, TROPHY_BODY)
  pygame.draw.polygon(s, TROPHY_GOLD_DARK, TROPHY_BODY, 1)
  x0, x1 = TROPHY_SPIRAL_X
  for y in TROPHY_SPIRALS_Y:
    pygame.draw.line(s, TROPHY_GOLD_DARK, (x0, y),
                     (x1, y - TROPHY_SPIRAL_RISE))
  s.fill(TROPHY_GOLD_LIGHT, TROPHY_BODY_SHINE)


def _globe(s):
  pygame.draw.circle(s, TROPHY_GOLD_DARK, TROPHY_GLOBE, TROPHY_GLOBE_R)
  pygame.draw.circle(s, TROPHY_GOLD, TROPHY_GLOBE, TROPHY_GLOBE_R - 1)
  for a, b in TROPHY_MERIDIANS:
    pygame.draw.line(s, TROPHY_GOLD_DARK, a, b)
  s.fill(TROPHY_GOLD_LIGHT, TROPHY_GLOBE_SHINE)


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _draw_player(app, surf, cid, facing, pose, color, scale, feet):
  ang, bob = pose
  img, (fx, fy) = app.sprites.player(cid, facing, ang, bob, color, False,
                                     scale)
  surf.blit(img, (feet[0] - fx, feet[1] - fy))


# ---------------------------------------------------------------------------
# Choose a character (one person)
# ---------------------------------------------------------------------------
class PickScreen(screens.Screen):
  """The player chooses who to play with; the rest are the rivals."""
  PLAYER_X = 1030                    # x of the chosen one (plays right)
  OK_SIZE = (220, 48)                # play button (width, height) in px
  OK_Y = 426                         # vertical centre of that button (px)
  SUBTITLE_Y = 88                    # explanation below the title (px)
  INFO = (70, 120, 640, 290)         # rules box (x, y, width, height)
  INFO_PADDING = 12                  # px of air inside the box
  RULES_TOP = 10                     # first rule, from the box top (px)
  RULE_STEP = 26                     # px between rules
  STAGES_PER_ROW = 3                 # tournament stages per row
  STAGE_TOP = 150                    # first row of stages, from box top
  STAGE_SIZE = (190, 44)             # each stage (width, height) in px
  STAGE_STEP = (200, 54)             # px between stages (x, y)
  STAGE_BAR = (2, 6)                 # colour band (gap to the edge, width)
  STAGE_TEXT_X = 16                  # stage name, from the left edge (px)
  PEDESTAL = (200, 18)               # pedestal below the character (w, h)
  PEDESTAL_TOP = 372                 # top edge of the pedestal (px)
  FEET_Y = 376                       # y of the character feet (px)
  PLAYER_SCALE = 1.9                 # size of the character
  NAME_Y = 132                       # name of the chosen character (px)

  def __init__(self, app):
    super().__init__(app)
    last = (app.last_characters[1] if app.last_characters
            else CHARACTER_IDS[0])
    self.cursor = CHARACTER_IDS.index(last)
    self.ok_rect = pygame.Rect((0, 0), self.OK_SIZE)
    self.ok_rect.center = (self.PLAYER_X, self.OK_Y)
    self.hover_ok = False
    self.back_button = screens.BackButton(self.back)

  def back(self):
    _to_play_menu(self.app)

  def move(self, d):
    self.cursor = (self.cursor + d) % len(CHARACTER_IDS)
    self.app.audio.play("select")

  def confirm(self):
    self.app.audio.play("confirm")
    cid = CHARACTER_IDS[self.cursor]
    self.app.tournament = cup.Tournament(
        cid, random.Random(self.app.options.seed))
    self.app.switch(HubScreen(self.app))

  def handle_event(self, ev):
    if self.back_button.handle_event(ev):
      return
    if ev.type == pygame.KEYDOWN:
      self._key(ev.key)
    elif ev.type == pygame.MOUSEMOTION:
      self.hover_ok = self.ok_rect.collidepoint(ev.pos)
    elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
      self._click(ev.pos)

  def _key(self, key):
    if key in screens.BACK_KEYS:
      self.back()
    elif key in LEFT_KEYS:
      self.move(-1)
    elif key in RIGHT_KEYS:
      self.move(1)
    elif key in CONFIRM_KEYS:
      self.confirm()

  def _click(self, pos):
    if self.ok_rect.collidepoint(pos):
      self.confirm()
      return
    for k in range(len(CHARACTER_IDS)):
      if match_screens.card_rect(k).collidepoint(pos):
        self.cursor = k
        self.app.audio.play("select")

  def draw(self, surf):
    surf.blit(self.app.background, (0, 0))
    screens.dim(surf, layout.VEIL_OVERLAY)
    _title(surf)
    inner = screens.panel(surf, pygame.Rect(self.INFO))
    self._rules(surf, inner)
    for i, stage in enumerate(cup.STAGES):
      self._stage(surf, inner, i, stage)
    self._chosen(surf)
    self._cards(surf)
    self._footer(surf)

  def _footer(self, surf):
    screens.footer(surf, "A/D o flechas: elegir  -  Espacio, P o Enter: "
                   "confirmar  -  Esc: volver  -  Mouse: clic")
    self.back_button.draw(surf, self.t)

  def _rules(self, surf, inner):
    assets.draw_text(surf, "Elegí tu personaje: vas a enfrentar a los "
                     f"otros {len(cup.STAGES)}, uno por uno.",
                     layout.FONT_SMALL, (layout.CENTER_X, self.SUBTITLE_Y),
                     palette.INK, outline=palette.WHITE)
    pad = self.INFO_PADDING
    for i, ln in enumerate(RULES):
      assets.draw_text(surf, ln, layout.FONT_SMALL,
                       (inner.left + pad,
                        inner.top + self.RULES_TOP + i * self.RULE_STEP),
                       palette.INK, anchor="topleft", outline=None)

  def _stage(self, surf, inner, i, stage):
    """Box of stage i with a band: groups, knockout or final."""
    col = _stage_color(i)
    step_x, step_y = self.STAGE_STEP
    bar_gap, bar_w = self.STAGE_BAR
    row, col_k = divmod(i, self.STAGES_PER_ROW)
    r = pygame.Rect((inner.left + self.INFO_PADDING + col_k * step_x,
                     inner.top + self.STAGE_TOP + row * step_y),
                    self.STAGE_SIZE)
    retro.bevel_box(surf, r, palette.CREAM, shadow=False)
    pygame.draw.rect(surf, col, (r.left + bar_gap, r.top + bar_gap, bar_w,
                                 r.height - 2 * bar_gap))
    assets.draw_text(surf, stage, layout.FONT_SMALL,
                     (r.left + self.STAGE_TEXT_X, r.centery), palette.INK,
                     anchor="midleft", outline=None)

  def _chosen(self, surf):
    """Pedestal, character, name and the play button."""
    cid = CHARACTER_IDS[self.cursor]
    ped = pygame.Rect((0, 0), self.PEDESTAL)
    ped.midtop = (self.PLAYER_X, self.PEDESTAL_TOP)
    retro.bevel_box(surf, ped, palette.STRUCT)
    _draw_player(self.app, surf, cid, match_screens.FACING[HUMAN],
                 sprites.idle_pose(self.t), config.PLAYER_COLORS[HUMAN],
                 self.PLAYER_SCALE, (self.PLAYER_X, self.FEET_Y))
    assets.draw_text(surf, _name(cid).upper(), layout.FONT_LARGE,
                     (self.PLAYER_X, self.NAME_Y), palette.GOLD,
                     kind="title", outline=palette.INK, shadow=True)
    screens.button(surf, self.ok_rect, "¡A JUGAR!", self.hover_ok, True,
                   layout.FONT_TEXT, self.t)

  def _cards(self, surf):
    for k in range(len(CHARACTER_IDS)):
      rr = match_screens.draw_card(surf, self.app.sprites, k,
                                   k == self.cursor)
      if k == self.cursor:
        frame = rr.inflate(2 * match_screens.SELECTION_MARGIN,
                           2 * match_screens.SELECTION_MARGIN)
        pygame.draw.rect(surf, config.PLAYER_COLORS[HUMAN], frame,
                         match_screens.SELECTION_LINE)


# ---------------------------------------------------------------------------
# Tournament bracket
# ---------------------------------------------------------------------------
class HubScreen(screens.Screen):
  """Bracket with the six rivals and the next match."""
  MENU_CENTER = (layout.CENTER_X, 560)   # play, menu and quit buttons
  SUBTITLE_Y = 86                    # who you play with and next rival
  STAGE_W = 186                      # px: width of each bracket column
  STAGE_GAP = 20                     # px between columns
  STAGE_TOP = 140                    # top edge of the columns (px)
  STAGE_H = 300                      # px: height of each column
  CURRENT_BOB_PX = 6                 # px the next match column hops...
  CURRENT_BOB_HZ = 3                 # ...and how many times a second
  GROUP_Y = 12                       # groups/knockout, from column top
  STAGE_NAME_Y = 36                  # stage name, from column top (px)
  PORTRAIT_Y = 58                    # rival portrait, from column top (px)
  # White veil over the rivals still to come (r, g, b, a).
  UPCOMING_VEIL = (255, 255, 255, 120)
  RIVAL_NAME_GAP = 14                # rival name, below the portrait (px)
  STATUS_BOTTOM = 14                 # won/next line, from column bottom
  TROPHY_CENTER = (1196, 560)        # small cup, bottom right (px)
  TROPHY_SCALE = 2                   # size of that cup

  def __init__(self, app):
    super().__init__(app)
    t = app.tournament
    self.menu = screens.Menu(
        [(f"Jugar {t.stage_name}", self.play),
         ("Menú principal", self.to_menu),
         ("Abandonar Mundialito", self.abandon)], self.MENU_CENTER,
        width=MENU_W, height=MENU_BUTTON_H, gap=MENU_GAP)
    self.back_button = screens.BackButton(self.back)

  def back(self):
    """Back to the play menu (the progress is kept)."""
    _to_play_menu(self.app)

  def play(self):
    self.app.switch(TournamentMatchScreen(self.app, self.app.tournament))

  def to_menu(self):
    self.app.switch(screens.MenuScreen(self.app))   # progress is kept

  def abandon(self):
    self.app.tournament = None
    self.app.switch(screens.MenuScreen(self.app))

  def handle_event(self, ev):
    if self.back_button.handle_event(ev):
      return
    if ev.type == pygame.KEYDOWN and ev.key in screens.BACK_KEYS:
      self.back()
      return
    self.menu.handle_event(ev, self.app.audio)

  def update(self, dt):
    super().update(dt)
    self.menu.update(dt)

  def draw(self, surf):
    t = self.app.tournament
    surf.blit(self.app.background, (0, 0))
    screens.dim(surf, layout.VEIL_OVERLAY)
    _title(surf)
    self._subtitle(surf, t)
    w, gap = self.STAGE_W, self.STAGE_GAP
    n = len(cup.STAGES)
    x0 = layout.CENTER_X - (n * w + (n - 1) * gap) / 2
    for i, (stage, rival) in enumerate(zip(cup.STAGES, t.rivals)):
      r = pygame.Rect(x0 + i * (w + gap), self.STAGE_TOP, w, self.STAGE_H)
      self._column(surf, t, i, r, (stage, rival))
    self._bottom(surf)

  def _subtitle(self, surf, t):
    assets.draw_text(surf, f"Jugás con {_name(t.player)}  -  Próximo: "
                     f"{t.stage_name} contra {_name(t.rival)} "
                     f"(dificultad {bot.LEVELS[t.level]['name']})",
                     layout.FONT_SMALL, (layout.CENTER_X, self.SUBTITLE_Y),
                     palette.INK, outline=palette.WHITE)

  def _bottom(self, surf):
    draw_trophy(surf, self.TROPHY_CENTER, self.TROPHY_SCALE)
    self.menu.draw(surf)
    screens.footer(surf, "Volver o ir al menú guarda tu progreso.  "
                   "Abandonar lo descarta.")
    self.back_button.draw(surf, self.t)

  # pylint: disable-next=too-many-arguments,too-many-positional-arguments
  def _column(self, surf, t, i, r, stage_rival):
    """Column of stage i: name, rival portrait and status."""
    current = i == t.stage
    done = i < len(t.results)
    if current:
      face = palette.GOLD
    else:
      face = (palette.CREAM if done or i < t.stage
              else palette.CREAM_DARK)
    bob = (self.CURRENT_BOB_PX
           if current and int(self.t * self.CURRENT_BOB_HZ) % 2 else 0)
    inner = retro.bevel_box(surf, r.move(0, -bob), face)
    self._column_texts(surf, inner, i, stage_rival[0])
    pr = self._portrait(surf, inner, stage_rival[1], done or current)
    self._status(surf, t, i, inner, (done, current, pr))

  def _column_texts(self, surf, inner, i, stage):
    group = "GRUPOS" if i < cup.GROUP_STAGES else "ELIMINACIÓN"
    assets.draw_text(surf, group, layout.FONT_SMALL,
                     (inner.centerx, inner.top + self.GROUP_Y),
                     palette.INK_SOFT, outline=None)
    assets.draw_text(surf, stage, layout.FONT_SMALL,
                     (inner.centerx, inner.top + self.STAGE_NAME_Y),
                     palette.INK, outline=None)

  def _portrait(self, surf, inner, rival, seen):
    """Rival portrait (veiled if it is still to come)."""
    portrait = self.app.sprites.portrait(rival)
    pr = portrait.get_rect(midtop=(inner.centerx,
                                   inner.top + self.PORTRAIT_Y))
    surf.blit(portrait, pr)
    pygame.draw.rect(surf, palette.INK, pr, layout.FRAME_LINE)
    if not seen:
      veil = pygame.Surface(pr.size, pygame.SRCALPHA)
      veil.fill(self.UPCOMING_VEIL)
      surf.blit(veil, pr)
    return pr

  # pylint: disable-next=too-many-arguments,too-many-positional-arguments
  def _status(self, surf, t, i, inner, flags):
    """Rival name and whether that match was won or is next."""
    done, current, pr = flags
    assets.draw_text(surf, _name(t.rivals[i]).upper(), layout.FONT_SMALL,
                     (inner.centerx, pr.bottom + self.RIVAL_NAME_GAP),
                     palette.INK, outline=None)
    status_y = inner.bottom - self.STATUS_BOTTOM
    if done:
      _won(surf, t.results[i], (inner.centerx, status_y))
    elif current:
      assets.draw_text(surf, "PRÓXIMO", layout.FONT_SMALL,
                       (inner.centerx, status_y), palette.RED,
                       outline=palette.WHITE)


def _won(surf, result, pos):
  _, _, mine, theirs = result
  assets.draw_text(surf, f"GANADO {mine}-{theirs}", layout.FONT_SMALL, pos,
                   palette.GREEN, outline=palette.INK)


# ---------------------------------------------------------------------------
# Tournament match
# ---------------------------------------------------------------------------
class TournamentMatchScreen(match_screens.MatchScreen):
  """A match against the bot, with golden goal (hooks of MatchScreen)."""
  # Stage sign at the bottom centre (width, height) in px.
  STAGE_TAG = (330, 34)
  STAGE_TAG_BOTTOM = 6               # px between that sign and the bottom
  VIEWER = 0                         # the human is always P1 here

  def __init__(self, app, tournament):
    self.tournament = tournament
    chars = [None, None]
    chars[BOT] = tournament.rival
    chars[HUMAN] = tournament.player
    super().__init__(app, chars)
    seed = (app.options.seed if app.options.seed is not None
            else random.randrange(BOT_SEED_RANGE))
    self.bot = bot.Bot(BOT, tournament.level, seed + tournament.stage)
    self._dt = 1 / config.UI_FPS

  # hooks
  def pause_items(self):
    return [("Continuar", self.resume),
            ("Abandonar Mundialito", self.abandon)]

  def extra_payload(self):
    return {"golden_goal": True}

  def controls(self, active):
    out = [None, None]
    out[HUMAN] = self.app.input.snapshot_single(active)
    out[BOT] = self.bot.controls(self.state, self._dt)
    return out

  def update(self, dt):
    self._dt = dt
    super().update(dt)

  def on_match_over(self):
    score = self.end_info["score"]
    won = self.tournament.record(score[HUMAN], score[BOT])
    self.app.switch(TournamentResultScreen(self.app, self.tournament,
                                           score, won))

  def abandon(self):
    """Going to the menu from the pause = quitting the tournament."""
    self.app.tournament = None
    self._send(protocol.CMD_END)
    self.app.switch(screens.MenuScreen(self.app))

  def draw(self, surf):
    super().draw(surf)
    if self.state is not None and self.pause_state is None:
      r = pygame.Rect((0, 0), self.STAGE_TAG)
      r.midbottom = (layout.CENTER_X,
                     layout.SCREEN_H - self.STAGE_TAG_BOTTOM)
      inner = retro.bevel_box(surf, r, palette.CREAM, shadow=False)
      assets.draw_text(surf, "MUNDIALITO - "
                       f"{self.tournament.stage_name.upper()}",
                       layout.FONT_SMALL, inner.center, palette.INK,
                       outline=None)


# ---------------------------------------------------------------------------
# Result of each match
# ---------------------------------------------------------------------------
class TournamentResultScreen(screens.Screen):
  """Won, eliminated or champion of the world."""
  MENU_CENTER = (layout.CENTER_X, 590)   # next and menu buttons (px)
  CONFETTI_EVERY = 1.2               # s between confetti when winning
  CONFETTI_AT = (layout.CENTER_X, 300)   # where the confetti comes from
  HEADLINE_Y = 70                    # champion/won/eliminated sign (px)
  TROPHY_CENTER = (700, 300)         # big cup of the champion (px)
  TROPHY_SCALE = 5                   # size of that cup
  CHAMPION_FEET = (500, 400)         # feet of the champion, by the cup
  CHAMPION_SCALE = 2.2               # size of the champion
  CHAMPION_TEXT_Y = 470              # line below the champion (px)
  SCORE_CENTER = (layout.CENTER_X, 250)   # board with the result (px)
  SCORE_W = 340                      # width of the board (px)
  SUMMARY_Y = 330                    # summary of the match (px)
  NEXT_Y = 380                       # next stage and rival (px)
  PLACE_Y = 384                      # final place when eliminated (px)
  PLAYER_X = {BOT: 220, HUMAN: 1060}   # x of each player (px)
  FEET_Y = 470                       # y of the players feet (px)
  PLAYER_SCALE = 1.8                 # size of the players
  NAME_Y = 494                       # name of each player (px)

  def __init__(self, app, tournament, score, won):
    super().__init__(app)
    self.t_ = tournament
    self.score = score
    self.won = won
    self.confetti_t = 0.0
    if tournament.finished:
      app.tournament = None
    self.menu = screens.Menu(self._items(), self.MENU_CENTER, width=MENU_W,
                             height=MENU_BUTTON_H, gap=MENU_GAP)

  def _items(self):
    status = self.t_.status
    if status == cup.CHAMPION:
      first = ("Jugar otro Mundialito", self.again)
    elif status == cup.ELIMINATED:
      first = ("Empezar de nuevo", self.again)
    else:
      first = ("Siguiente partido", self.next_match)
    return [first, ("Menú principal", self.to_menu)]

  def enter(self):
    self.app.audio.crowd(False)
    self.app.fx.clear()
    if self.t_.status == cup.CHAMPION:
      self.app.audio.play("goal")

  def next_match(self):
    self.app.switch(TournamentMatchScreen(self.app, self.t_))

  def again(self):
    self.app.switch(PickScreen(self.app))

  def to_menu(self):
    # If the tournament goes on, it is kept.
    self.app.switch(screens.MenuScreen(self.app))

  def handle_event(self, ev):
    self.menu.handle_event(ev, self.app.audio)

  def update(self, dt):
    super().update(dt)
    self.menu.update(dt)
    self.app.fx.update(dt)
    if self.won:
      self.confetti_t -= dt
      if self.confetti_t <= 0:
        self.confetti_t = self.CONFETTI_EVERY
        self.app.fx.confetti(*self.CONFETTI_AT, [
            config.PLAYER_COLORS[HUMAN], palette.WHITE, palette.GOLD])

  def draw(self, surf):
    t = self.t_
    surf.blit(self.app.background, (0, 0))
    screens.dim(surf, layout.VEIL_RESULT)
    if t.status == cup.CHAMPION:
      self._champion(surf, t)
    else:
      self._match_result(surf, t)
    self.app.fx.draw(surf)
    self.menu.draw(surf)
    if t.status not in (cup.CHAMPION, cup.ELIMINATED):
      screens.footer(surf, "Si vas al menú, el Mundialito queda "
                     "guardado y lo seguís desde Jugar > Mundialito.")

  def _champion(self, surf, t):
    screens.title(surf, "¡CAMPEÓN DEL MUNDO!",
                  (layout.CENTER_X, self.HEADLINE_Y), layout.FONT_TITLE_L)
    draw_trophy(surf, self.TROPHY_CENTER, self.TROPHY_SCALE)
    _draw_player(self.app, surf, t.player, 1,
                 sprites.celebrate_pose(self.t),
                 config.PLAYER_COLORS[HUMAN], self.CHAMPION_SCALE,
                 self.CHAMPION_FEET)
    assets.draw_text(surf, f"{_name(t.player)} ganó los "
                     f"{len(cup.STAGES)} partidos del Mundialito",
                     layout.FONT_TEXT,
                     (layout.CENTER_X, self.CHAMPION_TEXT_Y), palette.INK,
                     outline=palette.WHITE)

  def _match_result(self, surf, t):
    stage, rival, mine, theirs = t.results[-1]
    self._headline(surf)
    screens.scoreboard(surf, self.SCORE_CENTER, self.SCORE_W,
                       f"{theirs}-{mine}")
    assets.draw_text(surf, f"{stage}: {_name(rival)} {theirs} - {mine} "
                     f"{_name(t.player)}", layout.FONT_TEXT,
                     (layout.CENTER_X, self.SUMMARY_Y), palette.INK,
                     outline=palette.WHITE)
    self._next_or_place(surf, t)
    for slot in (BOT, HUMAN):
      self._player(surf, slot, rival if slot == BOT else t.player)

  def _headline(self, surf):
    head = "¡GANASTE!" if self.won else "ELIMINADO"
    screens.title(surf, head, (layout.CENTER_X, self.HEADLINE_Y),
                  layout.FONT_TITLE_XL,
                  palette.GREEN if self.won else palette.RED)

  def _next_or_place(self, surf, t):
    if self.won:
      assets.draw_text(surf, f"Pasás a {t.stage_name} contra "
                       f"{_name(t.rival)}", layout.FONT_TEXT,
                       (layout.CENTER_X, self.NEXT_Y), palette.INK,
                       outline=palette.WHITE)
      return
    pos = t.position
    extra = " (subcampeón)" if pos == RUNNER_UP else ""
    assets.draw_text(surf, f"Terminaste en el {cup.ordinal(pos)} "
                     f"puesto{extra}", layout.FONT_LARGE,
                     (layout.CENTER_X, self.PLACE_Y), palette.GOLD,
                     kind="title", outline=palette.INK, shadow=True)

  def _player(self, surf, slot, cid):
    x = self.PLAYER_X[slot]
    happy = (slot == HUMAN) == self.won
    pose = sprites.celebrate_pose(self.t) if happy else (0, 0)
    _draw_player(self.app, surf, cid, match_screens.FACING[slot], pose,
                 config.PLAYER_COLORS[slot], self.PLAYER_SCALE,
                 (x, self.FEET_Y))
    assets.draw_text(surf, _name(cid), layout.FONT_TEXT,
                     (x, self.NAME_Y), config.PLAYER_COLORS[slot],
                     outline=palette.INK)
