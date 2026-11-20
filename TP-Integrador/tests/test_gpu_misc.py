"""F7 and F8 without a window: governor, demo clock, CSV and flags.

The GPU does not take part here: the governor is a state machine, the
director only counts seconds, the CSV is written in a temporary folder and
the flags are parsed without opening pygame.
"""
import csv
import os
import tempfile
import types
import unittest
from unittest import mock

import helpers  # pylint: disable=unused-import
import main as main_module
from fdc import config
from fdc.gpu import backend
from fdc.gpu import demo
from fdc.gpu import metrics
from fdc.gpu import overlay
from fdc.gpu import quality
from fdc.gpu import sysinfo

G = config.Gpu
SLOW = 25.0              # ms of a frame that asks for a lower level
FAST = 8.0               # ms of a frame that allows a higher level
NORMAL = 14.0            # ms between the two thresholds
DT = 1.0 / config.UI_FPS  # s between frames
DOWN_FRAMES = G.QUALITY_AVG_FRAMES + 1
UP_FRAMES = G.QUALITY_UP_FRAMES + 1
WAIT_FRAMES = int(G.QUALITY_MIN_SECONDS / DT) + 1


class GovernorTest(unittest.TestCase):
  """The CPU quality level follows the mean frame time."""

  def test_gpu_never_changes(self):
    governor = quality.QualityGovernor("auto", "gpu")
    for _ in range(DOWN_FRAMES):
      governor.frame(SLOW, DT)
    self.assertFalse(governor.enabled)
    self.assertEqual(governor.level, quality.MIN_LEVEL)

  def test_fixed_level_ignores_the_clock(self):
    governor = quality.QualityGovernor("2", "cpu")
    for _ in range(DOWN_FRAMES):
      governor.frame(SLOW, DT)
    self.assertFalse(governor.enabled)
    self.assertEqual(governor.level, 2)

  def test_down_with_slow_frames(self):
    governor = quality.QualityGovernor("auto", "cpu")
    for _ in range(DOWN_FRAMES):
      governor.frame(SLOW, DT)
    self.assertEqual(governor.level, 1)

  def test_down_counts_one_per_change(self):
    governor = quality.QualityGovernor("auto", "cpu")
    self._feed(governor, DOWN_FRAMES, SLOW)
    self.assertEqual(governor.changes, 1)

  def test_wait_between_changes(self):
    governor = quality.QualityGovernor("auto", "cpu")
    self._feed(governor, DOWN_FRAMES, SLOW)
    self._feed(governor, DOWN_FRAMES, SLOW)
    self.assertEqual(governor.level, 1)      # still waiting

  def test_up_needs_many_fast_frames(self):
    governor = quality.QualityGovernor("auto", "cpu", level=2)
    self._feed(governor, WAIT_FRAMES + UP_FRAMES, FAST)
    self.assertEqual(governor.level, 1)

  def test_normal_frames_do_nothing(self):
    governor = quality.QualityGovernor("auto", "cpu")
    self._feed(governor, DOWN_FRAMES * 4, NORMAL)
    self.assertEqual(governor.level, quality.MIN_LEVEL)

  def test_level_labels_and_scales(self):
    self.assertEqual([quality.label(index) for index in range(4)],
                     ["Q0", "Q1", "Q2", "Q3"])
    self.assertEqual(quality.scale(0), 1)
    self.assertGreater(quality.scale(3), quality.scale(0))

  def test_level_of_clamps(self):
    self.assertEqual(quality.level_of("9"), 3)
    self.assertEqual(quality.level_of("auto", 2), 2)
    self.assertEqual(quality.level_of("basura"), 0)

  @staticmethod
  def _feed(governor, frames, milliseconds):
    """Calls the governor `frames` times with the same frame time."""
    for _ in range(frames):
      governor.frame(milliseconds, DT)


class DirectorTest(unittest.TestCase):
  """The demo clock runs the ten segments in order."""

  def test_all_segments_in_order(self):
    director = demo.DemoDirector(seconds=1.0)
    seen = []
    for _ in range(int(len(demo.SEGMENTS) * config.UI_FPS) + 1):
      index = director.step(DT, DT)
      if not seen or seen[-1] != index:
        seen.append(index)
    self.assertEqual(seen, list(range(len(demo.SEGMENTS))))

  def test_names_are_the_ones_of_the_spec(self):
    names = [name for name, _ in demo.SEGMENTS]
    self.assertEqual(len(names), 10)
    self.assertIn("VAR con zoom y cartel", names)
    self.assertIn("mapa de calor del partido", names)

  def test_frame_clock_is_repeatable(self):
    director = demo.DemoDirector(seconds=0.5, frame_clock=True)
    indexes = [director.step(0.0, DT) for _ in range(40)]
    self.assertEqual(indexes[-1], 1)

  def test_done_after_the_last_segment(self):
    director = demo.DemoDirector(seconds=1.0, frame_clock=True)
    frames = int(len(demo.SEGMENTS) * config.UI_FPS / 1.0) + 2
    director.step(0.0, 0.0)
    for _ in range(frames):
      director.step(1.0, 1.0)
    self.assertTrue(director.done)
    self.assertEqual(director.remaining(), 0.0)

  def test_label_and_forcing(self):
    director = demo.DemoDirector(seconds=1.0)
    self.assertEqual(director.kind(), None)
    self.assertIn("EFECTO 1/10", director.label())
    for _ in range(int(config.UI_FPS) + 2):
      director.step(DT, DT)
    self.assertEqual(director.kind(), "ice")
    self.assertIn("HIELO", director.label())

  def test_every_kind_has_a_name(self):
    kinds = [kind for _, kind in demo.SEGMENTS[1:]]
    for kind in kinds:
      self.assertTrue(kind)


class DemoPassesTest(unittest.TestCase):
  """Which backends the demo measures, with and without the GPU."""

  def _options(self, **kw):
    opts = types.SimpleNamespace(demo_backends="both", force_cpu=False)
    for name, value in kw.items():
      setattr(opts, name, value)
    return opts

  def test_both_measures_gpu_first(self):
    with mock.patch.object(config.Gpu, "ENABLED", True):
      with mock.patch.object(backend, "available", return_value=True):
        self.assertEqual(demo._passes(self._options()),
                         ["gpu", "cpu"])

  def test_fdc_gpu_0_measures_the_cpu_once(self):
    with mock.patch.object(config.Gpu, "ENABLED", False):
      with mock.patch.object(backend, "available", return_value=True):
        self.assertEqual(demo._passes(self._options()), ["cpu"])

  def test_a_machine_without_nvidia_measures_once(self):
    with mock.patch.object(backend, "available", return_value=False):
      self.assertEqual(demo._passes(self._options()), ["cpu"])

  def test_forced_cpu_measures_numpy_only(self):
    with mock.patch.object(backend, "available", return_value=True):
      opts = self._options(force_cpu=True)
      self.assertEqual(demo._passes(opts), ["cpu"])

  def test_one_backend_is_respected(self):
    opts = self._options(demo_backends="cpu")
    self.assertEqual(demo._passes(opts), ["cpu"])


class MeasurementLogTest(unittest.TestCase):
  """The CSV of the demo: warm-up, columns and percentiles."""

  def setUp(self):
    self.folder = tempfile.mkdtemp()
    self.path = os.path.join(self.folder, "demo.csv")
    self.log = metrics.MeasurementLog(self.path)
    self.log.begin_segment(1, "hielo", "gpu", "RTX", "1280x720",
                           "1280x720", False, "Q0", "32x8")

  def test_warmup_is_dropped(self):
    for _ in range(G.MEASURE_WARMUP + 10):
      self.log.add_frame(10.0, 5.0)
    self.assertEqual(len(self.log.frames), 10)

  def test_row_has_every_column(self):
    for _ in range(G.MEASURE_WARMUP + 2):
      self.log.add_frame(10.0, 5.0)
    row = self.log.end_segment({"gray": 1.0})
    self.assertEqual(tuple(row), metrics.COLUMNS)
    self.assertEqual(row["backend"], "gpu")
    self.assertEqual(row["frames"], 2)

  def test_file_has_header_and_row(self):
    for _ in range(G.MEASURE_WARMUP + 2):
      self.log.add_frame(10.0, 5.0)
    self.log.end_segment()
    with open(self.path, newline="", encoding="utf-8") as fh:
      rows = list(csv.DictReader(fh))
    self.assertEqual(len(rows), 1)
    self.assertEqual(rows[0]["effect"], "hielo")

  def test_percentile(self):
    values = [10.0, 20.0, 30.0, 40.0]
    self.assertEqual(metrics.percentile(values), 40.0)
    self.assertEqual(metrics.percentile([]), 0.0)

  def test_no_segment_open(self):
    other = metrics.MeasurementLog(
        os.path.join(self.folder, "vacio.csv"))
    self.assertIsNone(other.end_segment())


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
  """--window, --block, --quality and --backend without opening a window."""

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
    options = main_module.parse_args(["--demo", "--demo-seconds", "2",
                                      "--demo-backends", "cpu",
                                      "--overlay", "full",
                                      "--quality", "1",
                                      "--backend", "cpu"])
    self.assertTrue(options.demo)
    self.assertEqual(options.demo_seconds, 2.0)
    self.assertEqual(options.overlay, "full")
    self.assertEqual(options.quality, "1")

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
