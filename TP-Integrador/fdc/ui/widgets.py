"""Retro widgets to type: user name, room name and password."""
import pygame

from fdc.ui import assets
from fdc.ui import layout
from fdc.ui import palette
from fdc.ui import pixelfont
from fdc.ui import retro

DEFAULT_MAX_LEN = 16        # characters that fit in a field by default
LABEL_GAP = 14              # px between the label and the top of the field
FOCUS_RING = 6              # px the golden frame sticks out of the field
FOCUS_LINE = 3              # px: thickness of that frame
TEXT_PADDING = 10           # px between the field edge and the text
CARET_W = 4                 # px: width of the text caret
CARET_H = 24                # px: height of the text caret
CARET_GAP = 2               # px between the last letter and the caret
CHECK_SIZE = 32             # px: side of the check box
CHECK_MARK_INSET = 8        # px between the box edge and the "checked" square
CHECK_LABEL_GAP = 14        # px between the box and its text
ENTER_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER)

FONT_CHARS = frozenset(pixelfont.GLYPHS) | {" "}


class TextField:
    """One-line text field (with hidden letters for passwords)."""

    # Text: TEXTINPUT is the right event (accents, capitals, keyboard
    # layout). If the environment does not produce it (some browsers), the
    # KEYDOWN character is used; once a TEXTINPUT shows up, only that one is
    # used. Shared by every field.
    textinput_seen = False

    def __init__(self, rect, label, max_len=DEFAULT_MAX_LEN, password=False,
                 allowed=None, value="", placeholder="", sticky=False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.max_len = max_len
        self.password = password
        self.allowed = allowed or (lambda ch: ch in FONT_CHARS)
        self.value = value
        self.placeholder = placeholder
        self.focused = False
        self.enabled = True
        # Only field of the screen: a click outside does not unfocus it.
        self.sticky = sticky
        self._last_key_char = None

    def focus(self, on=True):
        if on and not self.focused:
            pygame.key.start_text_input()
        self.focused = on and self.enabled

    def _add(self, txt):
        for ch in txt:
            if len(self.value) < self.max_len and self.allowed(ch):
                self.value += ch

    def handle_event(self, ev):
        """True if it used the event; "submit" with Enter; "tab" with Tab."""
        if not self.enabled:
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            hit = self.rect.collidepoint(ev.pos)
            self.focus(hit or self.sticky)
            return hit
        if not self.focused:
            return False
        if ev.type == pygame.TEXTINPUT:
            return self._text_input(ev.text)
        if ev.type == pygame.KEYDOWN:
            return self._key(ev)
        return False

    def _text_input(self, txt):
        if not TextField.textinput_seen:
            TextField.textinput_seen = True
            if self._last_key_char == txt:   # it came in with the KEYDOWN
                return True
        self._add(txt)
        return True

    def _key(self, ev):
        if ev.key == pygame.K_ESCAPE:
            return False            # Esc is handled by the screen (back)
        if ev.key == pygame.K_BACKSPACE:
            self.value = self.value[:-1]
            return True
        if ev.key in ENTER_KEYS or ev.key == pygame.K_TAB:
            return "submit" if ev.key in ENTER_KEYS else "tab"
        ch = getattr(ev, "unicode", "")
        if not TextField.textinput_seen and ch and ch.isprintable():
            self._add(ch)
            self._last_key_char = ch
        return True                 # letters do not trigger other buttons

    def draw(self, surf, t=0.0):
        if self.label:
            self._draw_label(surf)
        inner = retro.bevel_box(surf, self.rect, self._face())
        if self.focused:
            pygame.draw.rect(surf, palette.GOLD,
                             self.rect.inflate(FOCUS_RING, FOCUS_RING),
                             FOCUS_LINE)
        shown = "•" * len(self.value) if self.password else self.value
        self._draw_text(surf, inner, shown)
        if self.focused and int(t * layout.CARET_HZ) % 2 == 0:
            _draw_caret(surf, inner, shown)

    def _draw_label(self, surf):
        assets.draw_text(surf, self.label, layout.FONT_SMALL,
                         (self.rect.left, self.rect.top - LABEL_GAP),
                         palette.INK, anchor="midleft", outline=palette.WHITE)

    def _face(self):
        if self.focused:
            return palette.WHITE
        return palette.CREAM if self.enabled else palette.CREAM_DARK

    def _draw_text(self, surf, inner, shown):
        x = inner.left + TEXT_PADDING
        if shown:
            assets.draw_text(surf, shown, layout.FONT_TEXT, (x, inner.centery),
                             palette.INK, anchor="midleft", outline=None)
        elif self.placeholder and not self.focused:
            assets.draw_text(surf, self.placeholder, layout.FONT_SMALL,
                             (x, inner.centery), palette.INK_SOFT,
                             anchor="midleft", outline=None)



def _draw_caret(surf, inner, shown):
    x = inner.left + TEXT_PADDING
    if shown:
        x += assets.text_width(shown, layout.FONT_TEXT) + CARET_GAP
    pygame.draw.rect(surf, palette.INK, (x, inner.centery - CARET_H // 2,
                                         CARET_W, CARET_H))


class CheckBox:
    """A box to tick (for example "Con contraseña")."""

    def __init__(self, rect, label, value=False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.value = value
        self.hover = False

    def handle_event(self, ev):
        """Toggles on a click. True if it changed."""
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(ev.pos)
        elif (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1
              and self.rect.collidepoint(ev.pos)):
            self.value = not self.value
            return True
        return False

    def draw(self, surf):
        box = pygame.Rect(self.rect.left, self.rect.centery - CHECK_SIZE // 2,
                          CHECK_SIZE, CHECK_SIZE)
        inner = retro.bevel_box(surf, box,
                                palette.GOLD if self.hover else palette.WHITE,
                                shadow=False)
        if self.value:
            pygame.draw.rect(surf, palette.INK,
                             inner.inflate(-CHECK_MARK_INSET,
                                           -CHECK_MARK_INSET))
        assets.draw_text(surf, self.label, layout.FONT_TEXT,
                         (box.right + CHECK_LABEL_GAP, box.centery),
                         palette.INK, anchor="midleft", outline=palette.WHITE)
