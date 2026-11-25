"""Synthetic RGB frames and the reference luma histogram (numpy)."""
import numpy as np

BINS = 256  # one bin per 8-bit luma value
LUMA_WEIGHTS = (77, 150, 29)  # BT.601 in 8.8 fixed point, same as kernels.cu
LUMA_ROUND = 128  # half of 256: round to nearest
LUMA_SHIFT = 8  # divide by 256
SIZES = {'720p': (1280, 720), '1080p': (1920, 1080)}
NIGHT_MAX = 8  # very dark scene: channels in [0, NIGHT_MAX), ~8 bins
SEED = 3658  # fixed seed so every run sees the same pixels


def make_frame(size, scene):
  """'uniform' spreads luma over 256 bins; 'night' piles it on a few."""
  width, height = size
  rng = np.random.default_rng(SEED)
  top = NIGHT_MAX if scene == 'night' else BINS
  return rng.integers(0, top, (height, width, 3), dtype=np.uint8)


def luma_bins(rgb):
  """Integer luma per pixel, identical to luma_bin() in kernels.cu."""
  flat = rgb.reshape(-1, 3).astype(np.uint32)
  weighted = flat @ np.array(LUMA_WEIGHTS, dtype=np.uint32)
  return (weighted + LUMA_ROUND) >> LUMA_SHIFT


def reference(rgb):
  """Ground truth used to check every method."""
  return np.bincount(luma_bins(rgb), minlength=BINS).astype(np.uint32)
