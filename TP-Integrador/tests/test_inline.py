"""Simulación dentro de la página (versión de navegador) y la app en modo web.

En el navegador no hay procesos: InlineLink corre el MISMO núcleo de
simulación que el proceso de escritorio, con el mismo protocolo (órdenes con
ACK, fotos de controles con contadores, estados con partido y seq).
"""
import types
import unittest

import driver  # configura SDL dummy antes de importar pygame
import pygame

from fdc import protocol as P
from fdc.config import MAX_CATCHUP_STEPS, PHYSICS_DT, MatchRules
from fdc.sim.inline import InlineLink


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class InlineLinkTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.link = InlineLink(seed=3, clock=self.clock)
        self.link.start()

    def poll(self, seconds=0.0, frame=1 / 60):
        """Avanza el reloj de a cuadros y junta lo que devuelve la simulación."""
        msgs, state = self.link.poll()
        left = seconds
        while left > 1e-9:
            self.clock.t += min(frame, left)
            left -= frame
            m, st = self.link.poll()
            msgs += m
            state = st or state
        return msgs, state

    def start_match(self):
        self.link.poll()
        cid = self.link.send_command(P.CMD_START, match=7, characters=["messi", "pele"])
        msgs, state = self.poll()
        ack = [m for m in msgs if m["type"] == P.EV_ACK]
        self.assertEqual((ack[0]["cid"], ack[0]["ok"]), (cid, True))
        self.assertEqual((state["match"], state["phase"]), (7, P.PHASE_COUNTDOWN))
        _, state = self.poll(MatchRules.KICKOFF_COUNTDOWN + 0.1)
        self.assertEqual(state["phase"], P.PHASE_PLAYING)
        return state

    def test_ready_ack_states_and_controls(self):
        self.assertFalse(self.link.ready)
        self.link.poll()
        self.assertTrue(self.link.ready)                    # READY, como el proceso
        st = self.start_match()
        x0, seq0 = st["players"][0]["x"], st["seq"]
        self.link.send_input([[False, True, 0, 0], [False, False, 0, 0]])
        _, st = self.poll(0.5)
        self.assertGreater(st["players"][0]["x"], x0 + 40)  # la simulación movió al jugador
        self.assertGreater(st["seq"], seq0)
        self.link.send_input([[False, False, 1, 0], [False, False, 0, 0]])   # una pulsación de salto
        _, st = self.poll(0.1)
        self.assertFalse(st["players"][0]["ground"])

    def test_pause_freezes_clock_and_resume_counts_down(self):
        self.start_match()
        self.link.send_command(P.CMD_PAUSE, reason=P.PAUSE_REASON_USER)
        msgs, st = self.poll()
        self.assertTrue(st["paused"])
        clock = st["clock"]
        self.poll(2.0)
        self.link.send_command(P.CMD_RESUME)
        msgs, st = self.poll()
        self.assertEqual(st["clock"], clock)                # en pausa el reloj no corre
        self.assertEqual(st["phase"], P.PHASE_COUNTDOWN)

    def test_long_stall_is_not_recovered_all_at_once(self):
        st = self.start_match()
        tick = st["tick"]
        self.clock.t += 5.0                                 # la página estuvo trabada 5 s
        _, st = self.link.poll()
        self.assertLessEqual(st["tick"] - tick, MAX_CATCHUP_STEPS)

    def test_simulation_error_is_reported_not_raised(self):
        link = InlineLink(test_mode=True, clock=self.clock)
        link.start()
        link.poll()
        link.send_command(P.CMD_START, match=1)
        link.poll()
        link.send_command(P.CMD_DEBUG_CRASH)
        link.poll()                                         # no rompe la interfaz
        self.assertIn("Fallo provocado", link.check_health())
        link.restart()
        link.poll()
        self.assertIsNone(link.check_health())

    def test_states_are_the_same_shape_as_the_process(self):
        st = self.start_match()
        for key in ("match", "seq", "tick", "phase", "clock", "score", "players", "ball", "goals",
                    "effects", "dropped_states"):
            self.assertIn(key, st)
        self.assertEqual(PHYSICS_DT, 1 / 120)


class WebAppTest(unittest.TestCase):
    """La app como en el navegador: menú completo, Mundialito y local sin procesos."""

    def test_full_game_without_processes(self):
        from fdc.ui.app import App
        from fdc.ui.match_screens import MatchScreen, SelectScreen
        from fdc.ui.mundialito_screens import HubScreen, MundialitoMatchScreen, PickScreen
        from fdc.ui.online_screens import OnlineHomeScreen
        from fdc.ui.screens import MenuScreen, MultiplayerMenuScreen, PlayMenuScreen

        opts = types.SimpleNamespace(web=True, test_mode=False, seed=4, no_audio=False, fullscreen=False,
                                     debug_panel=True, duration=None, server_url="ws://127.0.0.1:1/ws",
                                     profile_path=driver.profile_file("Web"))
        app = App(opts)
        d = driver.Driver(app)
        try:
            self.assertIsInstance(app.link, InlineLink)
            d.until(lambda: isinstance(d.screen(), MenuScreen), 10, "menú")
            labels = [label for label, _ in d.screen().menu.items]
            self.assertEqual(labels, ["Jugar", "Controles", "Poderes"])   # sin "Salir" en la web
            d.tap(pygame.K_RETURN)
            self.assertIsInstance(d.screen(), PlayMenuScreen)
            d.tap(pygame.K_RETURN)                       # Mundialito
            self.assertIsInstance(d.screen(), PickScreen)
            d.tap(pygame.K_RETURN)
            self.assertIsInstance(d.screen(), HubScreen)
            d.tap(pygame.K_RETURN)                       # jugar la etapa
            d.until(lambda: isinstance(d.screen(), MundialitoMatchScreen), 5, "partido del Mundialito")
            ms = d.screen()
            d.until(lambda: ms.state is not None and ms.state["phase"] == "playing", 8, "juego")
            x0 = ms.state["players"][1]["x"]
            d.down(pygame.K_LEFT)
            d.seconds(0.5)
            d.up(pygame.K_LEFT)
            self.assertLess(ms.state["players"][1]["x"], x0 - 40)
            d.tap(pygame.K_ESCAPE)                       # pausa confirmada por la simulación
            d.until(lambda: ms.pause_state == "paused", 3, "pausa")
            ms.abandon()                                 # menú desde la pausa = abandonar
            self.assertIsInstance(d.screen(), MenuScreen)

            d.tap(pygame.K_RETURN)                       # Jugar
            d.tap(pygame.K_s)
            d.tap(pygame.K_RETURN)                       # Multijugador
            self.assertIsInstance(d.screen(), MultiplayerMenuScreen)
            d.tap(pygame.K_RETURN)                       # Local
            self.assertIsInstance(d.screen(), SelectScreen)
            d.tap(pygame.K_SPACE)
            d.tap(pygame.K_p)
            d.until(lambda: isinstance(d.screen(), MatchScreen), 5, "partido local")
            ms = d.screen()
            d.until(lambda: ms.state is not None and ms.state["phase"] == "playing", 8, "juego local")
            x0, x1 = ms.state["players"][0]["x"], ms.state["players"][1]["x"]
            d.down(pygame.K_d)
            d.down(pygame.K_LEFT)
            d.seconds(0.5)
            d.up(pygame.K_d)
            d.up(pygame.K_LEFT)
            self.assertGreater(ms.state["players"][0]["x"], x0 + 40)    # dos personas, un teclado
            self.assertLess(ms.state["players"][1]["x"], x1 - 40)
            d.tap(pygame.K_ESCAPE)
            d.until(lambda: ms.pause_state == "paused", 3, "pausa local")
            ms.to_menu()

            d.tap(pygame.K_RETURN)
            d.tap(pygame.K_s)
            d.tap(pygame.K_RETURN)
            d.tap(pygame.K_s)
            d.tap(pygame.K_RETURN)                       # Online
            self.assertIsInstance(d.screen(), OnlineHomeScreen)
            self.assertTrue(d.screen().back_button.visible)
            d.tap(pygame.K_ESCAPE)
            self.assertIsInstance(d.screen(), MultiplayerMenuScreen)
        finally:
            app.running = False
            app.shutdown()


if __name__ == "__main__":
    unittest.main()
