"""Measure a complete grayscale pass without changing the game frame."""
import math
import time

import pygame

from fdc import config
from fdc.gpu import backend, cpu_ref

STEP_NAMES = ('reserve', 'upload', 'kernel', 'download', 'cleanup')
PROBE_PERIOD = config.Gpu.OVERLAY_REFRESH
MS_PER_SECOND = 1000  # milliseconds per second
THUMB_WIDTH = 144  # maximum width of the gray preview in px


class StepTimer:
  """Wall-clock milliseconds per step, with a barrier before each step."""

  def __init__(self):
    self.times = dict.fromkeys(STEP_NAMES)
    self.sync = lambda: None  # numpy has no queued device work

  def _start(self):
    self.sync()
    return time.perf_counter()

  def _record(self, name, start):
    self.times[name] = (time.perf_counter() - start) * MS_PER_SECOND

  def measure(self, name, operation, *args):
    start = self._start()
    result = operation(*args)
    self._record(name, start)
    return result

  def cleanup(self, operation, *args):
    """Always release resources, even if the timing barrier fails."""
    try:
      start = self._start()
    finally:
      operation(*args)
    self._record('cleanup', start)


def _measure(ops, image):
  timer = StepTimer()
  result = ops.gray_five_steps(image, timer)
  return result, tuple(timer.times.values())


def _total(times):
  return sum(ms for ms in times if ms is not None)


def _thumbnail(image, size):
  width, height = size
  thumb = min(width, THUMB_WIDTH)
  raw = pygame.image.frombytes(image.tobytes(), size, 'RGB')
  return pygame.transform.scale(raw, (thumb, max(1, height * thumb // width)))


def geometry(size):
  """The same geometry used to launch the actual 2D kernel."""
  if size is None:
    return {}
  width, height = size
  block, grid = backend.BLOCK, backend.grid_for(width, height)
  threads = math.prod(block) * math.prod(grid)
  return {'block': f'{block[0]}x{block[1]}',
          'grid': f'{grid[0]}x{grid[1]}', 'threads': threads,
          'surplus': threads - width * height}


class FiveStepProbe:
  """Throttle the lesson and only compare timings from a shared input."""

  def __init__(self):
    self.reset()

  def reset(self):
    self.last_run = None
    self.invalidate()

  def invalidate(self):
    self.size = None
    self.block = None
    self.mode = None
    self.steps = ()
    self.totals = {}
    self.thumbnail = None

  def maybe_run(self, ops, image, now=None):
    size = image.shape[1], image.shape[0]
    if size != self.size or backend.BLOCK != self.block:
      self.invalidate()
    now = time.perf_counter() if now is None else now
    if self.last_run is not None and now - self.last_run < PROBE_PERIOD:
      return None
    self.last_run = now
    return self._sample(ops, image, size)

  def _sample(self, ops, image, size):
    result, self.steps = _measure(ops, image)
    self.size, self.block, self.mode = size, backend.BLOCK, _mode(ops)
    self.totals = self._paired_totals(ops, image)
    self.thumbnail = _thumbnail(result, size)
    return result

  def _paired_totals(self, ops, image):
    if _mode(ops) == 'gpu':
      _, cpu_steps = _measure(cpu_ref.Cpu(), image)
      return {'gpu': _total(self.steps), 'cpu': _total(cpu_steps)}
    return {'cpu': _total(self.steps)}

  def speedup(self, size):
    cpu, gpu = self.totals.get('cpu'), self.totals.get('gpu')
    if size != self.size or cpu is None or gpu is None or gpu <= 0:
      return None
    return f'{cpu / gpu:.1f}×'

  def info(self, ops, size):
    valid = size == self.size and backend.BLOCK == self.block
    current = valid and _mode(ops) == self.mode
    return {**geometry(size), 'steps': self.steps if current else (),
            'totals': self.totals if valid else {},
            'speedup': self.speedup(size) if valid else None,
            'thumbnail': self.thumbnail if current else None,
            'resolution': f'{size[0]}x{size[1]}' if size else '-'}


def _mode(ops):
  return 'gpu' if isinstance(ops, backend.Gpu) else 'cpu'
