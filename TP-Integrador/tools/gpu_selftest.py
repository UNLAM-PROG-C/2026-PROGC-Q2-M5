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

W, H = 320, 180         # size of the test frame
BYTE = 256              # levels of gray
BYTE_MAX = 255.0        # top of the 8 bit range
CHANNELS = 3            # RGB
TOLERANCE = 3           # gray levels: rounding of an average
WARP_TOLERANCE = 8      # mean difference allowed on the warps
SEED = 7                # fixed random image (repeatable)
PATCH = (slice(40, 90), slice(100, 180))   # bright rectangle (for the glow)
PATCH_COLOR = 240       # gray level of that rectangle
BLUR_RADIUS = 3         # px of the blur test
SOFT_RADIUS = 6         # px: the warps are tested on a soft image
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
TRAIL_ALPHA = 0.4       # trail test: weight of the previous frame
HEAT_PHASE = 1.0        # rad: time of both warps
HEAT_AMP = 4.0          # px: depth of both warps
HEAT_PERIOD = 24.0      # px: wavelength of the heat waves
RIPPLE_PERIOD = 40.0    # px: wavelength of the circular waves
GRID_COLS, GRID_ROWS = 64, 36      # cells of the heat map
HEAT_POINTS = np.array([[10.0, 5.0], [30.0, 20.0], [63.0, 35.0]],
                       np.float32)                        # cells to fill
HEAT_AMOUNT = 2.0       # heat added to each of those cells
HEAT_MAX = 3.0          # top of the colour ramp
POS = np.array([[40.0, 50.0], [120.0, 90.0], [300.0, 170.0]],
               np.float32)                                  # particles: x, y
COL = np.array([[1.0, 0.2, 0.1, 3.0], [0.2, 1.0, 0.3, 2.0],
                [0.9, 0.9, 1.0, 4.0]], np.float32)       # r, g, b and size
LIGHTS = np.array([[50.0, 60.0, 90.0, 1.5, 1.0, 0.9, 0.6],
                   [250.0, 120.0, 70.0, 0.8, 0.2, 0.4, 1.0]],
                  np.float32)                # x, y, radio, power, r, g, b
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


def check_warps(gpu, cpu, img):
  """Heat waves and ripple (they move pixels: soft image, mean error)."""
  soft = cpu.blur(img, SOFT_RADIUS)
  ok = report("heat", gpu.heat(soft, HEAT_PHASE, HEAT_AMP, HEAT_PERIOD),
              cpu.heat(soft, HEAT_PHASE, HEAT_AMP, HEAT_PERIOD),
              WARP_TOLERANCE, True)
  ok &= report("ripple",
               gpu.ripple(soft, HEAT_PHASE, HEAT_AMP, RIPPLE_PERIOD),
               cpu.ripple(soft, HEAT_PHASE, HEAT_AMP, RIPPLE_PERIOD),
               WARP_TOLERANCE, True)
  return ok


def check_glow(gpu, cpu, img):
  """Bright pass, blur of the field and final composition."""
  field = gpu.glow(img, GLOW_THRESHOLD, GLOW_RADIUS, GLOW_PASSES)
  ref = cpu.glow(img, GLOW_THRESHOLD, GLOW_RADIUS, GLOW_PASSES)
  ok = report("glow", field, ref, GLOW_TOL)
  ok &= report("composite", gpu.composite(img, field, *PARAMS),
               cpu.composite(img, field, *PARAMS), GLOW_TOL)
  return ok


def check_images(gpu, cpu, img):
  """Blur, warps, mix, stretch and the glow chain."""
  ok = report("blur", gpu.blur(img, BLUR_RADIUS),
              cpu.blur(img, BLUR_RADIUS))
  ok &= check_warps(gpu, cpu, img)
  ok &= report("mix", gpu.mix(img, img[::-1], MIX_ALPHA),
               cpu.mix(img, img[::-1], MIX_ALPHA))
  ok &= report("stretch", gpu.stretch(img, STRETCH_LOW, STRETCH_HIGH),
               cpu.stretch(img, STRETCH_LOW, STRETCH_HIGH))
  ok &= check_glow(gpu, cpu, img)
  return ok


def check_lights(gpu, cpu, img):
  """Particles, spotlights and the trail."""
  ok = report("particles", gpu.particles(img, POS, COL, GAIN),
              cpu.particles(img, POS, COL, GAIN))
  ok &= report("lights", gpu.lights(img, LIGHTS, GAIN),
               cpu.lights(img, LIGHTS, GAIN))
  ok &= report("trail", gpu.trail(img, img[::-1], TRAIL_ALPHA)[0],
               cpu.trail(img, img[::-1], TRAIL_ALPHA)[0])
  return ok


def empty_heat():
  """Grid of the heat map, all zeros."""
  return np.zeros((GRID_ROWS, GRID_COLS), np.float32)


def filled_heat():
  """Grid of the heat map with one unit in every cell."""
  return empty_heat() + 1.0


def check_analysis(gpu, cpu, img):
  """Histogram, minimap and the heat map."""
  ok = report("histogram", gpu.histogram(img), cpu.histogram(img), 0)
  ok &= report("minimap",
               gpu.minimap(img, GRID_COLS, GRID_ROWS) * BYTE_MAX,
               cpu.minimap(img, GRID_COLS, GRID_ROWS) * BYTE_MAX, GLOW_TOL)
  ok &= report("heat_splat", gpu.heat_splat(HEAT_POINTS, empty_heat(),
                                            HEAT_AMOUNT),
               cpu.heat_splat(HEAT_POINTS, empty_heat(), HEAT_AMOUNT), 0)
  ok &= report("heat_colors", gpu.heat_colors(filled_heat(), HEAT_MAX),
               cpu.heat_colors(filled_heat(), HEAT_MAX))
  return ok


def measure(gpu, img):
  """Milliseconds of the two heaviest operations."""
  _, blur_ms = timed(gpu.blur, img, BLUR_RADIUS)
  field = gpu.glow(img, GLOW_THRESHOLD, GLOW_RADIUS, GLOW_PASSES)
  _, comp_ms = timed(gpu.composite, img, field, *PARAMS)
  print(f"  gpu blur {BLUR_RADIUS}px: {blur_ms:.3f} ms"
        f"   composite: {comp_ms:.3f} ms")


def run(gpu, cpu, img):
  """Every comparison; True if all of them are inside tolerance."""
  ok = check_images(gpu, cpu, img)
  ok &= check_lights(gpu, cpu, img)
  ok &= check_analysis(gpu, cpu, img)
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
