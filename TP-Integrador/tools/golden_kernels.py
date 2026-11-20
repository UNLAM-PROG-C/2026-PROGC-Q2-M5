"""Golden outputs of every CUDA kernel, to check a refactor of kernels.cu.

It runs each operation of `fdc.gpu.backend.Gpu` on a fixed input and saves
the arrays, so a later build of the kernels can be compared bit by bit.

Usage (PowerShell, from the repository; save and check need the GPU):
    py tools/golden_kernels.py save OUT.npz [--fatbin FILE]
    py tools/golden_kernels.py check GOLDEN.npz [--fatbin FILE]
    py tools/golden_kernels.py compare A.npz B.npz

`--fatbin` loads another compiled module (for example the one of 1.0.2,
whose crowd kernel was still called k_tribuna). `compare` only needs numpy.
"""
import argparse
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)
from fdc.gpu import backend  # noqa: E402  pylint: disable=wrong-import-position

W, H = 320, 180          # size of the test frame
CHANNELS = 3             # RGB
BYTE = 256               # levels of one channel
SEED = 7                 # fixed random image (repeatable)
PATCH = (slice(40, 90), slice(100, 180))   # bright rectangle (for the glow)
PATCH_COLOR = 240        # gray level of that rectangle
SOFT_RADIUS = 6          # px: the warps run on a soft image
OLD_NAMES = {"k_crowd": "k_tribuna"}   # kernel renamed after 1.0.2
TOLERANCE = 0            # check: biggest difference allowed (exact)
FAILED = 1               # exit code when a case is over the tolerance
BLUR_ARGS = (3,)                              # radius
GLOW_ARGS = (0.55, 3, 2)                      # threshold, radius, passes
CMP_PARAMS = (1.15, 1.0, 0.3, 0.6)            # exposure, gamma, vig., glow
GAIN = 1.0                                    # weight of the light kernels
POS = ((40.0, 50.0), (120.0, 90.0), (300.0, 170.0))   # particles: x, y
COL = ((1.0, 0.2, 0.1, 3.0), (0.2, 1.0, 0.3, 2.0),
       (0.9, 0.9, 1.0, 4.0))                  # r, g, b and size
PAPER = ((1.0, 1.0, 1.0, 2.0, 2.0), (0.2, 0.9, 0.4, 3.0, 1.0),
         (1.0, 0.3, 0.2, 3.0, 1.0))           # r, g, b, half w, half h
LAMPS = ((50.0, 60.0, 90.0, 1.5, 1.0, 0.9, 0.6),
         (250.0, 120.0, 70.0, 0.8, 0.2, 0.4, 1.0))   # x, y, r, power, rgb
HEAT_WARP = (1.0, 4.0, 24.0)                  # phase, amp, period
RIPPLE_WARP = (1.0, 4.0, 40.0)                # phase, amp, period
MIX_ALPHA = 0.35                              # weight of the second image
TRAIL_ALPHA = 0.4                             # weight of the previous frame
STRETCH = (20.0, 200.0)                       # new black and white levels
VIGNETTE = 0.3                                # darkening of the corners
GRID = (64, 36)                               # cols, rows of the maps
HEAT_POINTS = ((10.0, 5.0), (30.0, 20.0), (63.0, 35.0))   # cells to fill
HEAT_AMOUNT = 2.0                             # heat added to each cell
HEAT_MAX = 3.0                                # top of the colour ramp
BC_ARGS = (0.1, 1.4)                          # brightness, contrast
IMAGE_GAIN = 1.3                              # gain of k_gain
TINT = (1.0, 0.8, 0.5)                        # rgb of k_tint
ANGLE = 0.3                                   # rad of k_rotate
EDGE_STRENGTH = 0.8                           # k_edge_glow
ICE_ARGS = (0.8, (0.55, 0.85, 1.0), 0.45)     # strength, tint, amount
SPOTS = ((20.0, 20.0, 40.0, 0.9), (60.0, 40.0, 60.0, 0.6),
         (64.0, 42.0, 60.0, 0.9))             # x, y, radius, power
SPOT_ARGS = (0.15, (1.0, 0.86, 0.66))         # ambient, tint
SPOT_CAP = 0.85                               # top of the night light
FIRE_ARGS = (40.0, 30.0, 30.0, 0.5, 4.0)      # cx, cy, rad, t, amp
RING_ARGS = (40.0, 30.0, 12.0, 8.0, 5.0)      # cx, cy, radius, width, amp
STAND_ROW = 20                                # ring: rows kept untouched
DECAY = 0.55                                  # k_trail_blend
CRT_ARGS = (5, 0.9, 0.35, 0.45, 0.10, 3, (0.80, 1.0, 0.85))   # frame, ...
CROWD_SIZE = (96, 320)                        # rows, cols of the band
CROWD_BG = (12, 40, 24)                       # grass behind the band
CROWD_ARGS = (1.7, 0, 1.0)                    # t, side, boost
CELL = (5.0, 5.0)                             # px of one heat map cell
FIELD_POINTS = ((12.0, 9.0), (12.5, 9.5), (200.0, 100.0),
                (319.0, 179.0))               # x, y of the players (px)
HEAT_CHANNEL = 0                              # team drawn by k_heat_render
HEAT_RENDER = (0.55, 4.0)                     # alpha, gain


def frame():
  """Fixed RGB test image with a bright rectangle."""
  rng = np.random.default_rng(SEED)
  img = rng.integers(0, BYTE, (H, W, CHANNELS), dtype=np.uint8)
  img[PATCH] = PATCH_COLOR
  return img


class GoldenGpu(backend.Gpu):
  """Gpu that can load another fatbin and knows the names of 1.0.2."""

  def __init__(self, fatbin=None):
    self.fatbin = fatbin
    super().__init__()

  def _load_module(self, arch, compiler):
    if self.fatbin:
      return self.driver.module_from_file(self.fatbin)
    return super()._load_module(arch, compiler)

  def _fn(self, name):
    try:
      return super()._fn(name)
    except self.driver.LogicError:
      return super()._fn(OLD_NAMES[name])


def image_cases(ops, img, soft):
  """Blur, glow, lights and the screen effects."""
  glow = ops.glow(img, *GLOW_ARGS)
  return {
      "blur": ops.blur(img, *BLUR_ARGS), "glow": glow,
      "glow_composite": ops.glow_composite(img, *GLOW_ARGS, CMP_PARAMS),
      "composite": ops.composite(img, glow, *CMP_PARAMS),
      "particles": ops.particles(img, _f32(POS), _f32(COL), GAIN),
      "confetti": ops.confetti(img, _f32(POS), _f32(PAPER), GAIN),
      "lights": ops.lights(img, _f32(LAMPS), GAIN),
      "heat": ops.heat(soft, *HEAT_WARP),
      "ripple": ops.ripple(soft, *RIPPLE_WARP),
      "mix": ops.mix(img, img[::-1], MIX_ALPHA),
  }


def frame_cases(ops, img):
  """Trail, histogram, stretch and the maps."""
  heat = np.zeros(GRID[::-1], np.float32)
  splat = ops.heat_splat(_f32(HEAT_POINTS), heat, HEAT_AMOUNT)
  trail, before = ops.trail(img, img[::-1], TRAIL_ALPHA)
  return {
      "trail": trail, "trail_prev": before, "histogram": ops.histogram(img),
      "stretch": ops.stretch(img, *STRETCH),
      "stretch_vignette": ops.stretch(img, *STRETCH, VIGNETTE),
      "minimap": ops.minimap(img, *GRID),
      "heat_splat": heat if splat is None else splat,
      "heat_colors": ops.heat_colors(_ramp(), HEAT_MAX),
  }


def pixel_cases(ops, img):
  """The one pixel per thread kernels (k_gray .. k_rotate, Sobel)."""
  edges = ops.sobel(ops.to_gray(img))
  norm = ops.sobel_normalize(edges)
  return {
      "gray": ops.gray(img), "invert": ops.invert(img),
      "brightness_contrast": ops.brightness_contrast(img, *BC_ARGS),
      "gain": ops.gain(img, IMAGE_GAIN), "tint": ops.tint(img, TINT),
      "rotate": ops.rotate(img, ANGLE), "to_gray": ops.to_gray(img),
      "sobel": edges, "sobel_normalize": norm,
      "edge_glow": ops.edge_glow(img, norm, EDGE_STRENGTH),
  }


def power_cases(ops, img, soft):
  """Powers, trail, stats and the old television."""
  return {
      "ice": ops.ice(soft, *ICE_ARGS),
      "spotlights": ops.spotlights(img, SPOTS, *SPOT_ARGS),
      "spotlights_cap": ops.spotlights(img, SPOTS, *SPOT_ARGS, SPOT_CAP),
      "heat_distort": ops.heat_distort(soft, *FIRE_ARGS),
      "ripple_ring": ops.ripple_ring(soft, *RING_ARGS, STAND_ROW),
      "trail_blend": ops.trail_blend(img, img[::-1].copy(), DECAY),
      "luma_stats": np.asarray(ops.luma_stats(img), np.float64),
      "crt": ops.crt(img, *CRT_ARGS),
  }


def match_cases(ops, img):
  """Crowd of the stands and the heat map of the match (F6)."""
  from fdc.gpu import crowd  # pylint: disable=import-outside-toplevel
  band = np.empty((*CROWD_SIZE, CHANNELS), np.uint8)
  band[...] = CROWD_BG
  ops.heat_reset(*GRID)
  ops.heat_accumulate(HEAT_CHANNEL, FIELD_POINTS, *GRID, *CELL)
  grids, maxes = ops.heat_download(*GRID)
  render = ops.heat_render(img, grids, maxes, *GRID, HEAT_CHANNEL,
                           *HEAT_RENDER)
  return {
      "crowd": ops.crowd(band, *CROWD_ARGS, *crowd.params()),
      "heat_grids": grids, "heat_max": maxes, "heat_render": render,
  }


def run_all(fatbin=None):
  """{case: array} of every operation on the fixed input."""
  from fdc.gpu import cpu_ref  # pylint: disable=import-outside-toplevel
  ops = GoldenGpu(fatbin)
  img = frame()
  soft = cpu_ref.Cpu().blur(img, SOFT_RADIUS)
  out = {"input": img, "input_soft": soft}
  out.update(image_cases(ops, img, soft))
  out.update(frame_cases(ops, img))
  out.update(pixel_cases(ops, img))
  out.update(power_cases(ops, img, soft))
  out.update(match_cases(ops, img))
  return {name: np.asarray(value) for name, value in out.items()}


def _f32(rows):
  """Table of float32 rows."""
  return np.asarray(rows, np.float32)


def _ramp():
  """Heat grid with every level from 0 to over the top."""
  count = GRID[0] * GRID[1]
  values = np.linspace(0.0, HEAT_MAX * 2, count, dtype=np.float32)
  return values.reshape(GRID[::-1])


def differences(golden, current):
  """[(case, biggest absolute difference)]; missing cases are inf."""
  rows = []
  for name in sorted(set(golden) | set(current)):
    if name not in golden or name not in current:
      rows.append((name, float("inf")))
      continue
    a, b = golden[name], current[name]
    if a.shape != b.shape:
      rows.append((name, float("inf")))
      continue
    delta = np.abs(a.astype(np.float64) - b.astype(np.float64))
    rows.append((name, float(delta.max()) if delta.size else 0.0))
  return rows


def report(rows, tolerance):
  """Prints one line per case; returns the exit code."""
  bad = [name for name, delta in rows if delta > tolerance]
  for name, delta in rows:
    mark = "FAIL" if delta > tolerance else "ok"
    print(f"{mark:4} {name:22} max diff {delta:g}")
  print(f"{len(rows) - len(bad)}/{len(rows)} within {tolerance:g}")
  return FAILED if bad else 0


def load(path):
  """{case: array} of a saved .npz."""
  with np.load(path) as data:
    return {name: data[name] for name in data.files}


def parse_args(argv):
  """Command line: save / check / compare."""
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("command", choices=("save", "check", "compare"))
  parser.add_argument("paths", nargs="+")
  parser.add_argument("--fatbin", default=None)
  parser.add_argument("--tolerance", type=float, default=TOLERANCE)
  return parser.parse_args(argv)


def main(argv=None):
  """Entry point; returns the exit code."""
  args = parse_args(argv)
  if args.command == "save":
    np.savez_compressed(args.paths[0], **run_all(args.fatbin))
    print(f"saved {args.paths[0]}")
    return 0
  if args.command == "check":
    rows = differences(load(args.paths[0]), run_all(args.fatbin))
  else:
    rows = differences(load(args.paths[0]), load(args.paths[1]))
  return report(rows, args.tolerance)


if __name__ == "__main__":
  sys.exit(main())
