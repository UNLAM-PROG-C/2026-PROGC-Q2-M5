"""Nombre del jugador: se elige al empezar, una sola vez, y vale para todos los modos.

Aparece antes del menú la primera vez que se abre el juego (o si el nombre
guardado no sirve). Después se puede cambiar desde el menú principal.
"""
import pygame

from .. import profile as prof
from . import palette as C
from .assets import draw_text
from .screens import BackButton, Screen, button, dim, draw_logo, footer, panel
from .widgets import TextField


class ProfileScreen(Screen):
    def __init__(self, app, first_run=True):
        super().__init__(app)
        self.first_run = first_run
        current = app.profile.name if app.profile else ""
        self.field = TextField((440, 352, 400, 56), "TU NOMBRE", 16,
                               allowed=lambda ch: ch in prof.NAME_CHARS, value=current,
                               placeholder="entre 3 y 16 letras o números", sticky=True)
        self.field.focus(True)
        self.ok_rect = pygame.Rect(0, 0, 300, 56)
        self.ok_rect.center = (640, 470)
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
            self.error = "El nombre debe tener entre 3 y 16 letras, números o espacios."
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
        dim(surf, 110)
        panel(surf, pygame.Rect(360, 20, 560, 150), alpha=225)
        draw_logo(surf, (640, 72), 0.9, self.t)
        box = panel(surf, pygame.Rect(340, 210, 600, 330))
        draw_text(surf, "¿CÓMO TE LLAMÁS?", 32, (640, box.top + 34), C.GOLD, kind="title", outline=C.INK,
                  shadow=True)
        draw_text(surf, "Vale para todos los modos: Mundialito, local y online.", 16,
                  (640, box.top + 78), C.INK, outline=None)
        self.field.draw(surf, self.t)
        button(surf, self.ok_rect, "¡A JUGAR!" if self.first_run else "GUARDAR", self.hover, True, 24, self.t)
        if self.error:
            draw_text(surf, self.error, 16, (640, box.bottom + 24), C.RED, outline=C.WHITE)
        else:
            draw_text(surf, "Si otra persona usa el mismo nombre online, los distingue una etiqueta (#1234).",
                      16, (640, box.bottom + 24), C.INK, outline=C.WHITE)
        footer(surf, "Enter: confirmar" + ("" if self.first_run else "  -  Esc: volver sin cambiar"))
        self.back_button.draw(surf, self.t)
