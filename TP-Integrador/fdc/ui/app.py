"""Proceso principal: ventana, eventos, pantallas, dibujo y sonido.

Todo el manejo de eventos de pygame ocurre en ESTE hilo (el que creó la
ventana), como indica la documentación de pygame.event. La interfaz nunca se
bloquea esperando a la simulación ni a la red: en cada cuadro lee lo que haya
llegado (get_nowait) y dibuja el último estado válido. El ritmo lo marca
FrameLimiter, que duerme entre cuadros (no hay espera activa).

En el navegador (pygbag) está el juego completo, pero no hay procesos: los
modos locales simulan en la misma página (InlineLink, fdc/sim/inline.py, con el
mismo núcleo de simulación), el online usa el proceso de la sala en el
servidor, y el bucle es asíncrono: cada cuadro le devuelve el control al
navegador.
"""
import logging
import os
import sys
import time
from collections import deque

import pygame

from ..config import (DEBUG_PANEL_KEY, FULLSCREEN_KEY, GAME_NAME, LOGICAL_HEIGHT, LOGICAL_WIDTH,
                      MUTE_KEY, PHYSICS_HZ, UI_FPS)
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

    def __init__(self, fps, sleep=True):
        self.sleep = sleep        # en el navegador el ritmo lo marca el propio navegador
        self.period = 1.0 / fps
        self.deadline = time.perf_counter()
        self.last = self.deadline
        self.samples = deque(maxlen=60)

    def tick(self):
        self.deadline += self.period
        now = time.perf_counter()
        remaining = self.deadline - now
        if remaining > 0 and self.sleep:
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
        self.web = bool(getattr(options, "web", False))   # versión de navegador (pygbag)
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption(GAME_NAME)
        if self.web:
            flags = 0                                  # el navegador escala el lienzo
        else:
            flags = pygame.SCALED | pygame.RESIZABLE   # escala conservando la proporción
            if options.fullscreen:
                flags |= pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((LOGICAL_WIDTH, LOGICAL_HEIGHT), flags)
        self.clock = FrameLimiter(UI_FPS, sleep=not self.web)
        if self.web:
            from .browser import install_key_guard
            install_key_guard()         # Esc, F3, Tab y flechas no disparan acciones del navegador
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
        self.net = None                 # conexión con el servidor online (al entrar a Online)
        self.first_frame_shown = False
        self.server_url = getattr(options, "server_url", None)
        self.last_online_char = None
        # nombre del jugador: se elige al empezar (una sola vez) y vale para todos los modos
        from .. import profile as prof
        self.profile_path = getattr(options, "profile_path", None)
        self.profile = prof.load(self.profile_path)

        # El proceso de simulación arranca ANTES de mostrar el menú; la
        # pantalla de arranque espera su READY sin bloquear la ventana.
        # En el navegador no hay procesos: la simulación local corre en la página.
        duration = getattr(options, "duration", None)
        if self.web:
            from ..sim.inline import InlineLink
            self.link = InlineLink(test_mode=options.test_mode, seed=options.seed, duration=duration)
        else:
            from ..ipc import SimLink   # acá y no arriba: en el navegador no hay multiprocessing
            self.link = SimLink(test_mode=options.test_mode, seed=options.seed, duration=duration)
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

    def home(self):
        """El menú principal (igual en escritorio y navegador)."""
        from .screens import MenuScreen
        return MenuScreen(self)

    def first_screen(self):
        """Después del arranque: el nombre (si todavía no lo eligió) y después el
        menú. Si el navegador se recargó en medio del online, vuelve a la sala."""
        if self.profile is None:
            from .profile_screen import ProfileScreen
            return ProfileScreen(self, first_run=True)
        if self.web:
            from ..online.client import saved_session
            if saved_session():
                from .online_screens import OnlineHomeScreen
                return OnlineHomeScreen(self)
        return self.home()

    def set_profile(self, profile):
        from .. import profile as prof
        self.profile = profile
        prof.save(profile, self.profile_path)
        self.close_online()             # el online vuelve a entrar con el nombre nuevo

    def online(self):
        """Cliente de red (se crea la primera vez que se entra a Online)."""
        if self.net is None:
            from ..online.client import NetClient
            self.net = NetClient(self.server_url)
        return self.net

    def close_online(self):
        if self.net is not None:
            self.net.close()
            self.net = None

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
        if self.link is not None:
            msgs, state = self.link.poll()
            self.current.on_link(msgs, state)
            err = self.link.check_health()
            if err and not isinstance(self.current, ErrorScreen):
                self.switch(ErrorScreen(self, err, self.link.error_detail))
        if self.net is not None:
            # de a uno: si un mensaje cambia de pantalla, los siguientes ya
            # los recibe la pantalla nueva (no se pierde ninguno)
            for msg in self.net.poll():
                self.current.on_net(msg)
        self.current.update(dt)
        self.current.draw(self.screen)
        if self.show_debug:
            self.draw_debug(self.screen)
        pygame.display.flip()
        if self.web and not self.first_frame_shown:
            self.first_frame_shown = True
            from .browser import hide_loading_screen
            hide_loading_screen()

    def run(self):
        try:
            while self.running:
                self.frame()
        except KeyboardInterrupt:
            log.info("interrupción desde la terminal: cerrando ordenadamente")
        finally:
            self.shutdown()

    async def run_async(self):
        """Bucle del navegador: cada cuadro le devuelve el control (sin dormir)."""
        import asyncio
        try:
            while self.running:
                self.frame()
                await asyncio.sleep(0)
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
                if not self.web:
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
        self.close_online()
        if self.link is not None:
            report = self.link.stop()
            log.info("cierre completo: %s", report)
        clear_caches()
        pygame.quit()

    # ------------------------------------------------------------------ panel F3
    def draw_debug(self, surf):
        si = self.current.debug_info()
        yes = lambda v: "sí" if v else "no"  # noqa: E731
        clock = f"{si['clock']:.2f} s" if si.get("clock") is not None else "-"
        lines = [("PANEL DE DEPURACIÓN (F3)", C.GOLD)]
        if self.link is not None:
            li = self.link.debug_lines()
            info = self.link.ready_info or {}
            if getattr(self.link, "inline", False):
                lines.append(("Navegador: sin procesos; la simulación local corre en la misma página "
                              "(el online, en el servidor)", None))
            else:
                lines.append((f"UI pid {os.getpid()}  |  SIM pid {li['sim_pid']} "
                              f"({'viva' if li['alive'] else 'detenida'}), "
                              f"pygame en SIM: {yes(info.get('pygame_loaded'))}", None))
        lines += [
            (f"Pantalla {type(self.current).__name__}  |  partido #{si.get('match', '-')}  |  "
             f"fase {si.get('phase', '-')}", None),
            (f"Pausa SIM: {yes(si.get('paused'))}  |  pausa UI: {si.get('ui_pause', '-')}  |  reloj {clock}", None),
            (f"Actualización seq {si.get('seq', '-')}  |  tick {si.get('tick', '-')}", None),
        ]
        if self.link is not None:
            lines += [
                (f"Último confirmado: {li['confirmed']}", None),
                (f"Órdenes sin confirmar: {li['pending']}  |  controles: {li['inputs']}", None),
                (f"Recibidos: {li['received']}", None),
            ]
        if self.net is not None:
            ni = self.net.debug_lines()
            lines += [
                (f"Online: {ni['status']} como {ni['user']}  |  latencia {ni['rtt']}  |  {ni['url']}", None),
                (f"Mensajes: {ni['traffic']}", None),
            ]
            ri = self.net.room_info
            if ri:                           # la sala vista desde el servidor (llega una vez por segundo)
                ack = f"{ri['ack_ms']:.1f} ms" if ri.get("ack_ms") is not None else "-"
                lines += [
                    (f"Servidor pid {ri['server_pid']}  |  sala {ri['room']}: proceso de simulación pid "
                     f"{ri['sim_pid']} ({'vivo' if ri['sim_alive'] else 'detenido'})  |  partido #{ri['match']}",
                     C.GOLD),
                    (f"La sala manda {ri['states_per_s']:.0f} estados/s  |  recibe {ri['inputs_per_s']:.0f} "
                     f"fotos de controles/s  |  último ACK {ack}  |  sin confirmar {ri['pending_acks']}  |  "
                     f"pausa: {', '.join(ri['hold']) or '-'}", None),
                ]
        lines += [
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
