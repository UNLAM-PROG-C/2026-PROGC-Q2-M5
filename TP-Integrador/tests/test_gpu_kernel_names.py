"""Every kernel the backend asks for exists in the shipped kernels.fatbin.

A fatbin built from the bare `.cu` has C++-mangled names (`_Z9k_tribuna...`)
and the driver then fails with "named symbol not found" at the first frame
that uses the kernel. These tests catch that without playing a match.
"""
import re
import unittest

from fdc.gpu import backend

LAUNCHERS = re.compile(
    r"""(?:_fn\(\s*|_simple\(\s*|_warp\(\s*\w+\s*,\s*)["'](\w+)["']""")
MANGLED = r"_Z\d+%s[A-Z]"
MIN_KERNELS = 30            # the regex must really find the launches


def used_kernels():
  """Kernel names written as literals in backend.py (_fn/_simple/_warp)."""
  with open(backend.__file__, encoding="utf-8") as fh:
    return set(LAUNCHERS.findall(fh.read()))


class KernelNamesTest(unittest.TestCase):
  """Names of backend.py vs kernels.cu vs kernels.fatbin."""

  def test_found_the_kernels_the_backend_uses(self):
    self.assertGreater(len(used_kernels()), MIN_KERNELS)

  def test_backend_only_asks_for_declared_kernels(self):
    missing = used_kernels() - set(backend.kernel_names())
    self.assertEqual(missing, set())

  def test_fatbin_has_every_kernel_with_a_plain_name(self):
    path = backend.prebuilt_path()
    self.assertIsNotNone(path, "run: py tools/build_kernels.py")
    with open(path, "rb") as fh:
      data = fh.read()
    mangled = [n for n in backend.kernel_names()
               if re.search((MANGLED % n).encode(), data)]
    self.assertEqual(mangled, [], "C++-mangled: build with extern C")
    wanted = sorted(used_kernels() | set(backend.kernel_names()))
    absent = [n for n in wanted if n.encode() not in data]
    self.assertEqual(absent, [])

  def test_source_for_the_fatbin_is_extern_c(self):
    text = backend.c_linkage_source()
    self.assertTrue(text.startswith('extern "C" {'))
    self.assertIn(backend.kernel_source(), text)

  def test_driver_resolves_every_kernel(self):
    try:
      import pycuda.autoinit  # noqa: F401  pylint: disable=C0415,W0611
      import pycuda.driver as drv  # pylint: disable=C0415
    except Exception as exc:  # pylint: disable=broad-except
      self.skipTest(f"no CUDA here: {exc}")
    module = drv.module_from_file(backend.prebuilt_path())
    for name in sorted(used_kernels()):
      with self.subTest(kernel=name):
        module.get_function(name)


if __name__ == "__main__":
  unittest.main()
