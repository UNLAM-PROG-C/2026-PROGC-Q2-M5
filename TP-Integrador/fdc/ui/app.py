"""Proceso principal: ventana, eventos, pantallas, dibujo y sonido.

Todo el manejo de eventos de pygame ocurre en ESTE hilo (el que creó la
ventana), como indica la documentación de pygame.event. La interfaz nunca se
bloquea esperando a la simulación: en cada cuadro lee lo que haya llegado
(get_nowait) y dibuja el último estado válido. El ritmo lo marca
clock.tick(60), que duerme entre cuadros (no hay espera activa).
"""
import logging
import os
import sys
import time
from collections import deque

import pygame

from ..config import (DEBUG_PANEL_KEY, FULLSCREEN_KEY, GAME_NAME, LOGICAL_HEIGHT, LOGICAL_WIDTH,
                      MUTE_KEY, PHYSICS_HZ, UI_FPS)
from ..ipc import SimLink
from .assets import clear_caches, draw_text
from . import palette as C
from . import pixelfont
from .audio import Audio
from .sprites import CharacterSprites
from .fx import Effects
from .input import InputTracker, key_code
from .screens import BootScreen, ErrorScreen, fps_value
from .stadium import BallSprite, build_background

log = logging.getLogger("fdc.ui")


class FrameLimiter:
    """Limita a N cuadros por segundo DURMIENDO hasta el plazo del cuadro.

    Se usa en lugar de pygame.time.Clock.tick() porque en macOS ese método
    duerme de más (queda en ~47 FPS al pedir 60). time.sleep libera la CPU:
    no es una espera activa.
    """

    def __init__(self, fps):
        self.period = 1.0 / fps
        self.deadline = time.perf_counter()
        self.last = self.deadline
        self.samples = deque(maxlen=60)

    def tick(self):
        self.deadline += self.period
        now = time.perf_counter()
        remaining = self.deadline - now
        if remaining > 0:
            time.sleep(remaining)
        else:
            self.deadline = now        # cuadro atrasado: no intentar "recuperar"
        now = time.perf_counter()
        dt = now - self.last
        self.last = now
        self.samples.append(dt)
        return dt

    def get_fps(self):
        if not self.samples:
            return 0.0
        return len(self.samples) / max(1e-6, sum(self.samples))


class App:
    def __init__(self, options):
        self.options = options
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption(GAME_NAME)
        flags = pygame.SCALED | pygame.RESIZABLE   # escala conservando la proporción
        if options.fullscreen:
            flags |= pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((LOGICAL_WIDTH, LOGICAL_HEIGHT), flags)
        self.clock = FrameLimiter(UI_FPS)
        self.audio = Audio(enabled=not options.no_audio)
        self.sprites = CharacterSprites()
        self.ball_sprite = BallSprite()
        self.background = build_background()
        self._set_icon()
        self.fx = Effects()
        self.input = InputTracker()
        self.last_characters = None
        self.tournament = None          # Mundialito en curso (sólo en memoria)
        self.match_counter = 0
        self.show_debug = options.debug_panel
        self.running = True
        self.keys = {k: key_code(k) for k in (DEBUG_PANEL_KEY, FULLSCREEN_KEY, MUTE_KEY)}

        # El proceso de simulación arranca ANTES de mostrar el menú; la
        # pantalla de arranque espera su READY sin bloquear la ventana.
        self.link = SimLink(test_mode=options.test_mode, seed=options.seed,
                            duration=getattr(options, "duration", None))
        self.link.start()
        self.current = BootScreen(self)
        self.current.enter()

    def _set_icon(self):
        icon = pygame.Surface((64, 64), pygame.SRCALPHA)
        self.ball_sprite.draw(icon, 32, 32, 28, 20)
        pygame.display.set_icon(icon)

    # ------------------------------------------------------------------ navegación
    def switch(self, screen):
        self.current.leave()
        self.current = screen
        screen.enter()

    def next_match_id(self):
        self.match_counter += 1
        return self.match_counter

    def quit(self):
        self.running = False

    def restart_simulation(self):
        """Tras un error: cierre coordinado del proceso viejo y uno nuevo."""
        self.link.restart()
        self.switch(BootScreen(self))

    # ------------------------------------------------------------------ bucle
    def frame(self):
        """Un cuadro: eventos -> mensajes de la SIM -> salud -> lógica de pantalla -> dibujo."""
        dt = min(self.clock.tick(), 0.1)
        for ev in pygame.event.get():
            self.handle_event(ev)
            if not self.running:
                return
        msgs, state = self.link.poll()
        self.current.on_link(msgs, state)
        err = self.link.check_health()
        if err and not isinstance(self.current, ErrorScreen):
            self.switch(ErrorScreen(self, err, self.link.error_detail))
        self.current.update(dt)
        self.current.draw(self.screen)
        if self.show_debug:
            self.draw_debug(self.screen)
        pygame.display.flip()

    def run(self):
        try:
            while self.running:
                self.frame()
        except KeyboardInterrupt:
            log.info("interrupción desde la terminal: cerrando ordenadamente")
        finally:
            self.shutdown()

    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.running = False          # cierre desde cualquier pantalla
            return
        if ev.type in (pygame.WINDOWFOCUSLOST, pygame.WINDOWMINIMIZED):
            # ningún jugador queda "caminando" con una tecla trabada
            self.input.release_all()
            self.current.on_focus_lost()
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key == self.keys[DEBUG_PANEL_KEY]:
                self.show_debug = not self.show_debug
                return
            if ev.key == self.keys[FULLSCREEN_KEY]:
                pygame.display.toggle_fullscreen()
                return
            if ev.key == self.keys[MUTE_KEY]:
                self.audio.toggle_mute()
                return
        self.input.handle_event(ev)
        self.current.handle_event(ev)

    def shutdown(self):
        try:
            self.audio.crowd(False)
        except pygame.error:
            pass
        report = self.link.stop()
        log.info("cierre completo: %s", report)
        clear_caches()
        pygame.quit()

    # ------------------------------------------------------------------ panel F3
    def draw_debug(self, surf):
        li = self.link.debug_lines()
        si = self.current.debug_info()
        info = self.link.ready_info or {}
        yes = lambda v: "sí" if v else "no"  # noqa: E731
        clock = f"{si['clock']:.2f} s" if si.get("clock") is not None else "-"
        lines = [
            ("PANEL DE DEPURACIÓN (F3)", C.GOLD),
            (f"UI pid {os.getpid()}  |  SIM pid {li['sim_pid']} ({'viva' if li['alive'] else 'detenida'}), "
             f"pygame en SIM: {yes(info.get('pygame_loaded'))}", None),
            (f"Pantalla {type(self.current).__name__}  |  partido #{si.get('match', '-')}  |  "
             f"fase {si.get('phase', '-')}", None),
            (f"Pausa SIM: {yes(si.get('paused'))}  |  pausa UI: {si.get('ui_pause', '-')}  |  reloj {clock}", None),
            (f"Actualización seq {si.get('seq', '-')}  |  tick {si.get('tick', '-')}", None),
            (f"Último confirmado: {li['confirmed']}", None),
            (f"Órdenes sin confirmar: {li['pending']}  |  controles: {li['inputs']}", None),
            (f"Recibidos: {li['received']}", None),
            (f"Estados ignorados: {si.get('filtered', '-')}", None),
            (f"SIM reemplazó {si.get('sim_dropped', 0)} estados  |  eventos cosméticos perdidos "
             f"{si.get('cosmetic_dropped', 0)}  |  eventos viejos {si.get('ignored_events', 0)}", None),
            (f"FPS UI {fps_value(self.clock):.0f}  |  física {PHYSICS_HZ} Hz  |  prueba: "
             f"{yes(self.options.test_mode)}  |  semilla {self.options.seed}", None),
        ]
        w = max(pixelfont.text_width(t, 2) for t, _ in lines) + 24
        h = len(lines) * 24 + 14
        box = pygame.Surface((w, h), pygame.SRCALPHA)
        box.fill((*C.INK, 225))
        surf.blit(box, (8, 720 - h - 8))
        pygame.draw.rect(surf, C.GOLD, (8, 720 - h - 8, w, h), 2)
        for k, (t, col) in enumerate(lines):
            draw_text(surf, t, 16, (20, 720 - h + 2 + k * 24), col or C.CREAM, anchor="topleft", outline=None)


def run_app(options):
    app = App(options)
    app.run()
    return 0


def setup_logging():
    from ..config import LOG_DIR
    fmt = "%(asctime)s [%(processName)s pid=%(process)d] %(levelname)s %(name)s: %(message)s"
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handlers.append(logging.FileHandler(os.path.join(LOG_DIR, "fdc.log"), mode="w", encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers, force=True)
