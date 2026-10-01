"""Interfaz online real (sin ventana) contra un servidor real.

La persona maneja la aplicación de escritorio; el rival es un cliente de
prueba conectado al mismo servidor.
"""
import os
import unittest

try:
    import websockets  # noqa: F401
except ImportError:  # el juego local no lo necesita: sin websockets se saltean
    raise unittest.SkipTest("falta websockets (pip install -r requirements-online.txt)") from None

import driver  # configura SDL dummy antes de importar pygame
import pygame
from online_helpers import Client, ServerThread

from fdc.online import wire as W
from fdc.ui.online_screens import (CreateRoomScreen, OnlineMatchScreen, OnlineResultScreen,
                                   RoomScreen, RoomsScreen)
from fdc.ui.screens import BackButton, MenuScreen, MultiplayerMenuScreen

SHOTS = os.environ.get("FDC_CAPTURAS")


class OnlineUITest(unittest.TestCase):
    def test_full_online_flow(self):
        with ServerThread(duration=30.0, seed=3) as srv:
            app = driver.make_app(test_mode=False, seed=None, server_url=srv.url, profile_name="Ale")
            d = driver.Driver(app, SHOTS)
            rival = None
            try:
                d.until(lambda: isinstance(d.screen(), MenuScreen), 25, "menú")
                d.tap(pygame.K_RETURN)                       # Jugar
                d.tap(pygame.K_s)
                d.tap(pygame.K_RETURN)                       # Multijugador
                d.tap(pygame.K_s)
                d.tap(pygame.K_RETURN)                       # Online
                # entra directo con el nombre del perfil (no lo vuelve a pedir)
                d.until(lambda: isinstance(d.screen(), RoomsScreen), 10, "lista de salas")
                self.assertEqual(app.net.username, "Ale")
                self.assertTrue(app.net.display.startswith("Ale #"))

                # crear una sala propia y volver a la lista
                d.tap(pygame.K_c)
                self.assertIsInstance(d.screen(), CreateRoomScreen)
                d.tap(pygame.K_ESCAPE)
                self.assertIsInstance(d.screen(), RoomsScreen)

                rival = Client(srv.url, "Ale")             # mismo nombre que yo: lo distingue la etiqueta
                d.each_frame = rival.pump
                rival.send({"type": "create_room", "name": "Picadito", "password": "1234"})
                d.until(lambda: app.net.rooms, 5, "sala en la lista")
                d.shot("online_2_salas")
                d.tap(pygame.K_RETURN)                       # sala privada: pide la contraseña
                self.assertIsNotNone(d.screen().prompt)
                d.post(pygame.TEXTINPUT, text="1234")
                d.tap(pygame.K_RETURN)
                d.until(lambda: isinstance(d.screen(), RoomScreen), 5, "sala")

                rival.send({"type": "choose_character", "character": "pele"})
                rival.send({"type": "ready"})
                d.until(lambda: any(m["ready"] for m in app.net.room["members"]), 5, "rival listo")
                d.tap(pygame.K_d)                            # cambio de personaje
                d.frames(3)
                d.shot("online_3_sala")
                d.tap(pygame.K_SPACE)                        # ¡listo!
                d.until(lambda: isinstance(d.screen(), OnlineMatchScreen), 10, "partido")
                ms = d.screen()
                self.assertEqual(ms.names[ms.you], app.net.display)
                self.assertNotEqual(ms.names[0], ms.names[1])
                d.until(lambda: ms.state is not None and ms.state["phase"] == "playing", 15, "juego")

                # me muevo: la posición la decide la simulación del servidor
                me = ms.you
                x0 = ms.state["players"][me]["x"]
                key = pygame.K_RIGHT if me == 0 else pygame.K_LEFT
                d.down(key)
                d.seconds(0.5)
                d.up(key)
                d.seconds(0.2)
                self.assertGreater(abs(ms.state["players"][me]["x"] - x0), 40)

                # pausa pedida: se anuncia debajo del marcador y no corta la jugada
                d.tap(pygame.K_ESCAPE)
                d.until(lambda: ms.renderer.center_note == f"{app.net.display} pidió la pausa", 5,
                        "aviso de pausa")
                self.assertFalse(ms.state["paused"])
                d.shot("online_4_partido")

                rival.send({"type": "abandon"})              # el rival se va: gano por abandono
                d.until(lambda: isinstance(d.screen(), OnlineResultScreen), 10, "resultado")
                res = d.screen()
                self.assertEqual((res.over["reason"], res.winner), (W.END_FORFEIT, me))
                d.frames(5)
                d.shot("online_5_resultado")
                d.post(pygame.MOUSEBUTTONDOWN, pos=BackButton.RECT.center, button=1)
                d.until(lambda: isinstance(d.screen(), RoomsScreen), 5, "volver a la lista")
                # "Volver" desde la lista sale del online (no vuelve a entrar solo)
                d.post(pygame.MOUSEBUTTONDOWN, pos=BackButton.RECT.center, button=1)
                d.frames(30)
                self.assertIsInstance(d.screen(), MultiplayerMenuScreen)
                self.assertIsNone(app.net)
            finally:
                if rival is not None:
                    rival.close()
                app.running = False
                app.shutdown()


if __name__ == "__main__":
    unittest.main()
