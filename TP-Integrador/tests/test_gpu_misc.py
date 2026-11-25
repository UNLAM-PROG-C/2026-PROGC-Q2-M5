"""Overlay, flags and machine information without a visible window."""
import types
import unittest

import helpers  # pylint: disable=unused-import
import main as main_module
from fdc import config
from fdc.gpu import backend
from fdc.gpu import overlay
from fdc.gpu import sysinfo

class OverlayTest(unittest.TestCase):
  """The lines of the overlay (readable from the back of a classroom)."""

  INFO = {"mode": "gpu", "device": "RTX 5090", "block": "32x8",
          "grid": "40x90", "threads": "115200", "surplus": 0,
          "resolution": "1280x720", "window": "1280x720", "remote": False,
          "quality": "Q0", "fx_ms": 4.0, "work_ms": 9.0, "fps": 110.0,
          "active": "hielo", "kernels": [("glow", 3.0)]}

  def test_off_has_no_lines(self):
    self.assertEqual(overlay.lines(self.INFO, overlay.OFF), ())

  def test_compact_has_two_lines(self):
    self.assertEqual(len(overlay.lines(self.INFO, overlay.COMPACT)), 2)

  def test_full_has_the_five_lines(self):
    self.assertGreaterEqual(len(overlay.lines(self.INFO, overlay.FULL)), 5)

  def test_lines_say_the_mode_and_the_resolution(self):
    text = " ".join(overlay.lines(self.INFO, overlay.FULL))
    self.assertIn("GPU (CUDA)", text)
    self.assertIn("1280x720", text)
    self.assertIn("hielo", text)

  def test_cpu_mode_names_the_numpy_fallback(self):
    info = dict(self.INFO, mode="cpu", reason="")
    text = " ".join(overlay.lines(info, overlay.COMPACT))
    self.assertIn("numpy", text)


class FlagsTest(unittest.TestCase):
  """--window, --block, --calidad and --backend without opening a window."""

  def test_window_default_and_custom(self):
    app = _app_class()
    self.assertEqual(app._window_size(_app_with(None)),
                     (config.LOGICAL_WIDTH, config.LOGICAL_HEIGHT))
    self.assertEqual(app._window_size(_app_with("1024x600")),
                     (1024, 600))

  def test_window_with_garbage_falls_back(self):
    self.assertEqual(_app_class()._window_size(_app_with("grande")),
                     (config.LOGICAL_WIDTH, config.LOGICAL_HEIGHT))

  def test_parse_args_accepts_the_new_flags(self):
    options = main_module.parse_args(["--presentation",
                                      "--overlay", "full",
                                      "--calidad", "full",
                                      "--backend", "cpu"])
    self.assertTrue(options.presentation)
    self.assertEqual(options.overlay, "full")
    self.assertEqual(options.quality_mode, "full")

  def test_set_block_changes_and_restores(self):
    original = backend.BLOCK
    try:
      self.assertEqual(backend.set_block("16x16"), (16, 16, 1))
      self.assertEqual(backend.BLOCK1D, (16, 1, 1))
    finally:
      backend.set_block(f"{original[0]}x{original[1]}")
    self.assertEqual(backend.BLOCK, original)

  def test_detect_never_raises(self):
    found = backend.detect()
    self.assertIn(found["kind"], ("gpu", "cpu"))
    self.assertIn("device", found)


class SysinfoTest(unittest.TestCase):
  """Machine information used by the CSV and the overlay."""

  def test_host_name(self):
    self.assertTrue(sysinfo.host_name())

  def test_remote_session_is_boolean(self):
    self.assertIsInstance(sysinfo.is_remote_session(), bool)

  def test_cpu_name_is_text(self):
    self.assertTrue(isinstance(sysinfo.cpu_name(), str))

  def test_render_driver_default(self):
    self.assertTrue(sysinfo.render_driver())


def _app_class():
  """App, imported without opening a window."""
  from fdc.ui import app            # pylint: disable=import-outside-toplevel
  return app.App


def _app_with(window):
  """Fake App for _window_size: it only uses `self.options`."""
  return types.SimpleNamespace(options=types.SimpleNamespace(window=window))


if __name__ == "__main__":
  unittest.main()
