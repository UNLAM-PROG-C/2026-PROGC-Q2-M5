"""The crowd of the stands (F11): the CUDA kernel against the numpy one.

The two versions paint the band from a hash of each seat, so they must give
the same picture (with a tolerance for the sines and the rounding). The rest
of the tests check that the band is really repainted, that it moves with the
clock and that a goal gets the stand of the scorer to jump.
"""
import unittest

import numpy as np

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc import config
from fdc.gpu import backend
from fdc.gpu import cpu_ref
from fdc.gpu import crowd

WIDTH, HEIGHT = 320, 96      # small band: the numpy version is slow on purpose
TOLERANCE = 2                # channel difference allowed between the two
EDGE_SHARE = 0.05            # % of pixels that may sit on a shape edge: the
              # sines of the GPU and numpy differ in the last
              # bits and one pixel of an edge can flip
QUARTER = 4.0                # the mean difference must stay well under it
BACKGROUND = (12, 40, 24)    # "grass" behind the band: it must disappear
SAME_BACKGROUND = 1.0        # % of pixels that may keep the background
TIME = 1.7                   # s of the animation
LATER = 2.4                  # another moment of the animation
SIDE = 0                     # left stand
BOOST = 1.0                  # celebrating as hard as it can
NO_BOOST = 0.0               # nothing to celebrate
LEFT = (0, WIDTH // 2)       # left half of the band
RIGHT = (WIDTH // 2, WIDTH)  # right half


def band():
  """Empty band of the stands (h, w, 3) over the background colour."""
  image = np.empty((HEIGHT, WIDTH, 3), np.uint8)
  image[...] = BACKGROUND
  return image


def paint(ops, image, t=TIME, side=SIDE, boost=BOOST):
  """Paints the band with one backend and returns the picture."""
  cfg, pal = crowd.params()
  return ops.tribuna(image, t, side, boost, cfg, pal)


def _changed(first, second, columns):
  """Share of the pixels of a slice of columns that changed."""
  a = first[:, columns[0]:columns[1]]
  b = second[:, columns[0]:columns[1]]
  return np.any(a != b, axis=2).mean()


class CrowdParamsTest(unittest.TestCase):
  """The parameters the kernel receives are the ones of the config."""

  def test_params_have_the_size_of_the_kernel(self):
    cfg, pal = crowd.params()
    self.assertEqual(len(cfg), backend.CROWD_CFG)
    self.assertEqual(len(pal), backend.CROWD_PAL)
    self.assertLessEqual(max(pal), 1.0)
    self.assertGreaterEqual(min(pal), 0.0)

  def test_band_of_a_screen(self):
    rect = crowd.band((config.LOGICAL_WIDTH, config.LOGICAL_HEIGHT))
    self.assertEqual(rect.top, config.Gpu.CROWD_TOP)
    self.assertEqual(rect.bottom, config.Gpu.CROWD_BOTTOM)


class CrowdPaintTest(unittest.TestCase):
  """What the crowd paints, with the numpy version (it runs everywhere)."""

  def setUp(self):
    self.ops = cpu_ref.Cpu()

  def test_band_is_fully_painted(self):
    out = paint(self.ops, band())
    self.assertEqual(out.shape, (HEIGHT, WIDTH, 3))
    same = np.all(out == BACKGROUND, axis=2).mean() * 100.0
    self.assertLess(same, SAME_BACKGROUND)

  def test_crowd_moves_with_the_clock(self):
    first = paint(self.ops, band(), t=TIME)
    second = paint(self.ops, band(), t=LATER)
    different = np.any(first != second, axis=2).mean() * 100.0
    self.assertGreater(different, SAME_BACKGROUND)

  def test_goal_gets_one_stand_to_jump(self):
    calm = paint(self.ops, band(), boost=NO_BOOST)
    party = paint(self.ops, band(), boost=BOOST)
    left = _changed(calm, party, LEFT)
    right = _changed(calm, party, RIGHT)
    self.assertGreater(left, right)

  def test_each_side_has_its_own_stand(self):
    left = paint(self.ops, band(), side=0)
    right = paint(self.ops, band(), side=1)
    self.assertFalse(np.array_equal(left, right))


@unittest.skipUnless(backend.available(), "sin CUDA: solo se prueba numpy")
class CrowdGpuTest(unittest.TestCase):
  """The CUDA kernel and the numpy version paint the same band."""

  @classmethod
  def setUpClass(cls):
    cls.gpu = backend.Gpu()
    cls.cpu = cpu_ref.Cpu()

  def _check(self, one, other):
    """The pictures match but for the stray pixel of a shape edge."""
    diff = np.abs(one.astype(np.int32) - other.astype(np.int32))
    edges = float((diff.max(axis=2) > TOLERANCE).mean()) * 100.0
    self.assertLessEqual(edges, EDGE_SHARE)
    self.assertLess(float(diff.mean()), TOLERANCE / QUARTER)

  def test_gpu_and_numpy_agree(self):
    self._check(paint(self.gpu, band()), paint(self.cpu, band()))

  def test_gpu_animates_like_numpy(self):
    self._check(paint(self.gpu, band(), t=LATER),
                paint(self.cpu, band(), t=LATER))


if __name__ == "__main__":
  unittest.main()
