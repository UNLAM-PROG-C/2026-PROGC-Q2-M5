"""Entrada de la versión web (pygbag): el juego completo en el navegador.

No se ejecuta directamente: tools/construir_web.py copia este archivo como
main.py junto con el paquete fdc y los sprites, y pygbag lo compila para el
navegador. Ahí no hay multiprocessing: el Mundialito y el multijugador local
simulan dentro de la página (fdc/sim/inline.py) y el online usa el proceso de
la sala en el servidor.
"""
import asyncio
import logging
import types

# pygbag decide qué paquetes cargar mirando los import de ESTE archivo: pygame
# tiene que aparecer acá aunque lo use el paquete fdc
import pygame  # noqa: F401

from fdc.ui.app import App


async def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    options = types.SimpleNamespace(web=True, test_mode=False, seed=None, no_audio=False, fullscreen=False,
                                    debug_panel=False, duration=None, server_url=None)
    app = App(options)
    await app.run_async()


asyncio.run(main())
