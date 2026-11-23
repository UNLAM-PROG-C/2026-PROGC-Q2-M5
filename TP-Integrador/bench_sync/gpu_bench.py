"""GPU luma histogram: kernel alone (CUDA events) and the 5 steps."""
import os
import statistics
import time

import numpy as np
import pycuda.autoinit  # pylint: disable=unused-import
import pycuda.compiler
import pycuda.driver as drv

from frames import BINS

THREADS = 256  # threads per block (1D)
BYTES_PER_BIN = 4  # sizeof(unsigned int)
BLOCKS_PER_SM = 4  # resident blocks per multiprocessor in the launch
WARMUP = 3  # launches discarded before timing
MS_PER_SECOND = 1000  # milliseconds per second
KERNELS = {'a_global': 'k_hist_global', 'b_shared': 'k_hist_shared',
           'race': 'k_hist_racy'}
SOURCE = os.path.join(os.path.dirname(__file__), 'kernels.cu')


class GpuHistogram:
  """Compiles kernels.cu once and runs every variant on the same launch."""

  def __init__(self):
    with open(SOURCE, encoding='utf-8') as handle:
      module = pycuda.compiler.SourceModule(handle.read())
    self.fns = {key: module.get_function(name)
                for key, name in KERNELS.items()}
    sms = drv.Context.get_device().get_attribute(
        drv.device_attribute.MULTIPROCESSOR_COUNT)
    self.grid = (sms * BLOCKS_PER_SM, 1)
    self.block = (THREADS, 1, 1)

  def launch(self, key, src, hist, pixels):
    self.fns[key](src, hist, np.int32(pixels), block=self.block,
                  grid=self.grid)

  def kernel_ms(self, key, rgb, runs):
    """Median of the kernel alone; the buffers are already on the GPU."""
    pixels = rgb.shape[0] * rgb.shape[1]
    src, hist = drv.to_device(rgb), drv.mem_alloc(BINS * BYTES_PER_BIN)
    times = [self._timed_launch(key, src, hist, pixels)
             for _ in range(WARMUP + runs)]
    result = self._download(hist)
    src.free()
    hist.free()
    return statistics.median(times[WARMUP:]), result

  def _timed_launch(self, key, src, hist, pixels):
    start, end = drv.Event(), drv.Event()
    drv.memset_d32(hist, 0, BINS)
    start.record()
    self.launch(key, src, hist, pixels)
    end.record()
    end.synchronize()
    return start.time_till(end)

  @staticmethod
  def _download(hist):
    out = np.empty(BINS, dtype=np.uint32)
    drv.memcpy_dtoh(out, hist)
    return out

  def five_steps_ms(self, key, rgb, runs):
    """Median of the full cycle: reserve, upload, kernel, download, free."""
    times = [self._five_steps(key, rgb)[0] for _ in range(WARMUP + runs)]
    return statistics.median(times[WARMUP:])

  def _five_steps(self, key, rgb):
    start = time.perf_counter()
    # Step 1: Allocate device memory (cudaMalloc) and clear the bins.
    src, hist = drv.mem_alloc(rgb.nbytes), drv.mem_alloc(BINS * BYTES_PER_BIN)
    drv.memset_d32(hist, 0, BINS)
    # Step 2: Host-to-device upload (cudaMemcpyHostToDevice).
    drv.memcpy_htod(src, rgb)
    # Step 3: Run the kernel (kernel<<<grid, block>>>).
    self.launch(key, src, hist, rgb.shape[0] * rgb.shape[1])
    # Step 4: Device-to-host download (cudaMemcpyDeviceToHost).
    out = self._download(hist)
    # Step 5: Free device memory (cudaFree).
    src.free()
    hist.free()
    return (time.perf_counter() - start) * MS_PER_SECOND, out


def device_info():
  """Name, compute capability, multiprocessors and CUDA versions."""
  dev = drv.Context.get_device()
  return {'gpu': dev.name(), 'capability': '%d.%d' % dev.compute_capability(),
          'sms': dev.get_attribute(drv.device_attribute.MULTIPROCESSOR_COUNT),
          'driver_cuda': drv.get_driver_version(),
          'pycuda': pycuda.VERSION_TEXT}
