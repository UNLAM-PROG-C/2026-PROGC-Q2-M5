"""Nombre del jugador: se elige al empezar, una sola vez, y vale para todos los modos.

Aparece antes del menú la primera vez que se abre el juego (o si el nombre
guardado no sirve). Después se puede cambiar desde el menú principal.
"""
import pygame

from .. import profile as prof
from . import palette as C
from .assets import draw_text
from .layout import BUTTON_H, CENTER_X, FONT_LARGE, FONT_SMALL, FONT_TEXT, VEIL_PROFILE
from .screens import LOGO_CENTER, LOGO_PANEL, LOGO_PANEL_ALPHA, LOGO_SCALE, BackButton, Screen, button, dim, \
    draw_logo, footer, panel
from .widgets import TextField


class ProfileScreen(Screen):
    FIELD = (440, 352, 400, BUTTON_H)  # campo de texto del nombre (x, y, ancho, alto)
    OK_SIZE = (300, BUTTON_H)          # botón "¡A JUGAR!" / "GUARDAR" (ancho, alto)
    OK_CENTER = (CENTER_X, 470)        # centro de ese botón
    BOX = (340, 210, 600, 330)         # recuadro de la pregunta (x, y, ancho, alto)
    QUESTION_Y = 34                    # "¿CÓMO TE LLAMÁS?", desde arriba del recuadro
    EXPLANATION_Y = 78                 # explicación, desde arriba del recuadro
    NOTE_GAP = 24                      # aviso o error, debajo del recuadro

    def __init__(self, app, first_run=True):
        super().__init__(app)
        self.first_run = first_run
        current = app.profile.name if app.profile else ""
        self.field = TextField(self.FIELD, "TU NOMBRE", prof.NAME_MAX_LEN,
                               allowed=lambda ch: ch in prof.NAME_CHARS, value=current,
                               placeholder=f"entre {prof.NAME_MIN_LEN} y {prof.NAME_MAX_LEN} letras o números",
                               sticky=True)
        self.field.focus(True)
        self.ok_rect = pygame.Rect((0, 0), self.OK_SIZE)
        self.ok_rect.center = self.OK_CENTER
        self.hover = False
        self.error = None
        self.back_button = BackButton(self.back)
        self.back_button.visible = not first_run   # la primera vez no hay a dónde volver

    def back(self):
        from .screens import MenuScreen
        self.app.switch(MenuScreen(self.app))

    def submit(self):
        name = self.field.value.strip()
        if not prof.valid_name(name):
            self.error = f"El nombre debe tener {prof.NAME_RULE}."
            self.app.audio.play("blocked")
            return
        old = self.app.profile
        profile = old.renamed(name) if old else prof.Profile(name)   # mismo jugador, mismo id
        self.app.set_profile(profile)
        self.app.audio.play("confirm")
        self.back()

    def handle_event(self, ev):
        if self.back_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE and not self.first_run:
            self.app.audio.play("back")
            self.back()
            return
        r = self.field.handle_event(ev)
        if r == "submit":
            self.submit()
        if r:
            self.error = None if r is True else self.error
            return
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.ok_rect.collidepoint(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.ok_rect.collidepoint(ev.pos):
            self.submit()
        elif ev.type == pygame.KEYDOWN and ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.submit()

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_PROFILE)
        panel(surf, pygame.Rect(LOGO_PANEL), alpha=LOGO_PANEL_ALPHA)
        draw_logo(surf, LOGO_CENTER, LOGO_SCALE, self.t)
        box = panel(surf, pygame.Rect(self.BOX))
        draw_text(surf, "¿CÓMO TE LLAMÁS?", FONT_LARGE, (CENTER_X, box.top + self.QUESTION_Y), C.GOLD, kind="title",
                  outline=C.INK, shadow=True)
        draw_text(surf, "Vale para todos los modos: Mundialito, local y online.", FONT_SMALL,
                  (CENTER_X, box.top + self.EXPLANATION_Y), C.INK, outline=None)
        self.field.draw(surf, self.t)
        button(surf, self.ok_rect, "¡A JUGAR!" if self.first_run else "GUARDAR", self.hover, True, FONT_TEXT,
               self.t)
        if self.error:
            draw_text(surf, self.error, FONT_SMALL, (CENTER_X, box.bottom + self.NOTE_GAP), C.RED, outline=C.WHITE)
        else:
            draw_text(surf, "Si otra persona usa el mismo nombre online, los distingue una etiqueta (#1234).",
                      FONT_SMALL, (CENTER_X, box.bottom + self.NOTE_GAP), C.INK, outline=C.WHITE)
        footer(surf, "Enter: confirmar" + ("" if self.first_run else "  -  Esc: volver sin cambiar"))
        self.back_button.draw(surf, self.t)
