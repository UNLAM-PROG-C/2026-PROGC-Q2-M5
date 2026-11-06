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
RING_MEAN = 15.0        # the shock ring also adds brightness
SOFT = 4                # px: the warps are tested on a soft image
GAIN = 1.0              # light weight
STAND_ROW = 20          # y of the test frame where the stands end
SPOT_CAP = 0.85         # top of the light of the night (k_spotlights)
SPOT_TOP = int(SPOT_CAP * 255) + 2   # brightest byte a capped light gives

HAVE_GPU = env.setup() and backend.available()
REASON = "no CUDA or no toolchain here (see INSTALACION.md)"
# --- F5: old television of the replay (k_crt)
CRT_ARGS = (5, 0.9, 0.35, 0.45, 0.10, 3, (0.80, 1.0, 0.85))   # frame, ...
# --- F6: heat map (k_heat_accumulate and k_heat_render)
HEAT_COLS, HEAT_ROWS = 5, 4
HEAT_ALPHA = 0.55          # weight of the map over the image
HEAT_GAIN = 4.0            # cells over the top that saturate
INSIDE_POINTS = 4          # points of the test that fall in the pitch


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

    def test_lights(self):
        lights = np.array([[20.0, 20.0, 30.0, 0.8, 1.0, 0.9, 0.5]],
                          np.float32)
        self.assertClose(self.gpu.lights(self.img, lights, GAIN),
                         self.cpu.lights(self.img, lights, GAIN))

    def test_ice(self):
        """F11: the fused ice pass looks like the chain of the numpy one."""
        args = (0.8, (0.55, 0.85, 1.0), 0.45)
        self.assertClose(self.gpu.ice(self.soft, *args),
                         self.cpu.ice(self.soft, *args))
        self.assertClose(self.gpu.ice(self.img, *args),
                         self.cpu.ice(self.img, *args))

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

    def test_primitives_work(self):
        cpu = cpu_ref.Cpu()
        img = frame()
        self.assertEqual(cpu.gray(img).shape, img.shape)
        self.assertTrue(np.all(cpu.invert(cpu.invert(img)) == img))
        self.assertEqual(cpu.rotate(img, 0.0).shape, img.shape)


@unittest.skipUnless(HAVE_GPU, REASON)
class PrimitiveTest(unittest.TestCase):
    """The F1 group: gray, invert, gain, sobel and friends."""

    @classmethod
    def setUpClass(cls):
        cls.gpu = backend.Gpu()
        cls.cpu = cpu_ref.Cpu()
        cls.img = frame()
        cls.gray = cls.cpu.to_gray(cls.img)

    def assertClose(self, ours, ref, limit=LEVELS):
        self.assertLessEqual(biggest(ours, ref), limit)

    def test_gray_and_invert(self):
        self.assertClose(self.gpu.gray(self.img), self.cpu.gray(self.img))
        self.assertClose(self.gpu.invert(self.img),
                         self.cpu.invert(self.img))

    def test_brightness_gain_tint(self):
        self.assertClose(self.gpu.brightness_contrast(self.img, 0.1, 1.4),
                         self.cpu.brightness_contrast(self.img, 0.1, 1.4))
        self.assertClose(self.gpu.gain(self.img, 0.6),
                         self.cpu.gain(self.img, 0.6))
        self.assertClose(self.gpu.tint(self.img, (1.0, 0.8, 0.5)),
                         self.cpu.tint(self.img, (1.0, 0.8, 0.5)))

    def test_rotate(self):
        self.assertClose(self.gpu.rotate(self.img, 0.3),
                         self.cpu.rotate(self.img, 0.3))

    def test_to_gray_and_sobel(self):
        ours = self.gpu.to_gray(self.img)
        self.assertLessEqual(np.abs(ours - self.gray).max(), 0.002)
        top = float(self.cpu.sobel(self.gray).max())
        self.assertLessEqual(
            np.abs(self.gpu.sobel(self.gray) - self.cpu.sobel(self.gray)).max(),
            0.01 * top)

    def test_edges(self):
        edges = self.cpu.sobel(self.gray)
        self.assertClose(self.gpu.sobel_normalize(edges, 1.0),
                         self.cpu.sobel_normalize(edges, 1.0))
        norm = self.cpu.sobel_normalize(edges)
        self.assertClose(self.gpu.edge_glow(self.img, norm, 0.8),
                         self.cpu.edge_glow(self.img, norm, 0.8))


@unittest.skipUnless(HAVE_GPU, REASON)
class PowerAndNightTest(unittest.TestCase):
    """F3/F4 kernels: lamps, fire, shock ring, trail and luma statistics."""

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

    def test_shock_ring(self):
        args = (40.0, 30.0, 12.0, 8.0, 5.0)
        self.assertMean(self.gpu.ripple_ring(self.soft, *args),
                        self.cpu.ripple_ring(self.soft, *args), RING_MEAN)

    def test_shock_ring_keeps_the_stands(self):
        """Above y_min (the stands and the boards) the pixel is copied."""
        args = (40.0, 30.0, 12.0, 8.0, 5.0, STAND_ROW)
        for out in (self.gpu.ripple_ring(self.soft, *args),
                    self.cpu.ripple_ring(self.soft, *args)):
            self.assertTrue(np.array_equal(out[:STAND_ROW],
                                           self.soft[:STAND_ROW]))

    def test_trail_blend(self):
        prev = self.img[::-1].copy()
        self.assertClose(self.gpu.trail_blend(self.img, prev, 0.55),
                         self.cpu.trail_blend(self.img, prev, 0.55), 1)

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


@unittest.skipUnless(HAVE_GPU, REASON)
class HeatmapKernelTest(unittest.TestCase):
    """k_heat_accumulate and k_heat_render against numpy (exact counts)."""

    @classmethod
    def setUpClass(cls):
        cls.gpu = backend.Gpu()
        cls.cpu = cpu_ref.Cpu()
        cls.img = frame()
        cls.cell_w = W / HEAT_COLS      # px of one cell, across
        cls.cell_h = H / HEAT_ROWS      # px of one cell, down
        cls.points = np.array([[8.0, 8.0], [72.0, 55.0], [40.0, 30.0],
                               [8.0, 8.0], [300.0, 20.0]], np.float32)

    def accumulate(self, ops, channel=1, points=None):
        """Grids and maximums after one flush of the test points."""
        ops.heat_reset(HEAT_COLS, HEAT_ROWS)
        pts = self.points if points is None else points
        ops.heat_accumulate(channel, pts, HEAT_COLS, HEAT_ROWS, self.cell_w,
                            self.cell_h)
        return ops.heat_download(HEAT_COLS, HEAT_ROWS)

    def test_accumulate_is_exact(self):
        ours = self.accumulate(self.gpu)
        ref = self.accumulate(self.cpu)
        self.assertTrue(np.array_equal(ours[0], ref[0]))
        self.assertTrue(np.array_equal(ours[1], ref[1]))

    def test_points_outside_the_pitch_are_dropped(self):
        grids, maxes = self.accumulate(self.gpu)
        self.assertEqual(int(grids[1].sum()), INSIDE_POINTS)
        self.assertEqual(int(maxes[1]), 2)      # (8, 8) counts twice

    def test_every_point_goes_to_its_channel(self):
        for channel in range(3):
            grids, maxes = self.accumulate(self.gpu, channel)
            self.assertEqual(int(grids[channel].sum()), INSIDE_POINTS)
            self.assertEqual(int(grids.sum()), INSIDE_POINTS)
            self.assertEqual(int(maxes[channel]), 2)

    def test_render_without_heat_keeps_the_image(self):
        grids = np.zeros((3, HEAT_ROWS, HEAT_COLS), np.uint32)
        maxes = np.zeros(3, np.uint32)
        args = (HEAT_COLS, HEAT_ROWS, 0)
        ours = self.gpu.heat_render(self.img, grids, maxes, *args,
                                    HEAT_ALPHA, HEAT_GAIN)
        self.assertLessEqual(biggest(ours, self.img), LEVELS)

    def test_render_matches_the_reference(self):
        grids, maxes = self.accumulate(self.cpu)
        args = (HEAT_COLS, HEAT_ROWS, 1, HEAT_ALPHA, HEAT_GAIN)
        ours = self.gpu.heat_render(self.img, grids, maxes, *args)
        ref = self.cpu.heat_render(self.img, grids, maxes, *args)
        self.assertLessEqual(biggest(ours, ref), LEVELS)
        self.assertGreater(biggest(ours, self.img), LEVELS)


if __name__ == "__main__":
    unittest.main()
