"""Preview of the crowd of the stands (F11), with and without CUDA.

Usage (PowerShell, from the repository):
    py tools\\tribuna_preview.py                  # GPU and numpy, PNGs
    py tools\\tribuna_preview.py --cpu            # only the numpy version

It paints the band of the stands at 1280x352 with the same parameters the
game uses, saves `capturas\\mejoras\\tribuna-*.png` and prints the cost of
each backend and the difference between them (the test uses the same idea).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.dirname(ROOT)      # the worktree lives inside the project
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np                                # noqa: E402
import pygame                                     # noqa: E402

from fdc import config                            # noqa: E402
from fdc.gpu import backend                       # noqa: E402
from fdc.gpu import cpu_ref                       # noqa: E402
from fdc.gpu import crowd                         # noqa: E402
from fdc.gpu import env as gpu_env                # noqa: E402

FOLDER = os.path.join(PROJECT, "capturas", "mejoras")
WIDTH = config.LOGICAL_WIDTH      # px: width of the band of the stands
HEIGHT = config.Gpu.CROWD_BOTTOM - config.Gpu.CROWD_TOP   # px: its height
BACKGROUND = (24, 52, 34)     # grass colour: the crowd must cover it
TIME = 1.7                    # s of the animation of the shot
SIDE = 0                      # the left stand is celebrating
BOOST = 1.0                   # how hard it is celebrating (0-1)
FRAMES = 3                    # runs timed to warm up the buffers
TIMED = 5                     # runs timed for the report (the mean wins)
CPU = "--cpu"                 # argument: only the numpy version
OUT_FLAG = "--out"            # argument: folder of the PNGs
CUDA = "gpu"                  # name of the CUDA version
NUMPY = "cpu"                 # name of the fallback
WINDOW = (64, 64)             # dummy window (pygame needs one for surfaces)
# Crop of the zoom of the front rows (px of the band).
ZOOM_W, ZOOM_H = 320, 176     # size of the crop
ZOOM_X, ZOOM_Y = 12, 7        # the crop starts at (w / ZOOM_X, h / ZOOM_Y)
ZOOM_SCALE = 2                # the crop is doubled to look at the people
CHANNELS = 3                  # rgb
MS = 1000.0                   # seconds to milliseconds
FAR = 16                      # channel difference that counts as "different"
ALL = 100.0                   # percentage


def main(argv):
    """Paints the band with both backends and saves the PNGs."""
    gpu_env.setup()
    pygame.init()
    pygame.display.set_mode(WINDOW)
    folder = _folder(argv)
    os.makedirs(folder, exist_ok=True)
    image = _band()
    cfg, pal = crowd.params()
    names = [NUMPY] if CPU in argv else [CUDA, NUMPY]
    results = {name: _run(name, image, cfg, pal, folder) for name in names}
    _report(results)
    _compare(results)
    return 0


def _folder(argv):
    """Folder of the PNGs: `--out DIR` or the default one."""
    if OUT_FLAG in argv:
        index = argv.index(OUT_FLAG)
        if index + 1 < len(argv):
            return argv[index + 1]
    return FOLDER


def _band():
    """Empty band of the stands (h, w, 3)."""
    image = np.empty((HEIGHT, WIDTH, CHANNELS), np.uint8)
    image[...] = BACKGROUND
    return image


def _ops(name):
    """Backend by name (numpy if CUDA is not there)."""
    if name == CUDA:
        try:
            return backend.Gpu(), CUDA
        except Exception:                    # pylint: disable=broad-except
            print("sin CUDA: se usa numpy")
    return cpu_ref.Cpu(), NUMPY


def _run(name, image, cfg, pal, folder):
    """Paints one band, times it and saves it: (seconds, image)."""
    ops, real = _ops(name)
    for _ in range(FRAMES):
        ops.tribuna(image, TIME, SIDE, BOOST, cfg, pal)
    start = time.perf_counter()
    out = image
    for _ in range(TIMED):
        out = ops.tribuna(image, TIME, SIDE, BOOST, cfg, pal)
    elapsed = (time.perf_counter() - start) / TIMED
    _save(out, f"tribuna-{real}.png", folder)
    _save(_zoom(out), f"tribuna-{real}-zoom.png", folder)
    return elapsed, out


def _zoom(image):
    """A crop of the front rows, doubled, to look at the people."""
    top = image.shape[0] // ZOOM_Y
    left = image.shape[1] // ZOOM_X
    crop = image[top:top + ZOOM_H, left:left + ZOOM_W]
    small = pygame.surfarray.make_surface(np.transpose(crop, (1, 0, 2)))
    big = pygame.transform.scale(small, (ZOOM_W * ZOOM_SCALE,
                                         ZOOM_H * ZOOM_SCALE))
    return np.transpose(pygame.surfarray.array3d(big), (1, 0, 2))


def _save(image, name, folder):
    """Writes an RGB array as a PNG."""
    surface = pygame.surfarray.make_surface(np.transpose(image, (1, 0, 2)))
    pygame.image.save(surface, os.path.join(folder, name))


def _report(results):
    """Milliseconds of each backend."""
    for name, (elapsed, _) in results.items():
        print(f"{name}: {elapsed * MS:.2f} ms por franja {WIDTH}x{HEIGHT}")


def _compare(results):
    """Mean difference and pixels far apart between GPU and numpy."""
    if CUDA not in results or NUMPY not in results:
        return
    gpu_image = results[CUDA][1].astype(np.int32)
    cpu_image = results[NUMPY][1].astype(np.int32)
    diff = np.abs(gpu_image - cpu_image)
    far = (diff.max(axis=2) > FAR).mean() * ALL
    print(f"diferencia media {diff.mean():.3f} · píxeles >{FAR}: {far:.3f} %")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
