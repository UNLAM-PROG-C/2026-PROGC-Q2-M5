"""GPU implementation of the effects chain (PyCUDA).

Every operation is one or more kernels of `kernels.cu`: one thread per
pixel, 2D index, border check, global memory only and atomics when two
threads write the same pixel. The images travel as numpy arrays (RGB uint8,
shape h x w x 3) and the intermediate light buffers as float32.

`fdc.gpu.cpu_ref.Cpu` has the same methods with numpy, so the tests compare
both and the game falls back to the CPU when there is no CUDA.
"""
import hashlib
import re
import logging
import os

import numpy as np

from fdc.gpu import primitives

CHANNELS = 3                    # interleaved RGB
BINS = 256                      # luminance levels of the histogram
BLOCK = (32, 8, 1)              # threads per block (2D: x wide, y tall)
BLOCK1D = (32, 1, 1)            # for the kernels with one index (particles)
COMPILER_OPTIONS = ["-std=c++17", "--use_fast_math"]
DEFAULT_ARCH = "sm_120"         # RTX 50 series; it is detected at runtime
KERNEL_FILE = "kernels.cu"      # the CUDA source, next to this module
CONFIG_HEADER = "kernels_config.cuh"  # compile-time constants for the source
FATBIN_FILE = "kernels.fatbin"  # the same, compiled (tools/build_kernels)
HASH_FILE = "kernels.sha256"    # sha256 of the expanded CUDA source
REASON_MAX = 160                # characters of the failure shown on screen
MIN_ALLOC = 4                   # bytes: CUDA does not allocate 0
LAMP_FIELDS = 4                 # x, y, radius and power of one lamp
FALLBACK_CC = (12, 0)           # compute capability if it cannot be read
CROWD_CFG = 24                  # parameters of the crowd kernel
CROWD_PAL = 48                  # colours of the crowd kernel (16 rgb triplets)


def kernel_path():
  """Absolute path of the CUDA source."""
  return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      KERNEL_FILE)


def kernel_source():
  """Expand the local header for NVCC and PyCUDA temporary source files."""
  folder = os.path.dirname(kernel_path())
  with open(os.path.join(folder, CONFIG_HEADER), encoding="utf-8") as fh:
    config = fh.read()
  with open(kernel_path(), encoding="utf-8") as fh:
    return fh.read().replace(f'#include "{CONFIG_HEADER}"', config.rstrip())


def c_linkage_source():
  """The source inside `extern "C"`, as PyCUDA's SourceModule compiles it.

    nvcc treats a `.cu` as C++ and mangles the kernel names (`_Z7k_crowd..`)
    unless they sit in an `extern "C"` block; the driver looks them up by
    their plain name. The fatbin must be built from this text.
    """
  return 'extern "C" {\n' + kernel_source() + '\n}\n'


def kernel_names():
  """Names of the `__global__` kernels declared in `kernels.cu`."""
  return sorted(set(re.findall(r"__global__\s+void\s+(\w+)",
                               kernel_source())))


def source_hash():
  """sha256 (hex) of the CUDA source."""
  return hashlib.sha256(kernel_source().encode("utf-8")).hexdigest()


def prebuilt_path():
  """Path of the compiled kernels, or None if missing or out of date.

    The fatbin is only trusted when the hash saved at build time is the one
    of the current CUDA source (including its header); otherwise the source
    is compiled on the developer PC.
    """
  folder = os.path.dirname(os.path.abspath(__file__))
  fatbin = os.path.join(folder, FATBIN_FILE)
  try:
    with open(os.path.join(folder, HASH_FILE), encoding="ascii") as fh:
      saved = fh.read().strip()
  except OSError:
    return None
  if os.path.isfile(fatbin) and saved == source_hash():
    return fatbin
  return None


def failure_reason(exc):
  """One line for the player: why the GPU is not used (also logged)."""
  text = " ".join(str(exc).split()) or type(exc).__name__
  reason = f"{type(exc).__name__}: {text}"[:REASON_MAX]
  logging.getLogger("fdc.gpu").warning(
      "GPU unavailable; using CPU effects. Reason: %s", reason)
  return reason


def log_backend(mode, device):
  """One log line with the backend the effects run on."""
  logging.getLogger("fdc.gpu").info(
      "Effects backend: %s (%s)", mode.upper(), device)


def available():
  """True if PyCUDA and the driver work here (the context is created)."""
  try:
    import pycuda.autoinit     # pylint: disable=unused-import
  except Exception:              # pylint: disable=broad-except
    return False
  return True


def detect():
  """{'kind', 'device', 'reason'}: PyCUDA status, without raising."""
  try:
    import pycuda.autoinit     # pylint: disable=unused-import
    import pycuda.driver as drv
    return {"kind": "gpu", "device": drv.Device(0).name(), "reason": None}
  except Exception as exc:       # pylint: disable=broad-except
    return {"kind": "cpu", "device": "CPU", "reason": str(exc)}


def set_block(value):
  """Changes the threads per block ('WxH'); keeps BLOCK1D in sync."""
  global BLOCK, BLOCK1D          # pylint: disable=global-statement
  width, height = (int(part) for part in str(value).lower().split("x"))
  BLOCK = (width, height, 1)
  BLOCK1D = (width, 1, 1)
  return BLOCK


def device_name():
  """Name of the GPU, or 'CPU' when there is none."""
  if not available():
    return "CPU"
  import pycuda.driver as drv
  return drv.Device(0).name()


def sync():
  """Waits until the GPU finishes the queued work (true timings)."""
  if available():
    import pycuda.driver as drv
    drv.Context.synchronize()


def _auto_arch(driver):
  """'sm_XY' of the first device (the one PyCUDA uses)."""
  try:
    major, minor = driver.Device(0).compute_capability()
  except Exception:              # pylint: disable=broad-except
    major, minor = FALLBACK_CC
  return f"sm_{major}{minor}"


def grid_for(width, height):
  """Round up the grid to cover every pixel with BLOCK threads per block."""
  return ((width + BLOCK[0] - 1) // BLOCK[0],
          (height + BLOCK[1] - 1) // BLOCK[1])


def _free_buffers(buffers):
  """Free the input even if freeing the output fails."""
  try:
    if len(buffers) > 1:
      buffers[1].free()
  finally:
    if buffers:
      buffers[0].free()


class Gpu(primitives.Primitives):
  """The kernels of `kernels.cu`, wrapped as numpy in / numpy out."""

  def __init__(self, arch=None):
    import pycuda.autoinit     # pylint: disable=unused-import
    import pycuda.compiler
    import pycuda.driver as drv
    self.driver = drv
    self.arch = arch or _auto_arch(drv)
    self.module = self._load_module(arch, pycuda.compiler)
    self._fns = {}
    self._buffers = {}

  def _load_module(self, arch, compiler):
    """Compiled kernels if they match; else nvcc compiles the source."""
    fatbin = None if arch else prebuilt_path()
    if fatbin:
      return self.driver.module_from_file(fatbin)
    return compiler.SourceModule(
        kernel_source(), arch=self.arch, options=COMPILER_OPTIONS)

  # ------------------------------------------------------------- plumbing
  def _fn(self, name):
    """Kernel function, taken from the module the first time."""
    if name not in self._fns:
      self._fns[name] = self.module.get_function(name)
    return self._fns[name]

  def _buf(self, name, shape, dtype, host=None):
    """Cache a global memory buffer by name, shape and dtype."""
    key = (name, tuple(shape), np.dtype(dtype).str)
    buf = self._buffers.get(key)
    if buf is None:
      # Step 1: Allocate device memory (cudaMalloc); reused by the game.
      size = max(int(np.prod(shape)) * np.dtype(dtype).itemsize,
                 MIN_ALLOC)
      buf = self.driver.mem_alloc(size)
      self._buffers[key] = buf
    if host is not None:
      # Step 2: Host-to-device upload (cudaMemcpyHostToDevice).
      self.driver.memcpy_htod(buf, np.ascontiguousarray(host))
    return buf

  def _get(self, dev, shape, dtype):
    """Return a new NumPy array; the device buffer stays in the cache."""
    # Step 1: Allocate host output (malloc), deferred until the readback.
    host = np.empty(shape, dtype=dtype)
    # Step 4: Read the output (cudaMemcpyDeviceToHost).
    self.driver.memcpy_dtoh(host, dev)
    return host

  def _grid(self, w, h):
    """2D grid that covers a w x h image with BLOCK threads per block."""
    return grid_for(w, h)

  # --------------------------------------------------------------- images
  def glow(self, img, threshold, radius, passes):
    """Bright pass at half resolution, then `passes` box blurs."""
    h, w = img.shape[:2]
    gw, gh = w // 2, h // 2
    src = self._buf("glow_src", (h, w, CHANNELS), np.uint8, img)
    a = self._buf("glow_a", (gh, gw, CHANNELS), np.float32)
    b = self._buf("glow_b", (gh, gw, CHANNELS), np.float32)
    self._fn("bright_pass")(src, a, np.int32(gw), np.int32(gh),
                            np.int32(w), np.float32(threshold),
                            grid=self._grid(gw, gh), block=BLOCK)
    self._blur_field(a, b, gw, gh, radius, passes)
    return self._get(a, (gh, gw, CHANNELS), np.float32)

  def glow_composite(self, img, threshold, radius, passes, params):
    """Glow and composite without leaving the device (one trip)."""
    h, w = img.shape[:2]
    gw, gh = w // 2, h // 2
    src = self._buf("gc_src", (h, w, CHANNELS), np.uint8, img)
    a = self._buf("gc_a", (gh, gw, CHANNELS), np.float32)
    b = self._buf("gc_b", (gh, gw, CHANNELS), np.float32)
    out = self._buf("gc_out", (h, w, CHANNELS), np.uint8)
    self._fn("bright_pass")(src, a, np.int32(gw), np.int32(gh),
                            np.int32(w), np.float32(threshold),
                            grid=self._grid(gw, gh), block=BLOCK)
    self._blur_field(a, b, gw, gh, radius, passes)
    self._composite(src, a, out, w, h, gw, gh, params)
    return self._get(out, (h, w, CHANNELS), np.uint8)

  def _composite(self, src, field, out, w, h, gw, gh, params):
    """Exposure, gamma, vignette and halo, already on the device."""
    exposure, gamma, vignette, strength = params
    self._fn("composite")(src, field, out, np.int32(w), np.int32(h),
                          np.int32(gw), np.int32(gh),
                          np.float32(exposure), np.float32(gamma),
                          np.float32(vignette), np.float32(strength),
                          grid=self._grid(w, h), block=BLOCK)

  def _blur_field(self, src, tmp, w, h, radius, passes):
    """`passes` separable box blurs of a float field, in place."""
    size = (np.int32(w), np.int32(h), np.int32(radius))
    grid = self._grid(w, h)
    for _ in range(passes):
      self._fn("glow_rows")(src, tmp, *size, grid=grid, block=BLOCK)
      self._fn("glow_cols")(tmp, src, *size, grid=grid, block=BLOCK)

  def composite(self, img, glow, exposure, gamma, vignette, strength):
    """Exposure, glow, gamma and vignette, all in one pass."""
    h, w = img.shape[:2]
    gw, gh = glow.shape[1], glow.shape[0]
    shape = (h, w, CHANNELS)
    src = self._buf("cmp_src", shape, np.uint8, img)
    field = self._buf("cmp_glow", glow.shape, np.float32, glow)
    out = self._buf("cmp_out", shape, np.uint8)
    self._composite(src, field, out, w, h, gw, gh,
                    (exposure, gamma, vignette, strength))
    return self._get(out, shape, np.uint8)

  def particles(self, img, pos, col, gain):
    """Additive glowing particles: pos (n,2), col (n,4) r,g,b,size."""
    return self._splat(img, pos, col[:, :CHANNELS], col[:, CHANNELS], gain,
                       "particles")

  def confetti(self, img, pos, col, gain):
    """Confetti: pos (n,2), col (n,5) r,g,b, half width, half height."""
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    acc = self._buf("confetti_acc", shape, np.float32,
                    np.zeros(shape, np.float32))
    if len(pos) > 0:
      self._confetti_points(img, pos, col, gain, acc, w, h)
    return self._add(img, acc, 1.0)

  def _confetti_points(self, img, pos, col, gain, acc, w, h):
    """One thread per paper bit blends its rectangle over the image."""
    table = self._buf("confetti_tab", col.shape, np.float32, col)
    count = int(len(pos))
    src = self._buf("confetti_src", img.shape, np.uint8, img)
    self._fn("confetti")(
        self._buf("confetti_pos", pos.shape, np.float32, pos), table,
        np.int32(count), src, acc, np.int32(w), np.int32(h),
        np.float32(gain),
        grid=((count + BLOCK[0] - 1) // BLOCK[0], 1, 1), block=BLOCK1D)

  def heat(self, img, phase, amp, period):
    """Heat waves: each pixel reads from a shifted place."""
    return self._warp(img, "heat_distort", phase, amp, period)

  def mix(self, a, b, alpha):
    """Linear mix: alpha 0 keeps `a`, alpha 1 keeps `b`."""
    h, w = a.shape[:2]
    shape = (h, w, CHANNELS)
    first = self._buf("mix_a", shape, np.uint8, a)
    second = self._buf("mix_b", shape, np.uint8, b)
    out = self._buf("mix_out", shape, np.uint8)
    self._fn("mix_layers")(first, second, out, np.int32(w), np.int32(h),
                           np.float32(alpha), grid=self._grid(w, h),
                           block=BLOCK)
    return self._get(out, shape, np.uint8)

  # ------------------------------------------------------------ analysis
  def histogram(self, img):
    """256 bins of luminance (int32)."""
    h, w = img.shape[:2]
    src = self._buf("hist_src", (h, w, CHANNELS), np.uint8, img)
    hist = self._buf("hist_bins", (BINS,), np.int32, np.zeros(BINS,
                                                             np.int32))
    self._fn("luma_hist")(src, hist, np.int32(w), np.int32(h),
                          grid=self._grid(w, h), block=BLOCK)
    return self._get(hist, (BINS,), np.int32)

  def stretch(self, img, lo, hi, vignette=0.0):
    """Contrast stretch between two levels (from the histogram)."""
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    src = self._buf("str_src", shape, np.uint8, img)
    out = self._buf("str_out", shape, np.uint8)
    self._fn("stretch")(src, out, np.int32(w), np.int32(h),
                        np.float32(lo), np.float32(hi),
                        np.float32(vignette),
                        grid=self._grid(w, h), block=BLOCK)
    return self._get(out, shape, np.uint8)

  # -------------------------------------------------------------- helpers
  def _warp(self, img, name, phase, amp, period):
    """Shared launcher of the two distortion kernels."""
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    src = self._buf(f"{name}_src", shape, np.uint8, img)
    out = self._buf(f"{name}_out", shape, np.uint8)
    self._fn(name)(src, out, np.int32(w), np.int32(h), np.float32(phase),
                   np.float32(amp), np.float32(period),
                   grid=self._grid(w, h), block=BLOCK)
    return self._get(out, shape, np.uint8)

  def _splat(self, img, pos, col, size, gain, tag):
    """Particles: splat of every point, then additive blend."""
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    acc = self._buf(f"{tag}_acc", shape, np.float32,
                    np.zeros(shape, np.float32))
    if len(pos) > 0:
      self._splat_points(pos, col, size, gain, acc, w, h, tag)
    return self._add(img, acc, 1.0)

  def _splat_points(self, pos, col, size, gain, acc, w, h, tag):
    """One thread per particle writes its square of light."""
    colour = np.hstack([col, size.reshape(-1, 1)]).astype(np.float32)
    table = self._buf(f"{tag}_tab", colour.shape, np.float32, colour)
    count = int(len(pos))
    self._fn("splat_particles")(
        self._buf(f"{tag}_pos", pos.shape, np.float32, pos), table,
        np.int32(count), acc, np.int32(w), np.int32(h),
        np.float32(gain),
        grid=((count + BLOCK[0] - 1) // BLOCK[0], 1, 1), block=BLOCK1D)

  def _add(self, img, acc, gain):
    """Adds a light buffer to the image (add_light kernel)."""
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    src = self._buf("add_src", shape, np.uint8, img)
    out = self._buf("add_out", shape, np.uint8)
    self._fn("add_light")(src, acc, out, np.int32(w), np.int32(h),
                          np.float32(gain), grid=self._grid(w, h),
                          block=BLOCK)
    return self._get(out, shape, np.uint8)

  # Image primitives (F1).
  def _simple(self, kernel, img, *args):
    """The game allocates device buffers once per shape and reuses them.

    One thread per pixel writes to a separate output buffer. The cache owns
    both device buffers; the probe measures explicit allocation and cleanup.
    """
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    src = self._buf(f"{kernel}_src", shape, np.uint8, img)
    out = self._buf(f"{kernel}_out", shape, np.uint8)
    # Step 3: Run the kernel (kernel<<<grid, block>>>).
    self._fn(kernel)(src, out, np.int32(w), np.int32(h),
                     *[np.float32(a) for a in args],
                     grid=self._grid(w, h), block=BLOCK)
    return self._get(out, shape, np.uint8)

  def gray(self, img):
    """Luma in the three channels."""
    return self._simple("k_gray", img)

  def gray_five_steps(self, img, timer):
    """Teaching probe: run the full cycle instead of reusing game buffers."""
    img = np.ascontiguousarray(img)
    timer.sync = self.driver.Context.synchronize
    buffers = []
    try:
      host = timer.measure('reserve', self._gray_buffers, img, buffers)
      self._gray_roundtrip(img, host, buffers, timer)
    finally:
      # Step 5: Free device memory (cudaFree); Python frees the host copy.
      timer.cleanup(_free_buffers, buffers)
    return host

  def _gray_buffers(self, img, buffers):
    # Step 1: Allocate host and device memory (malloc / cudaMalloc).
    host = np.empty(img.shape, dtype=img.dtype)
    buffers.append(self.driver.mem_alloc(img.nbytes))
    buffers.append(self.driver.mem_alloc(host.nbytes))
    return host

  def _gray_roundtrip(self, img, host, buffers, timer):
    src, out = buffers
    # Step 2: Host-to-device upload (cudaMemcpyHostToDevice).
    timer.measure('upload', self.driver.memcpy_htod, src, img)
    # Step 3: Run the kernel (kernel<<<grid, block>>>).
    timer.measure('kernel', self._launch_gray, self._fn('k_gray'),
                  src, out, img.shape[:2])
    # Step 4: Read the output (cudaMemcpyDeviceToHost).
    timer.measure('download', self.driver.memcpy_dtoh, host, out)

  def _launch_gray(self, k_gray, src, out, shape):
    height, width = shape
    k_gray(src, out, np.int32(width), np.int32(height), block=BLOCK,
           grid=grid_for(width, height))
    self.driver.Context.synchronize()

  def invert(self, img):
    """255 - channel."""
    return self._simple("k_invert", img)

  def gain(self, img, gain):
    """Multiplies every channel (night, auto exposure)."""
    return self._simple("k_gain", img, gain)

  def tint(self, img, rgb):
    """Colour filter per channel."""
    return self._simple("k_tint", img, *rgb)

  def rotate(self, img, angle):
    """Rotation around the centre (neighbour sample)."""
    return self._simple("k_rotate", img, angle)

  def ice(self, img, strength, tint, amount):
    """Ice power: bright edges and blue tint, in two device passes.

    The same default stream orders both passes: the second reads the edges
    and the atomicMax result from global memory before the final download.
    """
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    src = self._buf("ice_src", shape, np.uint8, img)
    edges = self._buf("ice_edges", (h, w), np.float32)
    top = self._buf("ice_top", (1,), np.uint32, np.zeros(1, np.uint32))
    out = self._buf("ice_out", shape, np.uint8)
    self._fn("k_ice_edges")(src, edges, top, np.int32(w), np.int32(h),
                            grid=self._grid(w, h), block=BLOCK)
    self._ice_apply(src, edges, top, out, (w, h), strength, tint, amount)
    return self._get(out, shape, np.uint8)

  def _ice_apply(self, src, edges, top, out, size, strength, tint, amount):
    """Second pass of the ice: the edges over the tinted image."""
    w, h = size
    red, green, blue = (np.float32(c) for c in tint)
    self._fn("k_ice_apply")(src, edges, top, out, np.int32(w), np.int32(h),
                            np.float32(strength), red, green, blue,
                            np.float32(amount), grid=self._grid(w, h),
                            block=BLOCK)

  # -------------------------------------------------- pods and night (F3/F4)
  def spotlights(self, img, lights, ambient, tint, cap=0.0):
    """Light of every lamp (0..1) times the pixel and the warm colour."""
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    src = self._buf("spot_src", shape, np.uint8, img)
    lamps, count = self._lamp_buffer(lights)
    out = self._buf("spot_out", shape, np.uint8)
    red, green, blue = (np.float32(c) for c in tint)
    self._fn("k_spotlights")(src, out, np.int32(w), np.int32(h), lamps,
                             np.int32(count), np.float32(ambient),
                             red, green, blue, np.float32(cap),
                             grid=self._grid(w, h), block=BLOCK)
    return self._get(out, shape, np.uint8)

  def _lamp_buffer(self, lights):
    """Device table of lamps (x, y, radius, power) and their count."""
    table = np.asarray(lights, np.float32).reshape(-1, LAMP_FIELDS)
    count = min(len(table), primitives.SPOT_MAX)
    host = table[:count].reshape(-1) if count else None
    shape = (max(count, 1), LAMP_FIELDS)
    return self._buf("spot_tab", shape, np.float32, host), count

  def heat_distort(self, img, cx, cy, rad, t, amp):
    """Hot air inside a circle of `rad` px around (cx, cy)."""
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    src = self._buf("fire_src", shape, np.uint8, img)
    out = self._buf("fire_out", shape, np.uint8)
    self._fn("k_heat_distort")(src, out, np.int32(w), np.int32(h),
                               np.float32(cx), np.float32(cy),
                               np.float32(rad), np.float32(t),
                               np.float32(amp), grid=self._grid(w, h),
                               block=BLOCK)
    return self._get(out, shape, np.uint8)

  # Animated crowd (F11, FULL only).
  def crowd(self, img, t, side, boost, cfg, pal):
    """Crowd of the stands: seats, people and flags (k_crowd)."""
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    src = self._buf("crowd_src", shape, np.uint8, img)
    out = self._buf("crowd_out", shape, np.uint8)
    table = self._buf("crowd_cfg", (CROWD_CFG,), np.float32,
                      np.asarray(cfg, np.float32))
    colours = self._buf("crowd_pal", (CROWD_PAL,), np.float32,
                        np.asarray(pal, np.float32))
    self._fn("k_crowd")(src, out, np.int32(w), np.int32(h),
                          np.float32(t), np.int32(side),
                          np.float32(boost), table, colours,
                          grid=self._grid(w, h), block=BLOCK)
    return self._get(out, shape, np.uint8)

  def luma_stats(self, img):
    """(mean, p95, top) of the 0..255 luma histogram."""
    h, w = img.shape[:2]
    src = self._buf("lhist_src", (h, w, CHANNELS), np.uint8, img)
    hist = self._buf("lhist_bins", (BINS,), np.uint32,
                     np.zeros(BINS, np.uint32))
    top = self._buf("lhist_top", (1,), np.uint32, np.zeros(1, np.uint32))
    self._fn("k_luma_hist")(src, hist, top, np.int32(w), np.int32(h),
                            grid=self._grid(w, h), block=BLOCK)
    return primitives._stats(self._get(hist, (BINS,), np.uint32),
                             int(self._get(top, (1,), np.uint32)[0]))

  # ----------------------------------------------------- replay (F5)
  def crt(self, img, frame, amount, scan, vignette, noise, rows, tint):
    """Old television: gray, bands, vignette and grain."""
    h, w = img.shape[:2]
    shape = (h, w, CHANNELS)
    src = self._buf("crt_src", shape, np.uint8, img)
    out = self._buf("crt_out", shape, np.uint8)
    red, green, blue = (np.float32(c) for c in tint)
    self._fn("k_crt")(src, out, np.int32(w), np.int32(h),
                      np.int32(frame), np.float32(amount),
                      np.float32(scan), np.float32(vignette),
                      np.float32(noise), np.int32(rows), red, green, blue,
                      grid=self._grid(w, h), block=BLOCK)
    return self._get(out, shape, np.uint8)
