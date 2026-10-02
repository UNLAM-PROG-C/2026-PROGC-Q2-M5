"""Pantallas generales: arranque, menú, controles, leyenda de poderes y error.

Estilo retro claro: paneles crema con bisel, botones con cursor ► y fuente
pixel art propia. Las pantallas del partido (selección, juego, resultado)
están en match_screens.py.

Las medidas son px en la resolución lógica de 1280 x 720. Las comunes están
en layout.py; las propias de cada pantalla, al principio de su clase.
"""
import math

import pygame

from ..config import (CATEGORY_BAD, CATEGORY_COLORS, CATEGORY_GLOBAL, CATEGORY_GOOD,
                      DEBUG_PANEL_KEY, FULLSCREEN_KEY, GAME_NAME, GAME_TAGLINE, IPC, MUTE_KEY,
                      PAUSE_KEY, PLAYER_COLORS, PLAYER_KEYS, POWERS, UI_FPS, Arena, BallSpec)
from . import palette as C
from . import pixelfont
from .assets import draw_text, text_width, wrap
from .characters import CHARACTER_IDS
from .icons import power_icon
from .input import key_label
from .layout import (BLINK_HZ, BOB_HZ, BOB_PX, BUTTON_H, BUTTON_SMALL_H, CENTER_X, CURSOR_GAP,
                     FONT_BANNER, FONT_SMALL, FONT_TEXT, FONT_TITLE, FONT_TITLE_L, FONT_TITLE_S, FONT_TITLE_XL,
                     FRAME_LINE, SCREEN_H, SCREEN_MARGIN, SCREEN_W, SHADOW_OFFSET, TEXT_LINE_H, VEIL_BOOT, VEIL_ERROR,
                     VEIL_LIST, VEIL_MENU, VEIL_PROFILE, VEIL_SUBMENU)
from .retro import bevel_box, panel as retro_panel
from .sprites import idle_pose

UP_KEYS = (pygame.K_w, pygame.K_UP)
DOWN_KEYS = (pygame.K_s, pygame.K_DOWN)
OK_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_p)
BACK_KEYS = (pygame.K_ESCAPE, pygame.K_BACKSPACE)

# --- menús
MENU_W = 360                       # px: ancho de los botones de un menú
MENU_GAP = 14                      # px entre botones de un menú
# --- logo
LOGO_BOB_HZ = 2                    # el logo sube y baja dos veces por segundo
LOGO_BOB_PX = 4                    # px que sube el logo
LOGO_TAGLINE_SIZE = 18             # tamaño de letra de la frase bajo el logo (a escala 1)
LOGO_TAGLINE_GAP = 56              # px entre el logo y la frase (a escala 1)
LOGO_PANEL = (360, 20, 560, 150)   # recuadro translúcido detrás del logo (menú, nombre)
LOGO_PANEL_ALPHA = 225             # opacidad de ese recuadro
LOGO_CENTER = (CENTER_X, 72)       # centro del logo en el menú
LOGO_SCALE = 0.9                   # escala del logo en el menú
# --- pie de página
FOOTER_H = 36                      # px: alto de la franja del pie
FOOTER_ALPHA = 220                 # opacidad de la franja del pie
FOOTER_LINE = 2                    # px: línea superior de la franja
# --- teclas dibujadas
KEYCAP_MIN_W = 44                  # px: ancho mínimo de una tecla
KEYCAP_PADDING = 24                # px de aire alrededor del nombre de la tecla
KEYCAP_H = 36                      # px: alto de una tecla
# --- tablero LED del resultado
SCOREBOARD_H = 110                 # px: alto del tablero
SCOREBOARD_INSET = 8               # px entre el marco del tablero y la pantalla LED
SCOREBOARD_LED_SCALE = 9           # tamaño de los puntos LED del resultado
FALLBACK_FPS = float(UI_FPS)       # FPS que se muestran mientras no hay mediciones


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

    def on_net(self, msg):
        """Mensaje del servidor online (de a uno, en orden)."""

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
def button(surf, rect, label, active=False, enabled=True, size=FONT_TEXT, t=0.0):
    """Botón retro: bisel, sombra y cursor ► parpadeante cuando está elegido."""
    face = C.GOLD if active else C.CREAM
    if not enabled:
        face = C.CREAM_DARK
    r = pygame.Rect(rect)
    if active:
        r = r.move(0, -BOB_PX if int(t * BOB_HZ) % 2 else 0)
    bevel_box(surf, r, face)
    draw_text(surf, label, size, r.center, C.INK if enabled else C.INK_SOFT, outline=None)
    if active and int(t * BLINK_HZ) % 2 == 0:
        draw_text(surf, "►", size, (r.left - CURSOR_GAP, r.centery), C.INK, outline=C.WHITE)


class BackButton:
    """Botón "◄ VOLVER" de la esquina superior izquierda (mouse). Esc hace lo mismo."""
    WIDTH = 176                    # px: ancho del botón
    TOP = 12                       # px desde arriba de la pantalla
    RECT = pygame.Rect(SCREEN_MARGIN, TOP, WIDTH, BUTTON_SMALL_H)   # lugar del botón

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
            button(surf, self.rect, self.label, self.hover, True, FONT_SMALL, t)


class Menu:
    """Lista vertical de botones. Teclado (ambos jugadores) y mouse."""

    def __init__(self, items, center, width=MENU_W, height=BUTTON_H, gap=MENU_GAP, size=FONT_TEXT):
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


def dim(surf, alpha=VEIL_PROFILE, color=C.CREAM):
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


def title(surf, txt, center, size=FONT_TITLE_L, color=C.GOLD):
    draw_text(surf, txt, size, center, color, kind="title", outline=C.INK, shadow=True)


def draw_logo(surf, center, scale=1.0, t=0.0):
    y = center[1] + (LOGO_BOB_PX if int(t * LOGO_BOB_HZ) % 2 else 0)
    draw_text(surf, GAME_NAME.upper(), int(FONT_BANNER * scale), (center[0], y), C.GOLD, kind="title",
              outline=C.INK, shadow=True)
    draw_text(surf, GAME_TAGLINE, int(LOGO_TAGLINE_SIZE * scale), (center[0], y + LOGO_TAGLINE_GAP * scale),
              C.INK, outline=C.WHITE)


def footer(surf, txt):
    r = pygame.Rect(0, SCREEN_H - FOOTER_H, SCREEN_W, FOOTER_H)
    s = pygame.Surface(r.size, pygame.SRCALPHA)
    s.fill((*C.CREAM, FOOTER_ALPHA))
    surf.blit(s, r)
    pygame.draw.rect(surf, C.INK, (0, r.top, SCREEN_W, FOOTER_LINE))
    draw_text(surf, txt, FONT_SMALL, r.center, C.INK, outline=None)


def keycap(surf, center, label, size=FONT_SMALL):
    """Tecla dibujada como un botón retro."""
    w = max(KEYCAP_MIN_W, text_width(label, size) + KEYCAP_PADDING)
    r = pygame.Rect(0, 0, w, KEYCAP_H)
    r.center = center
    bevel_box(surf, r, C.WHITE)
    draw_text(surf, label, size, r.center, C.INK, outline=None)
    return r


def scoreboard(surf, center, width, score_text):
    """Tablero con el resultado en puntos LED (pantallas de fin de partido)."""
    box = pygame.Rect(0, 0, width, SCOREBOARD_H)
    box.center = center
    pygame.draw.rect(surf, C.INK, box.move(SHADOW_OFFSET, SHADOW_OFFSET))
    pygame.draw.rect(surf, C.STRUCT_DARK, box)
    pygame.draw.rect(surf, C.INK, box, FRAME_LINE)
    led = box.inflate(-2 * SCOREBOARD_INSET, -2 * SCOREBOARD_INSET)
    pygame.draw.rect(surf, C.LED_BG, led)
    score = pixelfont.render_led(score_text, SCOREBOARD_LED_SCALE, C.LED_ON, C.LED_OFF)
    surf.blit(score, score.get_rect(center=led.center))


def bouncing_ball(app, surf, t, x, ground_y, height, hz, spin):
    """La pelota del juego picando: sube 'height' px; 'hz' marca el ritmo y 'spin' el giro (grados/s)."""
    y = ground_y - abs(math.sin(t * hz)) * height
    app.ball_sprite.draw(surf, x, y, BallSpec.RADIUS, t * spin)


# ---------------------------------------------------------------------------
# Arranque: espera READY de la simulación (sin bloquear la ventana)
# ---------------------------------------------------------------------------
class BootScreen(Screen):
    LOGO_CENTER = (CENTER_X, 230)      # logo
    MESSAGE_Y = 420                    # "Iniciando el proceso de simulación..."
    BALL_GROUND_Y = 480                # pelota que pica: piso
    BALL_HOP = 30                      # px que sube
    BALL_HOP_HZ = 5                    # rebotes por segundo (de ida)
    BALL_SPIN = 400                    # grados por segundo que gira
    STATUS_Y = 540                     # "Esperando la confirmación READY..."

    def __init__(self, app):
        super().__init__(app)
        self.to_warm = list(CHARACTER_IDS)

    def update(self, dt):
        super().update(dt)
        if self.to_warm:                   # retratos, uno por cuadro: la ventana responde
            self.app.sprites.portrait(self.to_warm.pop(0))
        elif self.app.link is None or self.app.link.ready:
            self.app.switch(self.app.first_screen())

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_BOOT)
        draw_logo(surf, self.LOGO_CENTER, 1.0, self.t)
        link = self.app.link
        waiting = link is not None and not link.ready
        msg = "Iniciando el proceso de simulación..." if waiting else "Preparando personajes..."
        draw_text(surf, msg, FONT_TEXT, (CENTER_X, self.MESSAGE_Y), C.INK, outline=C.WHITE)
        bouncing_ball(self.app, surf, self.t, CENTER_X, self.BALL_GROUND_Y, self.BALL_HOP, self.BALL_HOP_HZ,
                      self.BALL_SPIN)
        if link is not None and not getattr(link, "inline", False):
            draw_text(surf, f"Esperando la confirmación READY ({self.t:.1f} s de {IPC.READY_TIMEOUT:.0f} s)"
                      if waiting else "Simulación lista", FONT_SMALL, (CENTER_X, self.STATUS_Y), C.INK_SOFT,
                      outline=None)


# ---------------------------------------------------------------------------
# Menú principal
# ---------------------------------------------------------------------------
class MenuScreen(Screen):
    MENU_CENTER = (CENTER_X, 440)      # centro de la lista de botones
    PLAYER_TOP = 12                    # px: botón con el nombre del jugador, arriba a la derecha
    PLAYER_PADDING = 40                # px de aire alrededor del nombre en ese botón
    # los dos cabezones decorativos: (personaje, x, mirando a la derecha = 1 / izquierda = -1)
    MASCOTS = (("messi", 230, 1), ("pele", 1050, -1))
    MASCOT_SCALE = 1.6                 # tamaño de los cabezones decorativos
    BALL_GROUND_Y = 590                # pelota que pica en el medio: piso
    BALL_HOP = 150                     # px que sube
    BALL_HOP_HZ = 2.6                  # rebotes por segundo (de ida)
    BALL_SPIN = 200                    # grados por segundo que gira

    def __init__(self, app):
        super().__init__(app)
        items = [
            ("Jugar", lambda: app.switch(PlayMenuScreen(app))),
            ("Controles", lambda: app.switch(ControlsScreen(app))),
            ("Poderes", lambda: app.switch(LegendScreen(app))),
        ]
        if not app.web:
            items.append(("Salir", app.quit))     # una página web no se cierra a sí misma
        self.menu = Menu(items, self.MENU_CENTER)

    def player_label(self):
        return f"{self.app.profile.name.upper()}  (CAMBIAR)" if self.app.profile else ""

    def player_rect(self):
        """Botón con el nombre del jugador, arriba a la derecha (su ancho depende del nombre)."""
        r = pygame.Rect(0, 0, text_width(self.player_label(), FONT_SMALL) + self.PLAYER_PADDING, BUTTON_SMALL_H)
        r.topright = (SCREEN_W - SCREEN_MARGIN, self.PLAYER_TOP)
        return r

    def enter(self):
        self.app.audio.crowd(False)

    def change_name(self):
        from .profile_screen import ProfileScreen
        self.app.audio.play("confirm")
        self.app.switch(ProfileScreen(self.app, first_run=False))

    def handle_event(self, ev):
        if ev.type == pygame.MOUSEMOTION:
            self.player_hover = self.player_rect().collidepoint(ev.pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.player_rect().collidepoint(ev.pos):
            self.change_name()
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_n:
            self.change_name()
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if not self.app.web:
                self.menu.sel = len(self.menu.items) - 1   # Esc lleva a "Salir" (no cierra de golpe)
                self.app.audio.play("select")
            return
        self.menu.handle_event(ev, self.app.audio)

    def update(self, dt):
        super().update(dt)
        self.menu.update(dt)

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_MENU)
        sp = self.app.sprites
        for i, (cid, x, f) in enumerate(self.MASCOTS):
            ang, bob = idle_pose(self.t, i)
            img, (fx, fy) = sp.player(cid, f, ang, bob, PLAYER_COLORS[i], False, self.MASCOT_SCALE)
            surf.blit(img, (x - fx, Arena.FLOOR_Y - fy))
        bouncing_ball(self.app, surf, self.t, CENTER_X, self.BALL_GROUND_Y, self.BALL_HOP, self.BALL_HOP_HZ,
                      self.BALL_SPIN)
        panel(surf, pygame.Rect(LOGO_PANEL), alpha=LOGO_PANEL_ALPHA)
        draw_logo(surf, LOGO_CENTER, LOGO_SCALE, self.t)
        self.menu.draw(surf)
        if self.app.profile is not None:            # jugador: clic (o N) para cambiar el nombre
            button(surf, self.player_rect(), self.player_label(), getattr(self, "player_hover", False),
                   True, FONT_SMALL, self.t)
        badge = "  -  MODO PRUEBA" if self.app.options.test_mode else ""
        footer(surf, f"N: cambiar nombre  -  {key_label(DEBUG_PANEL_KEY)}: depuración  -  "
                     f"{key_label(FULLSCREEN_KEY)}: pantalla completa  -  {key_label(MUTE_KEY)}: silencio{badge}")


# ---------------------------------------------------------------------------
# Submenús: Jugar -> Mundialito / Multijugador -> Local / Online
# ---------------------------------------------------------------------------
class SubMenuScreen(Screen):
    """Menú con título sobre el estadio. Esc vuelve al menú anterior."""
    TITLE = ""
    SUBTITLE = ""
    MENU_CENTER = (CENTER_X, 420)      # centro de la lista de botones
    TITLE_Y = 120                      # título
    SUBTITLE_Y = 176                   # explicación bajo el título

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
        dim(surf, VEIL_SUBMENU)
        title(surf, self.TITLE, (CENTER_X, self.TITLE_Y), FONT_TITLE_XL)
        if self.SUBTITLE:
            draw_text(surf, self.SUBTITLE, FONT_SMALL, (CENTER_X, self.SUBTITLE_Y), C.INK, outline=C.WHITE)
        self.menu.draw(surf)
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
    SUBTITLE = "Local: dos personas en el mismo teclado.  Online: cada uno desde su casa."

    def __init__(self, app):
        super().__init__(app, [("Local", self.local), ("Online", self.online), ("Volver", self.back)])

    def back(self):
        self.app.switch(PlayMenuScreen(self.app))

    def local(self):
        from .match_screens import SelectScreen
        self.app.switch(SelectScreen(self.app))

    def online(self):
        from .online_screens import OnlineHomeScreen
        self.app.switch(OnlineHomeScreen(self.app))


# ---------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------
class ControlsScreen(Screen):
    ACTION_NAMES = (("left", "Izquierda"), ("right", "Derecha"), ("jump", "Saltar"), ("kick", "Patear"))
    TITLE_Y = 52                       # título
    PLAYER_PANEL = (460, 290)          # recuadro de cada jugador (ancho, alto)
    PLAYER_PANEL_X = (350, 930)        # centro horizontal de cada recuadro (J1, J2)
    PLAYER_PANEL_Y = 265               # centro vertical de los recuadros
    COLOR_BAR_H = 8                    # franja con el color del jugador arriba del recuadro
    HEADER_Y = 34                      # "JUGADOR 1 (izquierda)", desde arriba del recuadro
    FIRST_ACTION_Y = 84                # primera acción, desde arriba del recuadro
    ACTION_STEP = 48                   # px entre acciones
    ACTION_NAME_X = 20                 # nombre de la acción, desde el borde izquierdo
    KEY_X = 96                         # centro de la tecla, desde el borde derecho
    INFO_PANEL = (1080, 240)           # recuadro de explicaciones (ancho, alto)
    INFO_TOP = 428                     # borde superior de ese recuadro
    INFO_PADDING = 10                  # px de aire dentro del recuadro
    INFO_LINE_H = 24                   # px entre renglones de las explicaciones
    PARAGRAPH_GAP = 6                  # px extra entre párrafos

    def __init__(self, app):
        super().__init__(app)
        self.back_button = BackButton(self.back)

    def back(self):
        self.app.audio.play("back")
        self.app.switch(self.app.home())

    def handle_event(self, ev):
        if self.back_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN and (ev.key in BACK_KEYS or ev.key in OK_KEYS):
            self.back()

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_LIST)
        title(surf, "CONTROLES", (CENTER_X, self.TITLE_Y))
        for i in (0, 1):
            r = pygame.Rect((0, 0), self.PLAYER_PANEL)
            r.center = (self.PLAYER_PANEL_X[i], self.PLAYER_PANEL_Y)
            inner = panel(surf, r)
            pygame.draw.rect(surf, PLAYER_COLORS[i], (inner.left, inner.top, inner.width, self.COLOR_BAR_H))
            draw_text(surf, f"JUGADOR {i + 1} ({'izquierda' if i == 0 else 'derecha'})", FONT_TEXT,
                      (r.centerx, inner.top + self.HEADER_Y), PLAYER_COLORS[i], outline=C.INK)
            for k, (action, name) in enumerate(self.ACTION_NAMES):
                y = inner.top + self.FIRST_ACTION_Y + k * self.ACTION_STEP
                draw_text(surf, name, FONT_TEXT, (inner.left + self.ACTION_NAME_X, y), C.INK, anchor="midleft",
                          outline=None)
                keycap(surf, (inner.right - self.KEY_X, y), key_label(PLAYER_KEYS[i][action]))
        info = pygame.Rect((0, 0), self.INFO_PANEL)
        info.midtop = (CENTER_X, self.INFO_TOP)
        inner = panel(surf, info)
        lines = [
            f"{key_label(PAUSE_KEY)}: pausa  -  {key_label(DEBUG_PANEL_KEY)}: panel de depuración  -  "
            f"{key_label(FULLSCREEN_KEY)}: pantalla completa  -  {key_label(MUTE_KEY)}: silencio.",
            "Menús: W/S o flechas arriba/abajo; Enter, Espacio o P para elegir (también con el mouse).",
            "Elegir personaje: J1 con A/D y Espacio (W cancela); J2 con flechas y P (flecha arriba cancela).",
            "Mundialito y Online: valen las dos combinaciones. Online, Esc pide pausa (tras el próximo gol).",
            "Cabecear es tocar la pelota con la cabeza; la patada sale hacia donde mira el personaje.",
            "Aviso: muchos teclados no registran más de 3 o 4 teclas a la vez (\"ghosting\"). Si alguna "
            "combinación no responde es una limitación del teclado; las teclas se cambian en fdc/config.py.",
        ]
        y = inner.top + self.INFO_PADDING
        for ln in lines:
            for sub in wrap(ln, FONT_SMALL, inner.width - 2 * self.INFO_PADDING):
                draw_text(surf, sub, FONT_SMALL, (inner.left + self.INFO_PADDING, y), C.INK, anchor="topleft",
                          outline=None)
                y += self.INFO_LINE_H
            y += self.PARAGRAPH_GAP
        footer(surf, "Esc o Enter: volver")
        self.back_button.draw(surf, self.t)


# ---------------------------------------------------------------------------
# Leyenda de poderes
# ---------------------------------------------------------------------------
class LegendScreen(Screen):
    TITLE_Y = 34                       # título
    LEGEND_X0 = 150                    # x del primer texto de la leyenda de colores
    LEGEND_STEP = 380                  # px entre los tres textos de la leyenda
    LEGEND_Y = 84                      # centro vertical de la leyenda
    SWATCH = 24                        # px: cuadradito de color de la leyenda
    SWATCH_GAP = 30                    # px entre el cuadradito y su texto
    RULE_Y = 114                       # "Se activan cuando la PELOTA toca el objeto..."
    ROWS = 9                           # poderes por columna
    CARD = (608, 54)                   # tarjeta de cada poder (ancho, alto)
    CARD_X0 = 24                       # x de la primera columna
    CARD_COL_STEP = 624                # px entre columnas
    CARD_Y0 = 134                      # y de la primera tarjeta
    CARD_ROW_STEP = 60                 # px entre tarjetas
    CATEGORY_BAR_W = 6                 # franja con el color de la categoría
    ICON_SIZE = 40                     # px: ícono del poder
    ICON_X = 12                        # ícono, desde el borde izquierdo de la tarjeta
    ICON_Y = 3                         # ícono, desde el borde superior
    TEXT_X = 62                        # nombre y descripción, desde el borde izquierdo
    NAME_Y = 6                         # nombre, desde el borde superior
    DESCRIPTION_Y = 26                 # descripción, desde el borde superior
    DURATION_MARGIN = 10               # duración, desde el borde derecho

    def __init__(self, app):
        super().__init__(app)
        self.back_button = BackButton(self.back)

    def back(self):
        self.app.audio.play("back")
        self.app.switch(self.app.home())

    def handle_event(self, ev):
        if self.back_button.handle_event(ev):
            return
        if ev.type == pygame.KEYDOWN and (ev.key in BACK_KEYS or ev.key in OK_KEYS):
            self.back()

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, VEIL_BOOT)
        title(surf, "PODERES", (CENTER_X, self.TITLE_Y), FONT_TITLE)
        legend = [(CATEGORY_GOOD, "Verde: beneficia al receptor"), (CATEGORY_BAD, "Rojo: lo perjudica"),
                  (CATEGORY_GLOBAL, "Violeta: cambia el partido")]
        for k, (cat, label) in enumerate(legend):
            x = self.LEGEND_X0 + k * self.LEGEND_STEP
            box = pygame.Rect(x - self.SWATCH_GAP, self.LEGEND_Y - self.SWATCH // 2, self.SWATCH, self.SWATCH)
            bevel_box(surf, box, CATEGORY_COLORS[cat], shadow=False)
            draw_text(surf, label, FONT_SMALL, (x, self.LEGEND_Y), C.INK, anchor="midleft", outline=C.WHITE)
        draw_text(surf, "Se activan cuando la PELOTA toca el objeto. Receptor = último jugador que la tocó.",
                  FONT_SMALL, (CENTER_X, self.RULE_Y), C.INK, outline=C.WHITE)
        for i, p in enumerate(POWERS):
            col, row = (0, i) if i < self.ROWS else (1, i - self.ROWS)
            r = pygame.Rect((self.CARD_X0 + col * self.CARD_COL_STEP, self.CARD_Y0 + row * self.CARD_ROW_STEP),
                            self.CARD)
            inner = bevel_box(surf, r, C.CREAM)
            pygame.draw.rect(surf, CATEGORY_COLORS[p.category], (inner.left, inner.top, self.CATEGORY_BAR_W,
                                                                 inner.height))
            surf.blit(power_icon(p.id, self.ICON_SIZE), (inner.left + self.ICON_X, inner.top + self.ICON_Y))
            draw_text(surf, p.name, FONT_SMALL, (inner.left + self.TEXT_X, inner.top + self.NAME_Y), C.INK,
                      anchor="topleft", outline=None)
            draw_text(surf, p.description, FONT_SMALL, (inner.left + self.TEXT_X, inner.top + self.DESCRIPTION_Y),
                      C.INK_SOFT, anchor="topleft", outline=None)
            dur = "puntual" if p.duration <= 0 else f"{p.duration:g} s".replace(".", ",")
            draw_text(surf, dur, FONT_SMALL, (inner.right - self.DURATION_MARGIN, inner.top + self.NAME_Y),
                      CATEGORY_COLORS[p.category], anchor="topright", outline=C.INK)
        footer(surf, "Esc o Enter: volver  -  Repetir un poder renueva su duración; uno opuesto lo reemplaza")
        self.back_button.draw(surf, self.t)


# ---------------------------------------------------------------------------
# Error de la simulación
# ---------------------------------------------------------------------------
class ErrorScreen(Screen):
    TRACE_LINES = 3                    # últimas líneas del error técnico que se muestran
    TRACE_MAX_CHARS = 110              # caracteres por línea del error técnico
    MENU_CENTER = (CENTER_X, 560)      # botones Reintentar / Salir
    MENU_W = 300                       # ancho de esos botones
    BOX = (1040, 340)                  # recuadro del mensaje (ancho, alto)
    BOX_TOP = 80                       # borde superior del recuadro
    TITLE_Y = 36                       # título, desde arriba del recuadro
    MESSAGE_Y = 96                     # primer renglón del mensaje, desde arriba del recuadro
    MESSAGE_MARGIN = 40                # px de aire a los costados del mensaje
    MESSAGE_LINE_H = 32                # px entre renglones del mensaje
    TRACE_GAP = 8                      # px entre el mensaje y el error técnico
    HINT_BOTTOM = 18                   # ayuda, desde el borde inferior del recuadro

    def __init__(self, app, message, detail=""):
        super().__init__(app)
        self.message = message
        tb = [ln for ln in (detail or "").strip().splitlines() if ln.strip()]
        self.detail = tb[-self.TRACE_LINES:] if tb else []
        items = [("Reintentar", self.retry)] + ([] if app.web else [("Salir", app.quit)])
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
        dim(surf, VEIL_ERROR)
        r = pygame.Rect((0, 0), self.BOX)
        r.midtop = (CENTER_X, self.BOX_TOP)
        inner = panel(surf, r, face=C.ERROR_PANEL, border=C.RED)
        title(surf, "PROBLEMA CON LA SIMULACIÓN", (CENTER_X, inner.top + self.TITLE_Y), FONT_TITLE_S, C.RED)
        y = inner.top + self.MESSAGE_Y
        for ln in wrap(self.message, FONT_TEXT, inner.width - self.MESSAGE_MARGIN):
            draw_text(surf, ln, FONT_TEXT, (CENTER_X, y), C.INK, outline=None)
            y += self.MESSAGE_LINE_H
        y += self.TRACE_GAP
        for ln in self.detail:
            draw_text(surf, ln[:self.TRACE_MAX_CHARS], FONT_SMALL, (CENTER_X, y), C.INK_SOFT, outline=None)
            y += TEXT_LINE_H
        hint = ("Podés reintentar: la simulación vuelve a empezar." if getattr(self.app.link, "inline", False)
                else "La interfaz sigue funcionando: podés reintentar (se lanza un proceso nuevo) o salir.")
        draw_text(surf, hint, FONT_SMALL, (CENTER_X, inner.bottom - self.HINT_BOTTOM), C.INK, outline=None)
        self.menu.draw(surf)


def fps_value(clock):
    v = clock.get_fps()
    return v if v > 0 else FALLBACK_FPS
