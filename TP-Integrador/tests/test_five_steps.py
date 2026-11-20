"""The grayscale lesson runs on CPU and can use a fake CUDA driver."""
import unittest
import types
from unittest import mock

import numpy as np
import pygame

from fdc.gpu import backend, cpu_ref, five_steps, overlay, postfx, quality

WIDTH = 33  # px: not a multiple of the block width
HEIGHT = 9  # px: not a multiple of the block height
CHANNELS = 3  # RGB channels
SHAPE = (HEIGHT, WIDTH, CHANNELS)
CPU_MS = 10.0  # fake total in ms
GPU_MS = 2.0  # fake total in ms
THREADS = 1024  # threads launched on a 2 x 2 grid of 32 x 8 blocks
SURPLUS = 727  # threads beyond the image
CPU_ONLY_SKIPS = 3  # upload, download and device cleanup


def _image():
  return np.arange(np.prod(SHAPE)).astype(np.uint8).reshape(SHAPE)


class FakeDriver:
  def __init__(self):
    self.events = []
    self.Context = self
    self.fail_at = None

  def _event(self, name):
    self.events.append(name)
    if name == self.fail_at:
      raise RuntimeError(name)

  def mem_alloc(self, _size):
    self._event("alloc")
    return FakeBuffer(self)

  def memcpy_htod(self, _dest, _src):
    self._event("upload")

  def memcpy_dtoh(self, dest, _src):
    self._event("download")
    dest.fill(0)

  def synchronize(self):
    self._event("sync")

  def launch(self, *_args, **_kwargs):
    self._event("kernel")


class FakeBuffer:
  def __init__(self, driver):
    self.driver = driver

  def free(self):
    self.driver.events.append("free")


def _fake_gpu(driver):
  gpu = backend.Gpu.__new__(backend.Gpu)
  gpu._fns = {"k_gray": driver.launch}
  gpu.driver = driver
  return gpu


class FiveStepsTest(unittest.TestCase):
  def test_cpu_matches_gray(self):
    cpu, image = cpu_ref.Cpu(), _image()
    timer = five_steps.StepTimer()
    actual = cpu.gray_five_steps(image, timer)
    np.testing.assert_array_equal(cpu.gray(image), actual)
    reserve, upload, kernel, read, clean = timer.times.values()
    self.assertGreater(reserve, 0)
    self.assertGreater(kernel, 0)
    self.assertEqual((upload, read, clean), (None, None, None))

  def test_gpu_synchronizes_the_five_steps(self):
    driver = FakeDriver()
    timer = five_steps.StepTimer()
    _fake_gpu(driver).gray_five_steps(_image(), timer)
    self.assertEqual(driver.events, ["sync", "alloc", "alloc", "sync",
                                    "upload", "sync", "kernel", "sync",
                                    "sync", "download", "sync", "free",
                                    "free"])
    self.assertEqual(tuple(timer.times), five_steps.STEP_NAMES)
    self.assertTrue(all(ms > 0 for ms in timer.times.values()))

  def test_cleanup_after_copy_or_kernel_fails(self):
    for name in ("upload", "kernel", "download"):
      with self.subTest(name=name):
        driver = FakeDriver()
        driver.fail_at = name
        timer = five_steps.StepTimer()
        with self.assertRaisesRegex(RuntimeError, name):
          _fake_gpu(driver).gray_five_steps(_image(), timer)
        self.assertEqual(driver.events[-2:], ["free", "free"])

  def test_cleanup_even_if_sync_fails_after_launch(self):
    driver = FakeDriver()
    gpu = _fake_gpu(driver)
    with mock.patch.dict(gpu._fns, k_gray=mock.Mock(side_effect=RuntimeError)):
      with mock.patch.object(driver, 'synchronize') as sync:
        sync.side_effect = [None, None, None, RuntimeError('cleanup sync')]
        with self.assertRaises(RuntimeError):
          gpu.gray_five_steps(_image(), five_steps.StepTimer())
    self.assertEqual(driver.events[-2:], ["free", "free"])

  def test_probe_throttles_cpu_runs(self):
    probe = five_steps.FiveStepProbe()
    cpu = cpu_ref.Cpu()
    first = probe.maybe_run(cpu, _image(), now=0)
    self.assertIsNone(probe.maybe_run(cpu, _image(), now=0))
    self.assertIsNotNone(first)
    self.assertIsNotNone(probe.maybe_run(cpu, _image(),
                                        now=five_steps.PROBE_PERIOD))

  def test_speedup_uses_the_latest_same_input_totals(self):
    probe, image = five_steps.FiveStepProbe(), _image()
    gpu, cpu = _fake_gpu(FakeDriver()), cpu_ref.Cpu()
    with mock.patch.object(five_steps, '_measure') as measure:
      measure.side_effect = [(image, (GPU_MS,)), (image, (CPU_MS,)),
                             (image, (CPU_MS,))]
      probe.maybe_run(gpu, image, now=0)
      self.assertIs(measure.call_args_list[0].args[1], image)
      self.assertIs(measure.call_args_list[1].args[1], image)
      self.assertEqual(probe.speedup((WIDTH, HEIGHT)), '5.0×')
      self.assertIsNone(probe.speedup((WIDTH, HEIGHT - 1)))
      probe.maybe_run(cpu, image.copy(), now=five_steps.PROBE_PERIOD)
      self.assertIsNone(probe.speedup((WIDTH, HEIGHT)))

  def test_zero_gpu_total_is_not_a_speedup(self):
    probe = five_steps.FiveStepProbe()
    probe.size = (WIDTH, HEIGHT)
    probe.totals = {'gpu': 0, 'cpu': CPU_MS}
    self.assertIsNone(probe.speedup(probe.size))

  def test_cpu_steps_page(self):
    cpu, image = cpu_ref.Cpu(), _image()
    probe = five_steps.FiveStepProbe()
    probe.maybe_run(cpu, image, now=0)
    info = probe.info(cpu, (WIDTH, HEIGHT))
    text = '\n'.join(overlay.lines(info, mode=overlay.STEPS))
    self.assertEqual(text.count('no aplica'), CPU_ONLY_SKIPS)
    self.assertIn('GPU: -', text)
    self.assertIn('sin medir', text)
    self.assertIn('33x9', text)
    self.assertIn('32x8', text)
    self.assertIn('warp = 32', text)
    self.assertIn(f'{THREADS} totales', text)
    self.assertIn(f'{SURPLUS} sobrantes', text)

  def test_four_overlay_pages(self):
    with mock.patch.object(overlay.pygame.font, 'Font'):
      panel = overlay.Overlay(mode=overlay.OFF)
    pages = tuple(panel.cycle() for _mode in overlay.MODES)
    self.assertEqual(pages, (overlay.COMPACT, overlay.FULL,
                             overlay.STEPS, overlay.OFF))

  def test_scaled_probe_uses_chain_input_size(self):
    pygame.display.init()
    pygame.display.set_mode((WIDTH, HEIGHT))
    options = types.SimpleNamespace(quality_mode=quality.AUTO,
                                    force_cpu=True, quality='1')
    chain = postfx.PostFx(options, (WIDTH, HEIGHT))
    chain.start()
    chain.probe_active = True
    target = pygame.Surface(chain.target.get_size())
    with mock.patch.object(chain, '_chain', side_effect=lambda img, _dt: img):
      chain.finish(target, 0)
    size = chain.processed_size
    self.assertNotEqual(size, chain.target.get_size())
    self.assertEqual(chain.probe.size, size)

  @unittest.skipUnless(backend.available(), 'CUDA unavailable')
  def test_real_gpu_matches_gray(self):
    gpu, image = backend.Gpu(), _image()
    timer = five_steps.StepTimer()
    np.testing.assert_array_equal(gpu.gray(image),
                                  gpu.gray_five_steps(image, timer))
    self.assertTrue(all(ms > 0 for ms in timer.times.values()))
