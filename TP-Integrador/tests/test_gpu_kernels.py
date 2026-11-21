"""Every kernel of fdc/gpu against its numpy version (fdc.gpu.cpu_ref).

The GPU tests are skipped when there is no CUDA (or no toolchain): the
game and the rest of the suite work without them. The warps move whole
pixels, so they are compared by mean difference.
"""
import unittest

import numpy as np

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc.gpu import backend
from fdc.gpu import cpu_ref
from fdc.gpu import env

W, H = 80, 60           # test frame
SEED = 11               # fixed random frame
LEVELS = 3              # gray levels of tolerance
HIST_LEVELS = 1         # the histogram counts pixels: one bin may move
WARP_MEAN = 8.0         # mean difference of a warp (it moves pixels)
GAIN = 1.0              # light weight
SPOT_CAP = 0.85         # top of the light of the night (k_spotlights)
SPOT_TOP = int(SPOT_CAP * 255) + 2   # brightest byte a capped light gives

HAVE_GPU = env.setup() and backend.available()
REASON = "no CUDA or no toolchain here (see INSTALACION.md)"
# --- F5: old television of the replay (k_crt)
CRT_ARGS = (5, 0.9, 0.35, 0.45, 0.10, 3, (0.80, 1.0, 0.85))   # frame, ...


def frame():
  """Random RGB frame with a bright patch."""
  rng = np.random.default_rng(SEED)
  img = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)
  img[10:30, 20:50] = 240
  return img


def biggest(a, b):
  """Biggest absolute difference between two images."""
  return float(np.abs(a.astype(np.float32) - b.astype(np.float32)).max())


def mean(a, b):
  """Mean absolute difference between two images."""
  return float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean())


@unittest.skipUnless(HAVE_GPU, REASON)
class KernelTest(unittest.TestCase):
  """The kernels have to give the same image as the numpy reference."""

  @classmethod
  def setUpClass(cls):
    cls.gpu = backend.Gpu()
    cls.cpu = cpu_ref.Cpu()
    cls.img = frame()
    cls.soft = np.repeat(np.repeat(cls.img[::2, ::2], 2, 0), 2, 1)

  def assertClose(self, ours, ref, limit=LEVELS):
    self.assertLessEqual(biggest(ours, ref), limit)

  def assertMean(self, ours, ref, limit=WARP_MEAN):
    self.assertLessEqual(mean(ours, ref), limit)

  def test_glow_and_composite(self):
    field = self.gpu.glow(self.img, 0.6, 2, 2)
    self.assertClose(field, self.cpu.glow(self.img, 0.6, 2, 2), 6)
    params = (1.1, 1.0, 0.3, 0.6)
    self.assertClose(self.gpu.composite(self.img, field, *params),
                     self.cpu.composite(self.img, field, *params), 6)
    self.assertClose(self.gpu.glow_composite(self.img, 0.6, 2, 2,
                                             params),
                     self.cpu.glow_composite(self.img, 0.6, 2, 2,
                                             params), 6)

  def test_particles(self):
    pos = np.array([[10.0, 12.0], [60.0, 40.0]], np.float32)
    col = np.array([[1.0, 0.2, 0.1, 2.0], [0.1, 0.9, 0.3, 3.0]],
                   np.float32)
    self.assertClose(self.gpu.particles(self.img, pos, col, GAIN),
                     self.cpu.particles(self.img, pos, col, GAIN))

  def test_confetti(self):
    """F10: each thread paints the rectangle of one paper bit."""
    pos = np.array([[10.0, 12.0], [60.0, 40.0], [59.0, 41.0]], np.float32)
    col = np.array([[1.0, 1.0, 1.0, 2.0, 2.0],
                    [0.2, 0.9, 0.4, 3.0, 1.0],
                    [1.0, 0.3, 0.2, 3.0, 1.0]], np.float32)
    self.assertClose(self.gpu.confetti(self.img, pos, col, GAIN),
                     self.cpu.confetti(self.img, pos, col, GAIN))
    empty = np.zeros((0, 2), np.float32)
    self.assertClose(self.gpu.confetti(self.img, empty, col[:0], GAIN),
                     self.cpu.confetti(self.img, empty, col[:0], GAIN))

  def test_ice(self):
    """F11: the fused ice pass looks like the chain of the numpy one."""
    args = (0.8, (0.55, 0.85, 1.0), 0.45)
    self.assertClose(self.gpu.ice(self.soft, *args),
                     self.cpu.ice(self.soft, *args))
    self.assertClose(self.gpu.ice(self.img, *args),
                     self.cpu.ice(self.img, *args))

  def test_heat_waves(self):
    self.assertMean(self.gpu.heat(self.soft, 1.0, 3.0, 20.0),
                    self.cpu.heat(self.soft, 1.0, 3.0, 20.0))

  def test_mix(self):
    self.assertClose(self.gpu.mix(self.img, self.img[::-1], 0.4),
                     self.cpu.mix(self.img, self.img[::-1], 0.4))

  def test_histogram_and_stretch(self):
    ours = self.gpu.histogram(self.img)
    self.assertEqual(ours.sum(), self.img.size // 3)
    self.assertLessEqual(biggest(ours, self.cpu.histogram(self.img)),
                         HIST_LEVELS)
    self.assertClose(self.gpu.stretch(self.img, 20.0, 200.0),
                     self.cpu.stretch(self.img, 20.0, 200.0))

class NoGpuTest(unittest.TestCase):
  """Without CUDA the game still has the numpy version."""

  def test_cpu_reference_works(self):
    cpu = cpu_ref.Cpu()
    img = frame()
    out = cpu.ice(img, 0.8, (0.55, 0.85, 1.0), 0.45)
    self.assertEqual(out.shape, img.shape)
    self.assertEqual(out.dtype, np.uint8)

  def test_primitives_work(self):
    cpu = cpu_ref.Cpu()
    img = frame()
    self.assertEqual(cpu.gray(img).shape, img.shape)
    self.assertTrue(np.all(cpu.invert(cpu.invert(img)) == img))
    self.assertEqual(cpu.rotate(img, 0.0).shape, img.shape)


@unittest.skipUnless(HAVE_GPU, REASON)
class PrimitiveTest(unittest.TestCase):
  """The F1 group: gray, invert, gain, tint and rotation."""

  @classmethod
  def setUpClass(cls):
    cls.gpu = backend.Gpu()
    cls.cpu = cpu_ref.Cpu()
    cls.img = frame()

  def assertClose(self, ours, ref, limit=LEVELS):
    self.assertLessEqual(biggest(ours, ref), limit)

  def test_gray_and_invert(self):
    self.assertClose(self.gpu.gray(self.img), self.cpu.gray(self.img))
    self.assertClose(self.gpu.invert(self.img),
                     self.cpu.invert(self.img))

  def test_gain_and_tint(self):
    self.assertClose(self.gpu.gain(self.img, 0.6),
                     self.cpu.gain(self.img, 0.6))
    self.assertClose(self.gpu.tint(self.img, (1.0, 0.8, 0.5)),
                     self.cpu.tint(self.img, (1.0, 0.8, 0.5)))

  def test_rotate(self):
    self.assertClose(self.gpu.rotate(self.img, 0.3),
                     self.cpu.rotate(self.img, 0.3))

@unittest.skipUnless(HAVE_GPU, REASON)
class PowerAndNightTest(unittest.TestCase):
  """F3/F4 kernels: lamps, fire and luma statistics."""

  @classmethod
  def setUpClass(cls):
    cls.gpu = backend.Gpu()
    cls.cpu = cpu_ref.Cpu()
    cls.img = frame()
    cls.soft = np.repeat(np.repeat(cls.img[::2, ::2], 2, 0), 2, 1)

  def assertClose(self, ours, ref, limit=LEVELS):
    self.assertLessEqual(biggest(ours, ref), limit)

  def assertMean(self, ours, ref, limit=WARP_MEAN):
    self.assertLessEqual(mean(ours, ref), limit)

  def test_spotlights(self):
    lights = ((20.0, 20.0, 40.0, 0.9), (60.0, 40.0, 60.0, 0.6))
    params = (0.15, (1.0, 0.86, 0.66))
    self.assertClose(self.gpu.spotlights(self.img, lights, *params),
                     self.cpu.spotlights(self.img, lights, *params), 2)

  def test_spotlights_with_a_cap(self):
    """Lamps on top of each other never pass the cap of the night."""
    lights = ((20.0, 20.0, 40.0, 0.9), (24.0, 22.0, 40.0, 0.9),
              (28.0, 20.0, 40.0, 0.9))
    params = (0.25, (1.0, 0.92, 0.80), SPOT_CAP)
    ours = self.gpu.spotlights(self.img, lights, *params)
    ref = self.cpu.spotlights(self.img, lights, *params)
    self.assertClose(ours, ref, 2)
    self.assertLessEqual(int(ours.max()), SPOT_TOP)
    free = self.gpu.spotlights(self.img, lights, *params[:2])
    self.assertGreater(int(free.max()), int(ours.max()))

  def test_fire(self):
    args = (40.0, 30.0, 30.0, 0.5, 4.0)
    self.assertMean(self.gpu.heat_distort(self.soft, *args),
                    self.cpu.heat_distort(self.soft, *args))

  def test_luma_stats(self):
    ours = self.gpu.luma_stats(self.img)
    ref = self.cpu.luma_stats(self.img)
    self.assertAlmostEqual(ours[0], ref[0], delta=0.5)
    self.assertLessEqual(abs(ours[1] - ref[1]), 2)
    self.assertEqual(ours[2], ref[2])


@unittest.skipUnless(HAVE_GPU, REASON)
class ReplayKernelTest(unittest.TestCase):
  """k_crt (the old television of the replay) against numpy."""

  @classmethod
  def setUpClass(cls):
    cls.gpu = backend.Gpu()
    cls.cpu = cpu_ref.Cpu()
    cls.img = frame()

  def test_crt_matches_the_reference(self):
    out = self.gpu.crt(self.img, *CRT_ARGS)
    self.assertEqual(out.shape, self.img.shape)
    self.assertLessEqual(biggest(out, self.cpu.crt(self.img, *CRT_ARGS)),
                         LEVELS)

  def test_crt_without_amount_is_the_gray_image(self):
    args = (0, 0.0, 0.35, 0.45, 0.10, 3, (1.0, 1.0, 1.0))
    self.assertLessEqual(biggest(self.gpu.crt(self.img, *args),
                                 self.cpu.gray(self.img)), LEVELS)

  def test_crt_grain_changes_with_the_frame(self):
    first = self.gpu.crt(self.img, *CRT_ARGS)
    other = self.gpu.crt(self.img, CRT_ARGS[0] + 1, *CRT_ARGS[1:])
    self.assertGreater(biggest(first, other), LEVELS)


if __name__ == "__main__":
  unittest.main()
