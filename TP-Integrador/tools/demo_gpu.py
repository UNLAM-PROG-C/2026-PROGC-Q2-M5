"""Automatic match with and without the effects (no window).

Usage (PowerShell, from the repository):
    py tools\\demo_gpu.py             # 600 frames with and without effects
    py tools\\demo_gpu.py 300         # 300 frames
    py tools\\demo_gpu.py 300 --gpu-quality alta

It prints the milliseconds of each stage, the total and the FPS of the two
runs, so the cost of the chain is visible. Needs the toolchain next to the
repository for the GPU (see INSTALACION.md); without it, it measures the
numpy fallback.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  pylint: disable=wrong-import-position

from fdc.gpu import backend  # noqa: E402
from fdc.gpu import demo      # noqa: E402
from fdc.gpu import env       # noqa: E402


def main(argv):
    """Runs the demo three times and prints the summaries."""
    frames = int(argv[0]) if argv else demo.DEFAULT_FRAMES
    extra = argv[1:]
    env.setup()
    pygame.init()
    print("GPU:", backend.device_name())
    con = demo.run(frames, extra)
    cpu = demo.run(frames, extra + ["--gpu-cpu"])
    sin = demo.run(frames, extra + ["--no-gpu"])
    _show("con efectos (GPU)", con)
    _show("con efectos (numpy)", cpu)
    _show("sin efectos", sin)
    return 0


def _show(title, data):
    print(f"\n{title} ({data['surface']}, {data['frames']} frames)")
    print(f"  modo {data['mode']} | calidad {data['quality']} | {data['gpu']}")
    for key in ("glow", "composite", "particles", "lights", "heat", "trail",
                "histogram", "shock", "fire", "confusion", "confusion_rot",
                "ice", "blackout", "night", "exposure",
                "crt", "var"):
        if data.get(key):
            print(f"  {key:<13} {data[key]:7.3f} ms")
    print(f"  cadena        {data.get('frame', 0):7.3f} ms   "
          f"{data.get('fps', 0):6.1f} fps")
    print(f"  loop          {data.get('ms_frame', 0):7.3f} ms/frame   "
          f"{data.get('fps_loop', 0):6.1f} fps")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
