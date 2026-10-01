"""Conductor de la interfaz sin ventana visible (SDL "dummy").

Lo usan las pruebas de humo de la UI: arranca la aplicación real (con su
proceso de simulación real) y la maneja con eventos de teclado sintéticos.
"""
import os
import time
import types

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

import helpers  # noqa: E402,F401  (agrega la raíz al path)


def profile_file(name="Prueba", player_id=None):
    """Perfil temporal para las pruebas (nunca se toca el del usuario).
    Con name=None el archivo queda vacío: el juego pide el nombre al empezar."""
    import tempfile
    from fdc import profile as prof
    path = os.path.join(tempfile.mkdtemp(prefix="fdc-perfil-"), "perfil.json")
    if name:
        prof.save(prof.Profile(name, player_id), path)
    return path


def make_app(test_mode=True, seed=5, duration=None, server_url=None, profile_name="Prueba", web=False):
    from fdc.ui.app import App
    opts = types.SimpleNamespace(test_mode=test_mode, seed=seed, no_audio=False, fullscreen=False,
                                 debug_panel=True, duration=duration,
                                 # sin servidor salvo que la prueba lo levante (nunca uno real)
                                 server_url=server_url or "ws://127.0.0.1:1/ws",
                                 profile_path=profile_file(profile_name), web=web)
    return App(opts)


class Driver:
    def __init__(self, app, shots_dir=None):
        self.app = app
        self.shots_dir = shots_dir
        self.each_frame = None      # p. ej. leer los mensajes de un rival de prueba

    def frames(self, n=1):
        for _ in range(n):
            self.app.frame()

    def until(self, cond, timeout=10.0, what="condición"):
        t0 = time.monotonic()
        while not cond():
            self.app.frame()
            if self.each_frame:
                self.each_frame()
            if time.monotonic() - t0 > timeout:
                raise AssertionError(f"tiempo agotado esperando {what}")

    def seconds(self, s):
        t0 = time.monotonic()
        while time.monotonic() - t0 < s:
            self.app.frame()

    def down(self, key):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))
        self.app.frame()

    def up(self, key):
        pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, mod=0, unicode="", scancode=0))
        self.app.frame()

    def tap(self, key, frames_after=2):
        self.down(key)
        self.up(key)
        self.frames(frames_after)

    def post(self, etype, **kw):
        pygame.event.post(pygame.event.Event(etype, **kw))
        self.app.frame()

    def screen(self):
        return self.app.current

    def shot(self, name):
        if self.shots_dir:
            pygame.image.save(self.app.screen, os.path.join(self.shots_dir, name + ".png"))
