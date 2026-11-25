"""Golden outputs of every CUDA kernel, to check a refactor of kernels.cu.

It runs each operation of `fdc.gpu.backend.Gpu` on a fixed input and saves
the arrays, so a later build of the kernels can be compared bit by bit.

Usage (PowerShell, from the repository; save and check need the GPU):
    py tools/golden_kernels.py save OUT.npz [--fatbin FILE]
    py tools/golden_kernels.py check GOLDEN.npz [--fatbin FILE]
    py tools/golden_kernels.py compare A.npz B.npz
    py tools/golden_kernels.py subset IN.npz OUT.npz

`--fatbin` loads another compiled module (for example the one of 1.0.2,
whose crowd kernel was still called k_tribuna).
`compare` and `subset` only need numpy.
"""
import argparse
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)
from fdc.gpu import backend  # noqa: E402  pylint: disable=wrong-import-position
from fdc.gpu import cpu_ref  # noqa: E402  pylint: disable=wrong-import-position

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
CASES = ("glow", "glow_composite", "composite", "particles", "confetti",
         "heat", "mix", "histogram", "stretch", "stretch_vignette", "gray",
         "invert", "gain", "tint", "rotate", "ice", "spotlights",
         "spotlights_cap", "heat_distort", "luma_stats", "crt", "crowd")
GLOW_ARGS = (0.55, 3, 2)                      # threshold, radius, passes
CMP_PARAMS = (1.15, 1.0, 0.3, 0.6)            # exposure, gamma, vig., glow
GAIN = 1.0                                    # weight of the light kernels
POS = ((40.0, 50.0), (120.0, 90.0), (300.0, 170.0))   # particles: x, y
COL = ((1.0, 0.2, 0.1, 3.0), (0.2, 1.0, 0.3, 2.0),
       (0.9, 0.9, 1.0, 4.0))                  # r, g, b and size
PAPER = ((1.0, 1.0, 1.0, 2.0, 2.0), (0.2, 0.9, 0.4, 3.0, 1.0),
         (1.0, 0.3, 0.2, 3.0, 1.0))           # r, g, b, half w, half h
HEAT_WARP = (1.0, 4.0, 24.0)                  # phase, amp, period
MIX_ALPHA = 0.35                              # weight of the second image
STRETCH = (20.0, 200.0)                       # new black and white levels
VIGNETTE = 0.3                                # darkening of the corners
IMAGE_GAIN = 1.3                              # gain of k_gain
TINT = (1.0, 0.8, 0.5)                        # rgb of k_tint
ANGLE = 0.3                                   # rad of k_rotate
ICE_ARGS = (0.8, (0.55, 0.85, 1.0), 0.45)     # strength, tint, amount
SPOTS = ((20.0, 20.0, 40.0, 0.9), (60.0, 40.0, 60.0, 0.6),
         (64.0, 42.0, 60.0, 0.9))             # x, y, radius, power
SPOT_ARGS = (0.15, (1.0, 0.86, 0.66))         # ambient, tint
SPOT_CAP = 0.85                               # top of the night light
FIRE_ARGS = (40.0, 30.0, 30.0, 0.5, 4.0)      # cx, cy, rad, t, amp
CRT_ARGS = (5, 0.9, 0.35, 0.45, 0.10, 3, (0.80, 1.0, 0.85))   # frame, ...
CROWD_SIZE = (96, 320)                        # rows, cols of the band
CROWD_BG = (12, 40, 24)                       # grass behind the band
CROWD_ARGS = (1.7, 0, 1.0)                    # t, side, boost


def frame():
  """Fixed RGB test image with a bright rectangle."""
  rng = np.random.default_rng(SEED)
  img = rng.integers(0, BYTE, (H, W, CHANNELS), dtype=np.uint8)
  img[PATCH] = PATCH_COLOR
  return img


def soft_frame(img):
  """Golden fixture: round each averaged axis as in the original input."""
  tmp = cpu_ref._box_axis(img, SOFT_RADIUS, 1).astype(np.uint8)
  return cpu_ref._box_axis(tmp, SOFT_RADIUS, 0).astype(np.uint8)


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
  """Glow, particles and the screen effects."""
  glow = ops.glow(img, *GLOW_ARGS)
  return {
      "glow": glow,
      "glow_composite": ops.glow_composite(img, *GLOW_ARGS, CMP_PARAMS),
      "composite": ops.composite(img, glow, *CMP_PARAMS),
      "particles": ops.particles(img, _f32(POS), _f32(COL), GAIN),
      "confetti": ops.confetti(img, _f32(POS), _f32(PAPER), GAIN),
      "heat": ops.heat(soft, *HEAT_WARP),
      "mix": ops.mix(img, img[::-1], MIX_ALPHA),
  }


def frame_cases(ops, img):
  """Histogram and contrast stretch."""
  return {
      "histogram": ops.histogram(img),
      "stretch": ops.stretch(img, *STRETCH),
      "stretch_vignette": ops.stretch(img, *STRETCH, VIGNETTE),
  }


def pixel_cases(ops, img):
  """The one pixel per thread kernels from gray to rotate."""
  return {
      "gray": ops.gray(img), "invert": ops.invert(img),
      "gain": ops.gain(img, IMAGE_GAIN), "tint": ops.tint(img, TINT),
      "rotate": ops.rotate(img, ANGLE),
  }


def power_cases(ops, img, soft):
  """Powers, night statistics and the old television."""
  return {
      "ice": ops.ice(soft, *ICE_ARGS),
      "spotlights": ops.spotlights(img, SPOTS, *SPOT_ARGS),
      "spotlights_cap": ops.spotlights(img, SPOTS, *SPOT_ARGS, SPOT_CAP),
      "heat_distort": ops.heat_distort(soft, *FIRE_ARGS),
      "luma_stats": np.asarray(ops.luma_stats(img), np.float64),
      "crt": ops.crt(img, *CRT_ARGS),
  }


def crowd_case(ops):
  """Crowd of the stands."""
  from fdc.gpu import crowd  # pylint: disable=import-outside-toplevel
  band = np.empty((*CROWD_SIZE, CHANNELS), np.uint8)
  band[...] = CROWD_BG
  return ops.crowd(band, *CROWD_ARGS, *crowd.params())


def run_all(fatbin=None):
  """{case: array} of every GPU operation on the fixed input."""
  return collect(GoldenGpu(fatbin), frame())


def collect(ops, img):
  """Run the same cases with the given backend."""
  soft = soft_frame(img)
  out = image_cases(ops, img, soft)
  out.update(frame_cases(ops, img))
  out.update(pixel_cases(ops, img))
  out.update(power_cases(ops, img, soft))
  out["crowd"] = crowd_case(ops)
  return {name: np.asarray(value) for name, value in out.items()}


def _f32(rows):
  """Table of float32 rows."""
  return np.asarray(rows, np.float32)


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


def subset(data):
  """Keep exactly the current cases; reject a baseline missing any one."""
  return {name: data[name] for name in CASES}


def parse_args(argv):
  """Command line: save / check / compare / subset."""
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("command", choices=("save", "check", "compare", "subset"))
  parser.add_argument("paths", nargs="+")
  parser.add_argument("--fatbin", default=None)
  parser.add_argument("--tolerance", type=float, default=TOLERANCE)
  args = parser.parse_args(argv)
  expected = 2 if args.command in ("compare", "subset") else 1
  if len(args.paths) != expected:
    parser.error(f"{args.command} expects {expected} path(s)")
  return args


def main(argv=None):
  """Entry point; returns the exit code."""
  args = parse_args(argv)
  if args.command == "save":
    np.savez_compressed(args.paths[0], **run_all(args.fatbin))
    print(f"saved {args.paths[0]}")
    return 0
  if args.command == "subset":
    np.savez_compressed(args.paths[1], **subset(load(args.paths[0])))
    return 0
  if args.command == "check":
    rows = differences(load(args.paths[0]), run_all(args.fatbin))
  else:
    rows = differences(load(args.paths[0]), load(args.paths[1]))
  return report(rows, args.tolerance)


if __name__ == "__main__":
  sys.exit(main())
