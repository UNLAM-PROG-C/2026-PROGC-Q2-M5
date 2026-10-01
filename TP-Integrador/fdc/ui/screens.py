"""Pantallas generales: arranque, menú, controles, leyenda de poderes y error.

Estilo retro claro: paneles crema con bisel, botones con cursor ► y fuente
pixel art propia. Las pantallas del partido (selección, juego, resultado)
están en match_screens.py.
"""
import math

import pygame

from ..config import (CATEGORY_BAD, CATEGORY_COLORS, CATEGORY_GLOBAL, CATEGORY_GOOD,
                      DEBUG_PANEL_KEY, FULLSCREEN_KEY, GAME_NAME, GAME_TAGLINE, IPC, MUTE_KEY,
                      PAUSE_KEY, PLAYER_COLORS, PLAYER_KEYS, POWERS)
from . import palette as C
from .assets import draw_text, wrap
from .characters import CHARACTER_IDS
from .icons import power_icon
from .input import key_label
from .retro import bevel_box, panel as retro_panel

UP_KEYS = (pygame.K_w, pygame.K_UP)
DOWN_KEYS = (pygame.K_s, pygame.K_DOWN)
OK_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_p)
BACK_KEYS = (pygame.K_ESCAPE, pygame.K_BACKSPACE)


class Screen:
    def __init__(self, app):
        self.app = app
        self.t = 0.0

    def enter(self):
        pass

    def leave(self):
        pass

    def handle_event(self, ev):
        pass

    def on_link(self, msgs, state):
        pass

    def on_focus_lost(self):
        pass

    def update(self, dt):
        self.t += dt

    def draw(self, surf):
        pass

    def debug_info(self):
        return {}


# ---------------------------------------------------------------------------
# Widgets retro
# ---------------------------------------------------------------------------
def button(surf, rect, label, active=False, enabled=True, size=24, t=0.0):
    """Botón retro: bisel, sombra y cursor ► parpadeante cuando está elegido."""
    face = C.GOLD if active else C.CREAM
    if not enabled:
        face = C.CREAM_DARK
    r = pygame.Rect(rect)
    if active:
        r = r.move(0, -2 if int(t * 4) % 2 else 0)
    bevel_box(surf, r, face)
    draw_text(surf, label, size, r.center, C.INK if enabled else C.INK_SOFT, outline=None)
    if active and int(t * 3) % 2 == 0:
        draw_text(surf, "►", size, (r.left - 22, r.centery), C.INK, outline=C.WHITE)


class BackButton:
    """Botón "◄ VOLVER" de la esquina superior izquierda (mouse). Esc hace lo mismo."""
    RECT = pygame.Rect(16, 12, 176, 44)

    def __init__(self, action, label="◄ VOLVER", rect=None):
        self.action = action
        self.label = label
        self.rect = pygame.Rect(rect or self.RECT)
        self.hover = False
        self.visible = True

    def handle_event(self, ev):
        """True si el evento fue un clic en el botón (ya ejecutó la acción)."""
        if not self.visible:
            return False
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos):
            self.action()
            return True
        return False

    def draw(self, surf, t=0.0):
        if self.visible:
            button(surf, self.rect, self.label, self.hover, True, 16, t)


class Menu:
    """Lista vertical de botones. Teclado (ambos jugadores) y mouse."""

    def __init__(self, items, center, width=360, height=56, gap=14, size=24):
        self.items = list(items)        # [(texto, callback)]
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
        if not self.enabled:
            return False
        if ev.type == pygame.KEYDOWN:
            if ev.key in UP_KEYS:
                self.sel = (self.sel - 1) % len(self.items)
                audio and audio.play("select")
                return True
            if ev.key in DOWN_KEYS:
                self.sel = (self.sel + 1) % len(self.items)
                audio and audio.play("select")
                return True
            if ev.key in OK_KEYS:
                audio and audio.play("confirm")
                self.items[self.sel][1]()
                return True
        elif ev.type == pygame.MOUSEMOTION:
            for i, r in enumerate(self.rects()):
                if r.collidepoint(ev.pos) and self.sel != i:
                    self.sel = i
                    audio and audio.play("select")
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for i, r in enumerate(self.rects()):
                if r.collidepoint(ev.pos):
                    self.sel = i
                    audio and audio.play("confirm")
                    self.items[i][1]()
                    return True
        return False

    def update(self, dt):
        self.t += dt

    def draw(self, surf):
        for i, (r, (label, _)) in enumerate(zip(self.rects(), self.items)):
            button(surf, r, label, i == self.sel and self.enabled, self.enabled, self.size, self.t)


_overlays = {}


def dim(surf, alpha=110, color=C.CREAM):
    """Velo claro sobre el estadio (mantiene la paleta luminosa)."""
    key = (surf.get_size(), alpha, color)
    s = _overlays.get(key)
    if s is None:
        s = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        s.fill((*color, alpha))
        _overlays[key] = s
    surf.blit(s, (0, 0))


def panel(surf, rect, face=C.CREAM, border=C.INK, alpha=None):
    return retro_panel(surf, rect, face, border, alpha)


def title(surf, txt, center, size=56, color=C.GOLD):
    draw_text(surf, txt, size, center, color, kind="title", outline=C.INK, shadow=True)


def draw_logo(surf, center, scale=1.0, t=0.0):
    y = center[1] + (4 if int(t * 2) % 2 else 0)
    draw_text(surf, GAME_NAME.upper(), int(72 * scale), (center[0], y), C.GOLD, kind="title",
              outline=C.INK, shadow=True)
    draw_text(surf, GAME_TAGLINE, int(18 * scale), (center[0], y + 56 * scale), C.INK, outline=C.WHITE)


def footer(surf, txt):
    r = pygame.Rect(0, 684, 1280, 36)
    s = pygame.Surface(r.size, pygame.SRCALPHA)
    s.fill((*C.CREAM, 220))
    surf.blit(s, r)
    pygame.draw.rect(surf, C.INK, (0, r.top, 1280, 2))
    draw_text(surf, txt, 16, r.center, C.INK, outline=None)


def keycap(surf, center, label, size=16):
    """Tecla dibujada como un botón retro."""
    from .assets import text_width
    w = max(44, text_width(label, size) + 24)
    r = pygame.Rect(0, 0, w, 36)
    r.center = center
    bevel_box(surf, r, C.WHITE)
    draw_text(surf, label, size, r.center, C.INK, outline=None)
    return r


# ---------------------------------------------------------------------------
# Arranque: espera READY de la simulación (sin bloquear la ventana)
# ---------------------------------------------------------------------------
class BootScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.to_warm = list(CHARACTER_IDS)

    def update(self, dt):
        super().update(dt)
        if self.to_warm:                   # retratos, uno por cuadro: la ventana responde
            self.app.sprites.portrait(self.to_warm.pop(0))
        elif self.app.link.ready:
            self.app.switch(MenuScreen(self.app))

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, 150)
        draw_logo(surf, (640, 230), 1.0, self.t)
        waiting = not self.app.link.ready
        msg = "Iniciando el proceso de simulación..." if waiting else "Preparando personajes..."
        draw_text(surf, msg, 24, (640, 420), C.INK, outline=C.WHITE)
        self.app.ball_sprite.draw(surf, 640, 480 - abs(math.sin(self.t * 5)) * 30, 17, self.t * 400)
        draw_text(surf, f"Esperando la confirmación READY ({self.t:.1f} s de {IPC.READY_TIMEOUT:.0f} s)"
                  if waiting else "Simulación lista", 16, (640, 540), C.INK_SOFT, outline=None)


# ---------------------------------------------------------------------------
# Menú principal
# ---------------------------------------------------------------------------
class MenuScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.menu = Menu([
            ("Jugar", lambda: app.switch(PlayMenuScreen(app))),
            ("Controles", lambda: app.switch(ControlsScreen(app))),
            ("Poderes", lambda: app.switch(LegendScreen(app))),
            ("Salir", app.quit),
        ], (640, 440))

    def enter(self):
        self.app.audio.crowd(False)

    def handle_event(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.menu.sel = len(self.menu.items) - 1   # Esc lleva a "Salir" (no cierra de golpe)
            self.app.audio.play("select")
            return
        self.menu.handle_event(ev, self.app.audio)

    def update(self, dt):
        super().update(dt)
        self.menu.update(dt)

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, 70)
        sp = self.app.sprites
        floor = 646
        for i, (cid, x, f) in enumerate((("messi", 230, 1), ("pele", 1050, -1))):
            bob = -1 if (self.t * 1.6 + i * 0.5) % 2 < 1 else 0
            img, (fx, fy) = sp.player(cid, f, 0, bob, PLAYER_COLORS[i], False, 1.6)
            surf.blit(img, (x - fx, floor - fy))
        by = 590 - abs(math.sin(self.t * 2.6)) * 150
        self.app.ball_sprite.draw(surf, 640, by, 17, self.t * 200)
        panel(surf, pygame.Rect(360, 20, 560, 150), alpha=225)
        draw_logo(surf, (640, 72), 0.9, self.t)
        self.menu.draw(surf)
        badge = "  -  MODO PRUEBA" if self.app.options.test_mode else ""
        footer(surf, f"{key_label(DEBUG_PANEL_KEY)}: panel de depuración  -  {key_label(FULLSCREEN_KEY)}: "
                     f"pantalla completa  -  {key_label(MUTE_KEY)}: silencio{badge}")


# ---------------------------------------------------------------------------
# Submenús: Jugar -> Mundialito / Multijugador -> Local / Online
# ---------------------------------------------------------------------------
class SubMenuScreen(Screen):
    """Menú con título sobre el estadio. Esc vuelve al menú anterior."""
    TITLE = ""
    SUBTITLE = ""

    def __init__(self, app, items):
        super().__init__(app)
        self.menu = Menu(items, (640, 420))
        self.notice = None            # (texto, tiempo restante)

    def back(self):
        self.app.switch(MenuScreen(self.app))

    def handle_event(self, ev):
        if self.notice and ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self.notice = None        # cualquier tecla o clic cierra el aviso
            return
        if ev.type == pygame.KEYDOWN and ev.key in BACK_KEYS:
            self.app.audio.play("back")
            self.back()
            return
        self.menu.handle_event(ev, self.app.audio)

    def update(self, dt):
        super().update(dt)
        self.menu.update(dt)
        if self.notice:
            txt, left = self.notice
            self.notice = (txt, left - dt) if left - dt > 0 else None

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, 90)
        title(surf, self.TITLE, (640, 120), 64)
        if self.SUBTITLE:
            draw_text(surf, self.SUBTITLE, 16, (640, 176), C.INK, outline=C.WHITE)
        self.menu.draw(surf)
        if self.notice:
            r = pygame.Rect(0, 0, 640, 170)
            r.center = (640, 400)
            inner = panel(surf, r)
            title(surf, self.notice[0], (640, inner.top + 46), 40)
            draw_text(surf, "Pronto vas a poder jugar contra otra persona por internet.", 16,
                      (640, inner.top + 96), C.INK, outline=None)
            draw_text(surf, "Tocá cualquier tecla para volver", 16, (640, inner.bottom - 16), C.INK_SOFT,
                      outline=None)
        footer(surf, "Esc: volver")


class PlayMenuScreen(SubMenuScreen):
    TITLE = "JUGAR"
    SUBTITLE = "Mundialito: vos contra la computadora.  Multijugador: dos personas."

    def __init__(self, app):
        super().__init__(app, [("Mundialito", self.mundialito), ("Multijugador", self.multiplayer),
                               ("Volver", self.back)])

    def mundialito(self):
        from .mundialito_screens import open_mundialito
        open_mundialito(self.app)

    def multiplayer(self):
        self.app.switch(MultiplayerMenuScreen(self.app))


class MultiplayerMenuScreen(SubMenuScreen):
    TITLE = "MULTIJUGADOR"
    SUBTITLE = "Local: dos personas en el mismo teclado."

    def __init__(self, app):
        super().__init__(app, [("Local", self.local), ("Online", self.online), ("Volver", self.back)])

    def back(self):
        self.app.switch(PlayMenuScreen(self.app))

    def local(self):
        from .match_screens import SelectScreen
        self.app.switch(SelectScreen(self.app))

    def online(self):
        self.app.audio.play("blocked")
        self.notice = ("MÓDULO EN DESARROLLO", 6.0)


# ---------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------
class ControlsScreen(Screen):
    ACTION_NAMES = (("left", "Izquierda"), ("right", "Derecha"), ("jump", "Saltar"), ("kick", "Patear"))

    def __init__(self, app):
        super().__init__(app)
        self.back_button = BackButton(self.back)

    def back(self):
        self.app.audio.play("back")
        self.app.switch(MenuScreen(self.app))

    def handle_event(self, ev):
        if self.back_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN and (ev.key in BACK_KEYS or ev.key in OK_KEYS):
            self.back()

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, 140)
        title(surf, "CONTROLES", (640, 52))
        for i in (0, 1):
            r = pygame.Rect(0, 0, 460, 290)
            r.center = (350 if i == 0 else 930, 265)
            inner = panel(surf, r)
            pygame.draw.rect(surf, PLAYER_COLORS[i], (inner.left, inner.top, inner.width, 8))
            draw_text(surf, f"JUGADOR {i + 1} ({'izquierda' if i == 0 else 'derecha'})", 24,
                      (r.centerx, inner.top + 34), PLAYER_COLORS[i], outline=C.INK)
            for k, (action, name) in enumerate(self.ACTION_NAMES):
                y = inner.top + 84 + k * 48
                draw_text(surf, name, 24, (inner.left + 20, y), C.INK, anchor="midleft", outline=None)
                keycap(surf, (inner.right - 96, y), key_label(PLAYER_KEYS[i][action]))
        info = pygame.Rect(0, 0, 1080, 240)
        info.midtop = (640, 428)
        inner = panel(surf, info)
        lines = [
            f"{key_label(PAUSE_KEY)}: pausa (continuar, reiniciar o volver al menú).  {key_label(DEBUG_PANEL_KEY)}: "
            f"panel de depuración.  {key_label(FULLSCREEN_KEY)}: pantalla completa.  {key_label(MUTE_KEY)}: silencio.",
            "Menús: W/S o flechas arriba/abajo; Enter, Espacio o P para elegir (también con el mouse).",
            "Elegir personaje: J1 con A/D, confirma con Espacio y cancela con W; J2 con las flechas, "
            "P y flecha arriba. También se puede confirmar con el mouse.",
            "Mundialito (1 jugador): jugás a la derecha y valen las dos combinaciones de teclas.",
            "Cabecear es tocar la pelota con la cabeza; la patada sale hacia donde mira el personaje.",
            "Aviso: muchos teclados no registran más de 3 o 4 teclas a la vez (\"ghosting\"). Si alguna "
            "combinación no responde es una limitación del teclado; las teclas se cambian en fdc/config.py.",
        ]
        y = inner.top + 10
        for ln in lines:
            for sub in wrap(ln, 16, inner.width - 20):
                draw_text(surf, sub, 16, (inner.left + 10, y), C.INK, anchor="topleft", outline=None)
                y += 24
            y += 6
        footer(surf, "Esc o Enter: volver")
        self.back_button.draw(surf, self.t)


# ---------------------------------------------------------------------------
# Leyenda de poderes
# ---------------------------------------------------------------------------
class LegendScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.back_button = BackButton(self.back)

    def back(self):
        self.app.audio.play("back")
        self.app.switch(MenuScreen(self.app))

    def handle_event(self, ev):
        if self.back_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN and (ev.key in BACK_KEYS or ev.key in OK_KEYS):
            self.back()

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, 150)
        title(surf, "PODERES", (640, 34), 48)
        legend = [(CATEGORY_GOOD, "Verde: beneficia al receptor"), (CATEGORY_BAD, "Rojo: lo perjudica"),
                  (CATEGORY_GLOBAL, "Violeta: cambia el partido")]
        for k, (cat, label) in enumerate(legend):
            x = 150 + k * 380
            box = pygame.Rect(x - 30, 72, 24, 24)
            bevel_box(surf, box, CATEGORY_COLORS[cat], shadow=False)
            draw_text(surf, label, 16, (x, 84), C.INK, anchor="midleft", outline=C.WHITE)
        draw_text(surf, "Se activan cuando la PELOTA toca el objeto. Receptor = último jugador que la tocó.",
                  16, (640, 114), C.INK, outline=C.WHITE)
        for i, p in enumerate(POWERS):
            col, row = (0, i) if i < 9 else (1, i - 9)
            r = pygame.Rect(24 + col * 624, 134 + row * 60, 608, 54)
            inner = bevel_box(surf, r, C.CREAM)
            pygame.draw.rect(surf, CATEGORY_COLORS[p.category], (inner.left, inner.top, 6, inner.height))
            surf.blit(power_icon(p.id, 40), (inner.left + 12, inner.top + 3))
            draw_text(surf, p.name, 16, (inner.left + 62, inner.top + 6), C.INK, anchor="topleft", outline=None)
            draw_text(surf, p.description, 16, (inner.left + 62, inner.top + 26), C.INK_SOFT,
                      anchor="topleft", outline=None)
            dur = "puntual" if p.duration <= 0 else f"{p.duration:g} s".replace(".", ",")
            draw_text(surf, dur, 16, (inner.right - 10, inner.top + 6), CATEGORY_COLORS[p.category],
                      anchor="topright", outline=C.INK)
        footer(surf, "Esc o Enter: volver  -  Repetir un poder renueva su duración; uno opuesto lo reemplaza")
        self.back_button.draw(surf, self.t)


# ---------------------------------------------------------------------------
# Error de la simulación
# ---------------------------------------------------------------------------
class ErrorScreen(Screen):
    def __init__(self, app, message, detail=""):
        super().__init__(app)
        self.message = message
        tb = [ln for ln in (detail or "").strip().splitlines() if ln.strip()]
        self.detail = tb[-3:] if tb else []
        self.menu = Menu([("Reintentar", self.retry), ("Salir", app.quit)], (640, 560), width=300)

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
        dim(surf, 170)
        r = pygame.Rect(0, 0, 1040, 340)
        r.midtop = (640, 80)
        inner = panel(surf, r, face=(255, 236, 232), border=C.RED)
        title(surf, "PROBLEMA CON LA SIMULACIÓN", (640, inner.top + 36), 40, C.RED)
        y = inner.top + 96
        for ln in wrap(self.message, 24, inner.width - 40):
            draw_text(surf, ln, 24, (640, y), C.INK, outline=None)
            y += 32
        y += 8
        for ln in self.detail:
            draw_text(surf, ln[:110], 16, (640, y), C.INK_SOFT, outline=None)
            y += 22
        draw_text(surf, "La interfaz sigue funcionando: podés reintentar (se lanza un proceso nuevo) o salir.",
                  16, (640, inner.bottom - 18), C.INK, outline=None)
        self.menu.draw(surf)


def fps_value(clock):
    v = clock.get_fps()
    return v if v > 0 else 60.0
