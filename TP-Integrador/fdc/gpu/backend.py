"""GPU implementation of the effects chain (PyCUDA).

Every operation is one or more kernels of `kernels.cu`: one thread per
pixel, 2D index, border check, global memory only and atomics when two
threads write the same pixel. The images travel as numpy arrays (RGB uint8,
shape h x w x 3) and the intermediate light buffers as float32.

`fdc.gpu.cpu_ref.Cpu` has the same methods with numpy, so the tests compare
both and the game falls back to the CPU when there is no CUDA.
"""
import os

import numpy as np

CHANNELS = 3                    # interleaved RGB
BINS = 256                      # luminance levels of the histogram
BLOCK = (32, 8, 1)              # threads per block (2D: x wide, y tall)
BLOCK1D = (32, 1, 1)            # for the kernels with one index (particles)
COMPILER_OPTIONS = ["-std=c++17", "--use_fast_math"]
DEFAULT_ARCH = "sm_120"         # RTX 50 series; it is detected at runtime
KERNEL_FILE = "kernels.cu"      # the CUDA source, next to this module
MIN_ALLOC = 4                   # bytes: CUDA does not allocate 0
FALLBACK_CC = (12, 0)           # compute capability if it cannot be read


def kernel_path():
    """Absolute path of the CUDA source."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        KERNEL_FILE)


def kernel_source():
    """The CUDA source as a string (read once per call: it is small)."""
    with open(kernel_path(), encoding="utf-8") as fh:
        return fh.read()


def available():
    """True if PyCUDA and the driver work here (the context is created)."""
    try:
        import pycuda.autoinit     # pylint: disable=unused-import
    except Exception:              # pylint: disable=broad-except
        return False
    return True


def device_name():
    """Name of the GPU, or 'CPU' when there is none."""
    if not available():
        return "CPU"
    import pycuda.driver as drv
    return drv.Device(0).name()


def _auto_arch(driver):
    """'sm_XY' of the first device (the one PyCUDA uses)."""
    try:
        major, minor = driver.Device(0).compute_capability()
    except Exception:              # pylint: disable=broad-except
        major, minor = FALLBACK_CC
    return f"sm_{major}{minor}"


class Gpu:
    """The kernels of `kernels.cu`, wrapped as numpy in / numpy out."""

    def __init__(self, arch=None):
        import pycuda.autoinit     # pylint: disable=unused-import
        import pycuda.compiler
        import pycuda.driver as drv
        self.driver = drv
        self.arch = arch or _auto_arch(drv)
        self.module = pycuda.compiler.SourceModule(
            kernel_source(), arch=self.arch, options=COMPILER_OPTIONS)
        self._fns = {}
        self._buffers = {}

    # ------------------------------------------------------------- plumbing
    def _fn(self, name):
        """Kernel function, taken from the module the first time."""
        if name not in self._fns:
            self._fns[name] = self.module.get_function(name)
        return self._fns[name]

    def _buf(self, name, shape, dtype, host=None):
        """Device buffer (allocated once per name and shape)."""
        key = (name, tuple(shape), np.dtype(dtype).str)
        buf = self._buffers.get(key)
        if buf is None:
            size = max(int(np.prod(shape)) * np.dtype(dtype).itemsize,
                       MIN_ALLOC)
            buf = self.driver.mem_alloc(size)
            self._buffers[key] = buf
        if host is not None:
            self.driver.memcpy_htod(buf, np.ascontiguousarray(host))
        return buf

    def _get(self, dev, shape, dtype):
        """Copies a device buffer back to the host."""
        host = np.empty(shape, dtype=dtype)
        self.driver.memcpy_dtoh(host, dev)
        return host

    def _grid(self, w, h):
        """2D grid that covers a w x h image with BLOCK threads per block."""
        return ((w + BLOCK[0] - 1) // BLOCK[0],
                (h + BLOCK[1] - 1) // BLOCK[1])

    # --------------------------------------------------------------- images
    def blur(self, img, radius):
        """Separable box blur of an RGB image (radius in pixels)."""
        h, w = img.shape[:2]
        shape = (h, w, CHANNELS)
        src = self._buf("blur_src", shape, np.uint8, img)
        tmp = self._buf("blur_tmp", shape, np.uint8)
        out = self._buf("blur_out", shape, np.uint8)
        grid = self._grid(w, h)
        size = (np.int32(w), np.int32(h), np.int32(radius))
        self._fn("blur_rows")(src, tmp, *size, grid=grid, block=BLOCK)
        self._fn("blur_cols")(tmp, out, *size, grid=grid, block=BLOCK)
        return self._get(out, shape, np.uint8)

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

    def lights(self, img, lights, gain):
        """Additive spotlights: x, y, radius, power, r, g, b."""
        h, w = img.shape[:2]
        if len(lights) == 0:
            return img.copy()
        shape = (h, w, CHANNELS)
        acc = self._buf("light_acc", shape, np.float32,
                        np.zeros(shape, np.float32))
        table = self._buf("light_tab", lights.shape, np.float32, lights)
        count = np.int32(len(lights))
        self._fn("splat_lights")(table, count, acc, np.int32(w), np.int32(h),
                                 np.float32(gain),
                                 grid=((len(lights) + BLOCK[0] - 1)
                                       // BLOCK[0], 1, 1), block=BLOCK1D)
        return self._add(img, acc, 1.0)

    def heat(self, img, phase, amp, period):
        """Heat waves: each pixel reads from a shifted place."""
        return self._warp(img, "heat_distort", phase, amp, period)

    def ripple(self, img, phase, amp, period):
        """Concentric waves, used by the replay screen."""
        return self._warp(img, "ripple", phase, amp, period)

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

    def trail(self, cur, prev, alpha):
        """Blend the previous frame into the current one."""
        h, w = cur.shape[:2]
        shape = (h, w, CHANNELS)
        now = self._buf("trail_cur", shape, np.uint8, cur)
        before = self._buf("trail_prev", shape, np.uint8, prev)
        out = self._buf("trail_out", shape, np.uint8)
        self._fn("trail")(now, before, out, np.int32(w), np.int32(h),
                          np.float32(alpha), grid=self._grid(w, h),
                          block=BLOCK)
        return self._get(out, shape, np.uint8), self._get(before, shape,
                                                          np.uint8)

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

    def stretch(self, img, lo, hi):
        """Contrast stretch between two levels (from the histogram)."""
        h, w = img.shape[:2]
        shape = (h, w, CHANNELS)
        src = self._buf("str_src", shape, np.uint8, img)
        out = self._buf("str_out", shape, np.uint8)
        self._fn("stretch")(src, out, np.int32(w), np.int32(h),
                            np.float32(lo), np.float32(hi),
                            grid=self._grid(w, h), block=BLOCK)
        return self._get(out, shape, np.uint8)

    def minimap(self, img, cols, rows):
        """Average of each block, as a float grid (rows, cols, 3)."""
        h, w = img.shape[:2]
        src = self._buf("mini_src", (h, w, CHANNELS), np.uint8, img)
        grid = self._buf("mini_grid", (rows, cols, CHANNELS), np.float32,
                         np.zeros((rows, cols, CHANNELS), np.float32))
        self._fn("minimap")(src, grid, np.int32(w), np.int32(h),
                            np.int32(cols), np.int32(rows),
                            grid=self._grid(cols, rows), block=BLOCK)
        return self._get(grid, (rows, cols, CHANNELS), np.float32)

    def heat_colors(self, heat, max_value):
        """Blue -> green -> yellow -> red ramp over the grid."""
        rows, cols = heat.shape
        src = self._buf("heat_in", (rows, cols), np.float32, heat)
        out = self._buf("heat_out", (rows, cols, CHANNELS), np.uint8)
        count = int(rows * cols)
        self._fn("heat_colors")(src, out, np.int32(count),
                                np.float32(max_value),
                                grid=((count + BLOCK[0] - 1) // BLOCK[0],
                                      1, 1), block=BLOCK1D)
        return self._get(out, (rows, cols, CHANNELS), np.uint8)

    def heat_splat(self, pos, heat, amount):
        """Accumulate points (col, row) into the grid, in place."""
        rows, cols = heat.shape
        grid = self._buf("heat_acc", (rows, cols), np.float32, heat)
        table = self._buf("heat_pos", pos.shape, np.float32, pos)
        count = int(len(pos))
        if count > 0:
            self._fn("heat_splat")(table, np.int32(count), grid,
                                   np.int32(cols), np.int32(rows),
                                   np.float32(amount),
                                   grid=((count + BLOCK[0] - 1) // BLOCK[0],
                                         1, 1), block=BLOCK1D)
        return self._get(grid, (rows, cols), np.float32)

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
