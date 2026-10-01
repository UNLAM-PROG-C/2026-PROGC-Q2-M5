"""Prueba de humo de la interfaz real, sin ventana visible (SDL "dummy").

Recorre: arranque -> menú -> selección -> partido (controles, poderes de
prueba, pausa confirmada, pérdida de foco, reinicio) -> resultado ->
revancha -> menú -> cierre coordinado. Usa el proceso de simulación real.
"""
import unittest

import driver  # configura SDL dummy antes de importar pygame
import pygame

from fdc.config import POWER_IDS
from fdc.ui.match_screens import MatchScreen, ResultScreen, SelectScreen
from fdc.ui.online_screens import OnlineHomeScreen
from fdc.ui.screens import (ControlsScreen, LegendScreen, MenuScreen, MultiplayerMenuScreen,
                            PlayMenuScreen)


class UISmokeTest(unittest.TestCase):
    def test_full_flow(self):
        app = driver.make_app(test_mode=True, seed=5, duration=8)
        d = driver.Driver(app)
        try:
            d.until(lambda: isinstance(d.screen(), MenuScreen), 20, "menú")
            d.tap(pygame.K_s)
            d.tap(pygame.K_RETURN)
            self.assertIsInstance(d.screen(), ControlsScreen)
            d.tap(pygame.K_ESCAPE)
            d.tap(pygame.K_s)
            d.tap(pygame.K_s)
            d.tap(pygame.K_RETURN)
            self.assertIsInstance(d.screen(), LegendScreen)
            d.tap(pygame.K_ESCAPE)
            d.tap(pygame.K_RETURN)                      # Jugar
            self.assertIsInstance(d.screen(), PlayMenuScreen)
            d.tap(pygame.K_s)
            d.tap(pygame.K_RETURN)                      # Multijugador
            self.assertIsInstance(d.screen(), MultiplayerMenuScreen)
            d.tap(pygame.K_s)
            d.tap(pygame.K_RETURN)                      # Online: pide el nombre de usuario
            self.assertIsInstance(d.screen(), OnlineHomeScreen)
            d.tap(pygame.K_ESCAPE)                      # volver sin conectarse
            self.assertIsInstance(d.screen(), MultiplayerMenuScreen)
            self.assertIsNone(app.net)
            d.tap(pygame.K_RETURN)                      # Local: el juego de siempre
            self.assertIsInstance(d.screen(), SelectScreen)

            # ambos eligen el MISMO personaje (permitido)
            sel = d.screen()
            sel.cursor = [0, 0]
            d.tap(pygame.K_SPACE)
            d.tap(pygame.K_p)
            d.until(lambda: isinstance(d.screen(), MatchScreen), 5, "partido")
            ms = d.screen()
            self.assertEqual(ms.chars, ["messi", "messi"])
            d.until(lambda: ms.state is not None and ms.state["phase"] == "playing", 8, "juego")

            # J1 camina a la derecha: la posición la decide la simulación
            x0 = ms.state["players"][0]["x"]
            d.down(pygame.K_d)
            d.seconds(0.4)
            d.up(pygame.K_d)
            d.seconds(0.1)
            self.assertGreater(ms.state["players"][0]["x"], x0 + 40)

            # un salto breve (una sola pulsación) no se pierde
            d.tap(pygame.K_w, 0)
            d.until(lambda: not ms.state["players"][0]["ground"], 1, "salto")

            # poder de prueba a J2
            ms.test_sel = POWER_IDS.index("shrink")
            d.tap(pygame.K_F9)
            d.until(lambda: any(e["target"] == "p1" for e in ms.state["effects"]), 2, "efecto")

            # pausa confirmada: el reloj no avanza
            d.down(pygame.K_ESCAPE)
            # la pausa se muestra recién con el ACK (puede llegar en el mismo cuadro)
            self.assertIn(ms.pause_state, ("requested", "paused"))
            d.up(pygame.K_ESCAPE)
            d.until(lambda: ms.pause_state == "paused", 3, "confirmación de pausa")
            c1 = ms.state["clock"]
            d.seconds(0.6)
            self.assertEqual(ms.state["clock"], c1)
            d.tap(pygame.K_ESCAPE)
            d.until(lambda: ms.pause_state is None, 3, "continuar")

            # pérdida de foco: se liberan teclas y se pide pausa
            d.until(lambda: ms.state["phase"] == "playing", 4, "juego tras la cuenta")
            d.down(pygame.K_a)
            self.assertTrue(app.input.held[0]["left"])
            d.post(pygame.WINDOWFOCUSLOST)
            self.assertFalse(app.input.held[0]["left"])
            d.until(lambda: ms.pause_state == "paused", 3, "pausa por foco")

            # reiniciar: partido nuevo, sin efectos, estados viejos ignorados
            old = ms.match_id
            d.tap(pygame.K_s)
            d.tap(pygame.K_RETURN)
            d.until(lambda: ms.state is not None and ms.state["match"] != old, 4, "reinicio")
            self.assertEqual(ms.state["effects"], [])
            self.assertEqual(ms.state["score"], [0, 0])

            # partido corto hasta el final
            d.until(lambda: isinstance(d.screen(), ResultScreen), 25, "resultado")
            d.tap(pygame.K_RETURN)                      # revancha
            self.assertIsInstance(d.screen(), MatchScreen)
            self.assertEqual(d.screen().chars, ["messi", "messi"])
            d.until(lambda: d.screen().state is not None, 5, "revancha")
            d.tap(pygame.K_ESCAPE)
            d.until(lambda: d.screen().pause_state == "paused", 3, "pausa")
            d.tap(pygame.K_s)
            d.tap(pygame.K_s)
            d.tap(pygame.K_RETURN)
            self.assertIsInstance(d.screen(), MenuScreen)
            self.assertIsNone(app.link.error)

            d.post(pygame.QUIT)
            self.assertFalse(app.running)
        finally:
            app.shutdown()
        report = app.link.shutdown_report
        self.assertEqual(report["method"], "ordenado")
        self.assertTrue(report["bye"])

    def test_mundialito_flow(self):
        from fdc.mundialito import HUMAN_SLOT, IN_PROGRESS
        from fdc.ui.mundialito_screens import HubScreen, MundialitoMatchScreen, MundialitoResultScreen, PickScreen
        app = driver.make_app(test_mode=True, seed=3, duration=3)
        d = driver.Driver(app)
        try:
            d.until(lambda: isinstance(d.screen(), MenuScreen), 20, "menú")
            d.tap(pygame.K_RETURN)                      # Jugar
            d.tap(pygame.K_RETURN)                      # Mundialito
            self.assertIsInstance(d.screen(), PickScreen)
            d.tap(pygame.K_RIGHT)
            d.tap(pygame.K_SPACE)                       # elige y confirma
            self.assertIsInstance(d.screen(), HubScreen)
            t = app.tournament
            self.assertEqual(len(t.rivals), 6)
            self.assertNotIn(t.player, t.rivals)
            d.tap(pygame.K_RETURN)                      # Jugar Fecha 1
            ms = d.screen()
            self.assertIsInstance(ms, MundialitoMatchScreen)
            self.assertEqual(ms.chars[HUMAN_SLOT], t.player)
            d.until(lambda: ms.state is not None and ms.state["phase"] == "playing", 8, "juego")
            # la persona controla el lugar de la derecha con cualquiera de los dos juegos de teclas
            x0 = ms.state["players"][HUMAN_SLOT]["x"]
            d.down(pygame.K_LEFT)
            d.seconds(0.3)
            d.up(pygame.K_LEFT)
            d.down(pygame.K_a)
            d.seconds(0.3)
            d.up(pygame.K_a)
            d.seconds(0.1)
            self.assertLess(ms.state["players"][HUMAN_SLOT]["x"], x0 - 60)
            # forzamos el resultado: gol de la persona y fin del partido corto
            d.until(lambda: isinstance(d.screen(), MundialitoResultScreen), 60, "fin del partido")
            rs = d.screen()
            self.assertEqual(len(rs.t_.results), 1)
            self.assertNotEqual(rs.t_.results[0][2], rs.t_.results[0][3])   # gol de oro: sin empates
            if rs.won:
                self.assertEqual(app.tournament.status, IN_PROGRESS)
                d.tap(pygame.K_s)
                d.tap(pygame.K_RETURN)                  # Menú principal: el progreso queda
                self.assertIsInstance(d.screen(), MenuScreen)
                d.tap(pygame.K_RETURN)
                d.tap(pygame.K_RETURN)                  # Jugar > Mundialito: vuelve a la llave
                self.assertIsInstance(d.screen(), HubScreen)
                self.assertEqual(app.tournament.stage, 1)
            else:
                self.assertIsNone(app.tournament)       # eliminado: hay que empezar de nuevo
                self.assertEqual(rs.t_.position, 7)
            # abandonar desde la pausa de un partido descarta el Mundialito
            if not isinstance(d.screen(), HubScreen):
                d.tap(pygame.K_RETURN)                  # Empezar de nuevo
                d.tap(pygame.K_SPACE)
            d.tap(pygame.K_RETURN)                      # Jugar la etapa
            ms = d.screen()
            d.until(lambda: ms.state is not None, 5, "estado")
            d.tap(pygame.K_ESCAPE)
            d.until(lambda: ms.pause_state == "paused", 3, "pausa")
            d.tap(pygame.K_s)
            d.tap(pygame.K_RETURN)                      # Abandonar Mundialito
            self.assertIsInstance(d.screen(), MenuScreen)
            self.assertIsNone(app.tournament)
        finally:
            app.shutdown()
        self.assertEqual(app.link.shutdown_report["method"], "ordenado")

    def test_back_buttons(self):
        from fdc.ui.match_screens import MatchScreen, SelectScreen
        from fdc.ui.mundialito_screens import HubScreen, PickScreen
        from fdc.ui.screens import BackButton
        app = driver.make_app(test_mode=False, seed=2)
        d = driver.Driver(app)
        back = BackButton.RECT.center

        def click(pos):
            d.post(pygame.MOUSEBUTTONDOWN, pos=pos, button=1)
            d.frames(2)
        try:
            d.until(lambda: isinstance(d.screen(), MenuScreen), 20, "menú")
            for screen_cls, expected in ((ControlsScreen, MenuScreen), (LegendScreen, MenuScreen),
                                         (SelectScreen, MultiplayerMenuScreen), (PickScreen, PlayMenuScreen)):
                app.switch(screen_cls(app))
                d.frames(2)
                click(back)
                self.assertIsInstance(d.screen(), expected, screen_cls.__name__)
            # llave del Mundialito: volver no pierde el progreso
            app.switch(PickScreen(app))
            d.tap(pygame.K_SPACE)
            self.assertIsInstance(d.screen(), HubScreen)
            click(back)
            self.assertIsInstance(d.screen(), PlayMenuScreen)
            self.assertIsNotNone(app.tournament)
            # en el partido, el botón de la esquina pide la pausa
            app.switch(MatchScreen(app, ["messi", "pele"]))
            ms = d.screen()
            d.until(lambda: ms.state is not None, 5, "estado")
            click(back)
            d.until(lambda: ms.pause_state == "paused", 3, "pausa por botón")
        finally:
            app.shutdown()

    def test_crash_shows_error_screen_and_retry(self):
        from fdc.ui.screens import ErrorScreen
        app = driver.make_app(test_mode=True, seed=1)
        d = driver.Driver(app)
        try:
            d.until(lambda: isinstance(d.screen(), MenuScreen), 20, "menú")
            app.switch(MatchScreen(app, ["pele", "henry"]))
            ms = d.screen()
            d.until(lambda: ms.state is not None, 5, "estado")
            d.tap(pygame.K_F12)                          # fallo provocado en la SIM
            d.until(lambda: isinstance(d.screen(), ErrorScreen), 5, "pantalla de error")
            self.assertIn("error", app.link.error.lower())
            d.tap(pygame.K_RETURN)                       # Reintentar: proceso nuevo
            d.until(lambda: isinstance(d.screen(), MenuScreen), 20, "menú tras reintentar")
            self.assertIsNone(app.link.error)
            self.assertTrue(app.link.alive)
        finally:
            app.shutdown()


class ProfileTest(unittest.TestCase):
    def test_name_is_asked_once_at_start(self):
        from fdc import profile as prof
        from fdc.ui.profile_screen import ProfileScreen
        app = driver.make_app(test_mode=False, seed=1, profile_name=None)   # primera vez
        d = driver.Driver(app)
        try:
            d.until(lambda: isinstance(d.screen(), ProfileScreen), 20, "pantalla del nombre")
            self.assertFalse(d.screen().back_button.visible)        # la primera vez no hay a dónde volver
            d.tap(pygame.K_RETURN)                                   # vacío: no avanza
            self.assertIsInstance(d.screen(), ProfileScreen)
            d.post(pygame.TEXTINPUT, text="Ale")
            d.tap(pygame.K_RETURN)
            self.assertIsInstance(d.screen(), MenuScreen)
            saved = prof.load(app.profile_path)                      # queda guardado para la próxima vez
            self.assertEqual(saved.name, "Ale")
            pid = saved.player_id
            d.tap(pygame.K_n)                                        # cambiar el nombre desde el menú
            self.assertIsInstance(d.screen(), ProfileScreen)
            self.assertTrue(d.screen().back_button.visible)
            for _ in range(3):
                d.tap(pygame.K_BACKSPACE)
            d.post(pygame.TEXTINPUT, text="Alan")
            d.tap(pygame.K_RETURN)
            self.assertIsInstance(d.screen(), MenuScreen)
            renamed = prof.load(app.profile_path)
            self.assertEqual((renamed.name, renamed.player_id), ("Alan", pid))   # mismo jugador
        finally:
            app.running = False
            app.shutdown()


if __name__ == "__main__":
    unittest.main()
