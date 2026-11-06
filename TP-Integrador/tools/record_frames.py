"""Twelve frames of the demo for the slides (PNG, no window needed).

Usage (PowerShell, from the repository):
    py tools\\record_frames.py                 # frames\\frame_NN.png
    py tools\\record_frames.py --demo-backends cpu

It runs the demo with a fixed 1/60 s clock (so the frames are repeatable)
and saves one image per segment, with the label and the overlay already
drawn. Images are 1280x720; the folder is created if it does not exist.
"""
import os
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  pylint: disable=wrong-import-position

import main as main_module                      # noqa: E402
from fdc.gpu import demo                        # noqa: E402
from fdc.gpu import env                         # noqa: E402
from fdc.ui import app as ui_app                # noqa: E402

FOLDER = os.path.join(ROOT, "frames")
PREFIX = "frame"
SECONDS = 1.2            # s of each segment (enough for the label)
LIMIT = 4000             # frames of the whole run (safety net)
FILTER = "_"


def main(argv):
    """Runs the demo and saves one frame per segment."""
    game = _start(argv)
    try:
        saved = _run(game)
    finally:
        game.shutdown()
    _report(saved)
    return 0 if saved else 1


def _start(argv):
    """Environment, options and App for the capture run."""
    env.setup()
    demo.headless()
    pygame.init()
    os.makedirs(FOLDER, exist_ok=True)
    options = main_module.parse_args(
        ["--demo", "--no-audio", "--demo-frame-clock",
         "--demo-seconds", str(SECONDS), "--overlay", "full"] + list(argv))
    return ui_app.App(options)


def _report(saved):
    """Prints how many frames were written and where."""
    print(f"{len(saved)} frames en {FOLDER}")
    for path in saved:
        print("  " + os.path.basename(path))


def _run(game):
    """Plays the demo and saves when the segment changes."""
    saved = []
    last = None
    for _ in range(LIMIT):
        game.frame()
        screen = game.current
        if not isinstance(screen, demo.DemoScreen):
            continue
        if screen.director.index != last:
            last = screen.director.index
            saved.append(_save(game.screen, screen))
        if screen.finished and len(saved) >= demo.SEGMENT_COUNT:
            break
    return saved


def _save(surface, screen):
    """One PNG with the number and the name of the segment."""
    name = _slug(screen.director.name())
    path = os.path.join(FOLDER, f"{PREFIX}_{screen.director.index + 1:02d}_"
                                f"{name}.png")
    pygame.image.save(surface, path)
    return path


def _slug(text):
    """File name without spaces or accents (the pack goes to Colab)."""
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(char for char in plain
                    if not unicodedata.combining(char))
    return plain.replace(" ", FILTER).replace("/", FILTER)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
