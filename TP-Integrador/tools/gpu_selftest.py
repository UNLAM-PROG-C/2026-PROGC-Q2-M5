"""Compares every GPU kernel with its numpy version (fdc.gpu.cpu_ref).

Usage (PowerShell, from the repository):
    py tools\\gpu_selftest.py

It needs the toolchain folder next to the repository (see INSTALACION.md).
Prints the difference of each operation and the milliseconds.
"""
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fdc.gpu import backend  # noqa: E402  pylint: disable=wrong-import-position
from fdc.gpu import cpu_ref  # noqa: E402  pylint: disable=wrong-import-position
from fdc.gpu import env      # noqa: E402  pylint: disable=wrong-import-position
from tools import golden_kernels  # noqa: E402

W, H = 320, 180         # size of the test frame
BYTE = 256              # levels of gray
CHANNELS = 3            # RGB
TOLERANCE = 3           # gray levels: rounding of an average
WARP_TOLERANCE = 8      # mean difference allowed on the warps
SEED = 7                # fixed random image (repeatable)
PATCH = (slice(40, 90), slice(100, 180))   # bright rectangle (for the glow)
PATCH_COLOR = 240       # gray level of that rectangle
GLOW_THRESHOLD = 0.55   # from this luma (0-1) a pixel glows
GLOW_RADIUS = 3         # px of the halo blur
GLOW_PASSES = 2         # box blurs of the halo
GLOW_TOL = 6            # gray levels allowed on the halo and composite
EXPOSURE = 1.15         # composite: brightness
GAMMA = 1.0             # composite: gamma
VIGNETTE = 0.3          # composite: darkening of the corners
GLOW_STRENGTH = 0.6     # composite: weight of the halo
PARAMS = (EXPOSURE, GAMMA, VIGNETTE, GLOW_STRENGTH)   # composite arguments
MIX_ALPHA = 0.35        # mix test: weight of the second image
STRETCH_LOW = 20.0      # stretch test: new black level
STRETCH_HIGH = 200.0    # stretch test: new white level
HEAT_PHASE = 1.0        # rad: time of the heat waves
HEAT_AMP = 4.0          # px: depth of the heat waves
HEAT_PERIOD = 24.0      # px: wavelength of the heat waves
POS = np.array([[40.0, 50.0], [120.0, 90.0], [300.0, 170.0]],
               np.float32)                                  # particles: x, y
COL = np.array([[1.0, 0.2, 0.1, 3.0], [0.2, 1.0, 0.3, 2.0],
                [0.9, 0.9, 1.0, 4.0]], np.float32)       # r, g, b and size
GAIN = 1.0              # light weight of the tests
MS_PER_S = 1000.0       # seconds to milliseconds


def timed(fn, *args):
  """(result, milliseconds) of one call."""
  start = time.perf_counter()
  out = fn(*args)
  return out, (time.perf_counter() - start) * MS_PER_S


def diff(a, b):
  """Biggest absolute difference between two arrays."""
  return float(np.abs(a.astype(np.float32) - b.astype(np.float32)).max())


def report(name, ours, ref, limit=TOLERANCE, mean=False):
  """Prints the difference of one operation; True if it is inside."""
  delta = diff(ours, ref)
  if mean:
    delta = float(np.abs(ours.astype(np.float32)
                         - ref.astype(np.float32)).mean())
  print(f"  {'OK ' if delta <= limit else 'BAD'} {name:<12} {delta:7.2f}")
  return delta <= limit


def check_heat(gpu, cpu, img):
  """Heat waves move pixels: use a soft image and compare mean error."""
  soft = golden_kernels.soft_frame(img)
  return report("heat", gpu.heat(soft, HEAT_PHASE, HEAT_AMP, HEAT_PERIOD),
              cpu.heat(soft, HEAT_PHASE, HEAT_AMP, HEAT_PERIOD),
              WARP_TOLERANCE, True)


def check_glow(gpu, cpu, img):
  """Bright pass, blur of the field and final composition."""
  field = gpu.glow(img, GLOW_THRESHOLD, GLOW_RADIUS, GLOW_PASSES)
  ref = cpu.glow(img, GLOW_THRESHOLD, GLOW_RADIUS, GLOW_PASSES)
  ok = report("glow", field, ref, GLOW_TOL)
  ok &= report("composite", gpu.composite(img, field, *PARAMS),
               cpu.composite(img, field, *PARAMS), GLOW_TOL)
  return ok


def check_images(gpu, cpu, img):
  """Heat waves, mix, stretch and the glow chain."""
  ok = check_heat(gpu, cpu, img)
  ok &= report("mix", gpu.mix(img, img[::-1], MIX_ALPHA),
               cpu.mix(img, img[::-1], MIX_ALPHA))
  ok &= report("stretch", gpu.stretch(img, STRETCH_LOW, STRETCH_HIGH),
               cpu.stretch(img, STRETCH_LOW, STRETCH_HIGH))
  ok &= check_glow(gpu, cpu, img)
  return ok


def check_particles(gpu, cpu, img):
  """Compare the additive sparks."""
  return report("particles", gpu.particles(img, POS, COL, GAIN),
              cpu.particles(img, POS, COL, GAIN))


def check_histogram(gpu, cpu, img):
  """Compare the contrast histogram exactly."""
  return report("histogram", gpu.histogram(img), cpu.histogram(img), 0)


def measure(gpu, img):
  """Milliseconds of the two heaviest operations."""
  field, glow_ms = timed(gpu.glow, img, GLOW_THRESHOLD, GLOW_RADIUS,
                          GLOW_PASSES)
  _, comp_ms = timed(gpu.composite, img, field, *PARAMS)
  print(f"  gpu glow: {glow_ms:.3f} ms"
        f"   composite: {comp_ms:.3f} ms")


def run(gpu, cpu, img):
  """Every comparison; True if all of them are inside tolerance."""
  ok = check_images(gpu, cpu, img)
  ok &= check_particles(gpu, cpu, img)
  ok &= check_histogram(gpu, cpu, img)
  return ok


def test_image():
  """Random frame with a bright rectangle (for the glow)."""
  rng = np.random.default_rng(SEED)
  img = rng.integers(0, BYTE, (H, W, CHANNELS), dtype=np.uint8)
  img[PATCH] = PATCH_COLOR
  return img


def main():
  """0 if the GPU matches the numpy reference."""
  if not env.setup():
    print("No toolchain: set FDC_GPU_TOOLCHAIN (see INSTALACION.md)")
    return 1
  if not backend.available():
    print("PyCUDA/CUDA not available")
    return 1
  gpu, cpu = backend.Gpu(), cpu_ref.Cpu()
  print(f"GPU: {backend.device_name()}  arch {gpu.arch}  {W}x{H}")
  ok = run(gpu, cpu, test_image())
  measure(gpu, test_image())
  print("SELFTEST", "OK" if ok else "FAILED")
  return 0 if ok else 1


if __name__ == "__main__":
  sys.exit(main())
