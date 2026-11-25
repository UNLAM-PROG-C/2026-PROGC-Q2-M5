"""The GPU zip ships compiled kernels: no nvcc nor MSVC on the player's PC."""
import os
import unittest
from unittest import mock

from fdc.gpu import backend
from fdc.gpu import postfx


class PrebuiltKernelsTest(unittest.TestCase):
  """The fatbin is trusted only while it matches kernels.cu."""

  def test_fatbin_matches_the_source(self):
    path = backend.prebuilt_path()
    self.assertIsNotNone(path, "run: py tools/build_kernels.py")
    self.assertTrue(os.path.getsize(path) > 0)

  def test_stale_hash_is_ignored(self):
    with mock.patch.object(backend, "source_hash", return_value="x"):
      self.assertIsNone(backend.prebuilt_path())

  def test_failure_reason_is_one_short_line(self):
    reason = backend.failure_reason(RuntimeError("a\nb  c" * 100))
    self.assertNotIn("\n", reason)
    self.assertLessEqual(len(reason), backend.REASON_MAX)

  def test_failure_goes_to_the_reasons_list(self):
    reasons = []
    with mock.patch.object(backend, "Gpu", side_effect=OSError("boom")):
      ops = postfx._make_ops(False, reasons)  # pylint: disable=W0212
    self.assertEqual(len(reasons), 1)
    self.assertIn("boom", reasons[0])
    self.assertNotIsInstance(ops, mock.Mock)

  def test_cpu_build_without_pycuda_is_silent(self):
    reasons = []
    err = ModuleNotFoundError("pycuda", name="pycuda")
    with mock.patch.object(backend, "Gpu", side_effect=err):
      postfx._make_ops(False, reasons)  # pylint: disable=W0212
    self.assertEqual(reasons, [])


if __name__ == "__main__":
  unittest.main()
