"""Widgets retro para escribir: nombre de usuario, nombre de sala y contraseña."""
import pygame

from . import palette as C
from . import pixelfont
from .assets import draw_text, text_width
from .retro import bevel_box

FONT_CHARS = frozenset(pixelfont.G) | {" "}

# Texto: TEXTINPUT es lo correcto (acentos, mayúsculas, distribución del
# teclado). Si el entorno no lo genera (algunos navegadores), se usa el
# carácter del KEYDOWN; en cuanto aparece un TEXTINPUT se pasa a usar sólo ese.
_textinput_seen = False


class TextField:
    def __init__(self, rect, label, max_len=16, password=False, allowed=None, value="", placeholder="",
                 sticky=False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.max_len = max_len
        self.password = password
        self.allowed = allowed or (lambda ch: ch in FONT_CHARS)
        self.value = value
        self.placeholder = placeholder
        self.focused = False
        self.enabled = True
        self.sticky = sticky          # único campo de la pantalla: un clic afuera no lo desactiva
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
        """True si usó el evento; "submit" con Enter; "tab" con Tab."""
        global _textinput_seen
        if not self.enabled:
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            hit = self.rect.collidepoint(ev.pos)
            self.focus(hit or self.sticky)
            return hit
        if not self.focused:
            return False
        if ev.type == pygame.TEXTINPUT:
            if not _textinput_seen:
                _textinput_seen = True
                if self._last_key_char == ev.text:   # ya entró por el KEYDOWN de la misma tecla
                    return True
            self._add(ev.text)
            return True
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                return False                        # Esc lo maneja la pantalla (volver)
            if ev.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
                return True
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return "submit"
            if ev.key == pygame.K_TAB:
                return "tab"
            ch = getattr(ev, "unicode", "")
            if not _textinput_seen and ch and ch.isprintable():
                self._add(ch)
                self._last_key_char = ch
            return True                             # las letras no activan otros botones
        return False

    def draw(self, surf, t=0.0):
        if self.label:
            draw_text(surf, self.label, 16, (self.rect.left, self.rect.top - 14), C.INK,
                      anchor="midleft", outline=C.WHITE)
        face = C.WHITE if self.focused else (C.CREAM if self.enabled else C.CREAM_DARK)
        inner = bevel_box(surf, self.rect, face)
        if self.focused:
            pygame.draw.rect(surf, C.GOLD, self.rect.inflate(6, 6), 3)
        shown = "•" * len(self.value) if self.password else self.value
        x = inner.left + 10
        if shown:
            draw_text(surf, shown, 24, (x, inner.centery), C.INK, anchor="midleft", outline=None)
        elif self.placeholder and not self.focused:
            draw_text(surf, self.placeholder, 16, (x, inner.centery), C.INK_SOFT, anchor="midleft",
                      outline=None)
        if self.focused and int(t * 2.5) % 2 == 0:
            cx = x + (text_width(shown, 24) + 2 if shown else 0)
            pygame.draw.rect(surf, C.INK, (cx, inner.centery - 12, 4, 24))


class CheckBox:
    def __init__(self, rect, label, value=False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.value = value
        self.hover = False

    def handle_event(self, ev):
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos):
            self.value = not self.value
            return True
        return False

    def draw(self, surf):
        box = pygame.Rect(self.rect.left, self.rect.centery - 16, 32, 32)
        inner = bevel_box(surf, box, C.GOLD if self.hover else C.WHITE, shadow=False)
        if self.value:
            pygame.draw.rect(surf, C.INK, inner.inflate(-8, -8))
        draw_text(surf, self.label, 24, (box.right + 14, box.centery), C.INK, anchor="midleft", outline=C.WHITE)
