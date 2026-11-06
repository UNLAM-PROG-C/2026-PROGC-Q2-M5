"""Fresh interpreter: what the effects do with FDC_GPU and FDC_EFECTOS.

Prints one JSON line with the backend the chain picked, the quality mode,
the effects that are active and whether PyCUDA was imported. The tests set
the environment variables; this file only reports what the game does.

FDC_TEST_NO_PYCUDA=1 hides PyCUDA from the imports, like a Mac or a
notebook without NVIDIA (there the module does not even exist).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
if os.environ.get("FDC_TEST_NO_PYCUDA") == "1":
    sys.modules["pycuda"] = None     # `import pycuda` now raises ImportError

# pylint: disable=wrong-import-position
import pygame          # noqa: E402
import main            # noqa: E402
from fdc import config  # noqa: E402
from fdc.gpu import postfx  # noqa: E402

WINDOW = (64, 48)       # small surface: the chain is not measured here


def chain(quality):
    """PostFx the App would build for `--calidad quality`, already started."""
    options = main.parse_args(["--calidad", quality])
    main.apply_gpu_options(options)
    effects = postfx.PostFx(options, WINDOW)
    effects.start()
    return effects


def pycuda_loaded():
    """True only if PyCUDA was really imported (not just hidden)."""
    return sys.modules.get("pycuda") is not None


def report(effects):
    """The part of the chain the tests look at."""
    return {
        "effects_enabled": config.Effects.ENABLED,
        "cuda_allowed": config.Gpu.ENABLED,
        "wanted": bool(effects.enabled),
        "backend": None if effects.ops is None else
        type(effects.ops).__name__,
        "mode": effects.mode,
        "device": effects.device,
        "quality_mode": effects.quality_mode_name(),
        "stage": effects.stage_level() if effects.enabled else None,
        "pycuda_loaded": pycuda_loaded(),
        "error": effects.error,
    }


def main_probe():
    """Builds the chain for --calidad full and prints the report."""
    pygame.init()
    pygame.display.set_mode(WINDOW)
    quality = os.environ.get("FDC_TEST_QUALITY", "full")
    print(json.dumps(report(chain(quality))))


if __name__ == "__main__":
    main_probe()
