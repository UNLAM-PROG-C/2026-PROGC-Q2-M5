"""Every kernel of fdc/gpu against its numpy version (fdc.gpu.cpu_ref).

The GPU tests are skipped when there is no CUDA (or no toolchain): the
game and the rest of the suite work without them. Tolerance: the box blur
rounds twice (one per pass) and the histogram counts pixels, so a couple
of gray levels are expected; the warps move whole pixels, so they are
compared by mean difference.
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
SOFT = 4                # px: the warps are tested on a soft image
GAIN = 1.0              # light weight

HAVE_GPU = env.setup() and backend.available()
REASON = "no CUDA or no toolchain here (see INSTALACION.md)"


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
        cls.soft = cls.cpu.blur(cls.img, SOFT)

    def assertClose(self, ours, ref, limit=LEVELS):
        self.assertLessEqual(biggest(ours, ref), limit)

    def assertMean(self, ours, ref, limit=WARP_MEAN):
        self.assertLessEqual(mean(ours, ref), limit)

    def test_blur(self):
        self.assertClose(self.gpu.blur(self.img, 2),
                         self.cpu.blur(self.img, 2))

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

    def test_lights(self):
        lights = np.array([[20.0, 20.0, 30.0, 0.8, 1.0, 0.9, 0.5]],
                          np.float32)
        self.assertClose(self.gpu.lights(self.img, lights, GAIN),
                         self.cpu.lights(self.img, lights, GAIN))

    def test_warps(self):
        self.assertMean(self.gpu.heat(self.soft, 1.0, 3.0, 20.0),
                        self.cpu.heat(self.soft, 1.0, 3.0, 20.0))
        self.assertMean(self.gpu.ripple(self.soft, 1.0, 3.0, 20.0),
                        self.cpu.ripple(self.soft, 1.0, 3.0, 20.0))

    def test_mix_and_trail(self):
        self.assertClose(self.gpu.mix(self.img, self.img[::-1], 0.4),
                         self.cpu.mix(self.img, self.img[::-1], 0.4))
        self.assertClose(self.gpu.trail(self.img, self.img[::-1], 0.4)[0],
                         self.cpu.trail(self.img, self.img[::-1], 0.4)[0])

    def test_histogram_and_stretch(self):
        ours = self.gpu.histogram(self.img)
        self.assertEqual(ours.sum(), self.img.size // 3)
        self.assertLessEqual(biggest(ours, self.cpu.histogram(self.img)),
                             HIST_LEVELS)
        self.assertClose(self.gpu.stretch(self.img, 20.0, 200.0),
                         self.cpu.stretch(self.img, 20.0, 200.0))

    def test_minimap_and_heat_map(self):
        self.assertClose(self.gpu.minimap(self.img, 8, 6) * 255.0,
                         self.cpu.minimap(self.img, 8, 6) * 255.0, 6)
        heat = np.zeros((6, 8), np.float32)
        points = np.array([[1.0, 1.0], [7.0, 5.0]], np.float32)
        self.assertClose(self.gpu.heat_splat(points, heat, 2.0),
                         self.cpu.heat_splat(points, heat.copy(), 2.0), 0)
        self.assertClose(self.gpu.heat_colors(heat + 1.0, 3.0),
                         self.cpu.heat_colors(heat + 1.0, 3.0))


class NoGpuTest(unittest.TestCase):
    """Without CUDA the game still has the numpy version."""

    def test_cpu_reference_works(self):
        cpu = cpu_ref.Cpu()
        img = frame()
        out = cpu.blur(img, 2)
        self.assertEqual(out.shape, img.shape)
        self.assertEqual(out.dtype, np.uint8)


if __name__ == "__main__":
    unittest.main()
