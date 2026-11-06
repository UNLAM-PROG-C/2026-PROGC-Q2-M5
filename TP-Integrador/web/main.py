"""Entry of the web version (pygbag): the whole game in the browser.

It is not run directly: tools/build_web.py copies this file as main.py
together with the fdc package and the sprites, and pygbag compiles it for
the browser. There is no multiprocessing there: the tournament and the local
multiplayer simulate inside the page (fdc/sim/inline.py) and the online mode
uses the room process on the server.
"""
import asyncio
import logging
import types

# pygbag decides which packages to load by looking at the imports of THIS
# file: pygame has to appear here even if only the fdc package uses it.
import pygame  # pylint: disable=unused-import

from fdc.ui import app as game

LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


async def main():
    """Creates the game with the browser options and runs its loop."""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    options = types.SimpleNamespace(
        web=True, test_mode=False, seed=None, no_audio=False,
        fullscreen=False, debug_panel=False, duration=None, server_url=None,
        quality_mode="auto")     # the browser adapts the cost of the chain
    await game.App(options).run_async()


asyncio.run(main())
