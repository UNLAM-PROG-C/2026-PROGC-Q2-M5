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

from fdc.gpu import primitives

CHANNELS = 3                    # interleaved RGB
BINS = 256                      # luminance levels of the histogram
BLOCK = (32, 8, 1)              # threads per block (2D: x wide, y tall)
BLOCK1D = (32, 1, 1)            # for the kernels with one index (particles)
COMPILER_OPTIONS = ["-std=c++17", "--use_fast_math"]
DEFAULT_ARCH = "sm_120"         # RTX 50 series; it is detected at runtime
KERNEL_FILE = "kernels.cu"      # the CUDA source, next to this module
MIN_ALLOC = 4                   # bytes: CUDA does not allocate 0
LAMP_FIELDS = 4                 # x, y, radius and power of one lamp
FALLBACK_CC = (12, 0)           # compute capability if it cannot be read
POINT_FIELDS = 2                # x and y of one heat map point
CROWD_CFG = 24                  # parameters of the crowd kernel
CROWD_PAL = 48                  # colours of the crowd kernel (16 rgb triplets)


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


class Gpu(primitives.Primitives):
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

    def lights(self, img, lights, gain):
        """Additive spotlights: x, y, radius, power, r, g, b."""
        h, w = img.shape[:2]
        if len(lights) == 0:
            return img.copy()
        shape = (h, w, CHANNELS)
        src = self._buf("light_src", shape, np.uint8, img)
        table = self._buf("light_tab", lights.shape, np.float32, lights)
        out = self._buf("light_out", shape, np.uint8)
        self._fn("k_light_pixels")(src, out, table, np.int32(len(lights)),
                                   np.int32(w), np.int32(h), np.float32(gain),
                                   grid=self._grid(w, h), block=BLOCK)
        return self._get(out, shape, np.uint8)

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

    # ------------------------------------------------------- primitivas (F1)
    def _simple(self, kernel, img, *args):
        """One in, one out image kernel: upload, launch, download."""
        h, w = img.shape[:2]
        shape = (h, w, CHANNELS)
        src = self._buf(f"{kernel}_src", shape, np.uint8, img)
        out = self._buf(f"{kernel}_out", shape, np.uint8)
        self._fn(kernel)(src, out, np.int32(w), np.int32(h),
                         *[np.float32(a) for a in args],
                         grid=self._grid(w, h), block=BLOCK)
        return self._get(out, shape, np.uint8)

    def gray(self, img):
        """Luma in the three channels."""
        return self._simple("k_gray", img)

    def invert(self, img):
        """255 - channel."""
        return self._simple("k_invert", img)

    def brightness_contrast(self, img, brightness, contrast):
        """Brightness and contrast around the mid gray."""
        return self._simple("k_brightness_contrast", img, brightness,
                            contrast)

    def gain(self, img, gain):
        """Multiplies every channel (night, auto exposure)."""
        return self._simple("k_gain", img, gain)

    def tint(self, img, rgb):
        """Colour filter per channel."""
        return self._simple("k_tint", img, *rgb)

    def rotate(self, img, angle):
        """Rotation around the centre (neighbour sample)."""
        return self._simple("k_rotate", img, angle)

    def to_gray(self, img):
        """Luma as float 0..1."""
        h, w = img.shape[:2]
        shape = (h, w, CHANNELS)
        src = self._buf("tog_src", shape, np.uint8, img)
        out = self._buf("tog_out", (h, w), np.float32)
        self._fn("k_to_gray_f32")(src, out, np.int32(w), np.int32(h),
                                  grid=self._grid(w, h), block=BLOCK)
        return self._get(out, (h, w), np.float32)

    def sobel(self, gray):
        """Gradient magnitude (edges)."""
        h, w = gray.shape[:2]
        src = self._buf("sob_src", (h, w), np.float32, gray)
        out = self._buf("sob_out", (h, w), np.float32)
        self._fn("k_sobel")(src, out, np.int32(w), np.int32(h),
                            grid=self._grid(w, h), block=BLOCK)
        return self._get(out, (h, w), np.float32)

    def sobel_normalize(self, edges, max_value=None):
        """Edges to 0..255 over the whole image."""
        h, w = edges.shape[:2]
        top = max_value if max_value else float(edges.max() or 1.0)
        shape = (h, w, CHANNELS)
        src = self._buf("sobn_src", (h, w), np.float32, edges)
        out = self._buf("sobn_out", shape, np.uint8)
        self._fn("k_sobel_normalize")(src, out, np.int32(w), np.int32(h),
                                      np.float32(top), grid=self._grid(w, h),
                                      block=BLOCK)
        return self._get(out, shape, np.uint8)

    def edge_glow(self, img, edges, strength):
        """Adds the bright edges to the original image."""
        h, w = img.shape[:2]
        shape = (h, w, CHANNELS)
        src = self._buf("eg_src", shape, np.uint8, img)
        edg = self._buf("eg_edg", shape, np.uint8, edges)
        out = self._buf("eg_out", shape, np.uint8)
        self._fn("k_edge_glow")(src, edg, out, np.int32(w), np.int32(h),
                                np.float32(strength), grid=self._grid(w, h),
                                block=BLOCK)
        return self._get(out, shape, np.uint8)

    def ice(self, img, strength, tint, amount):
        """Ice power: bright edges and blue tint, in two device passes.

        The whole path stays on the board: the edges are normalised with the
        maximum that `atomicMax` leaves in `ice_top`, so the image travels up
        and down only once (before it was six round trips).
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
    def spotlights(self, img, lights, ambient, tint):
        """Light of every lamp (0..1) times the pixel and the warm colour."""
        h, w = img.shape[:2]
        shape = (h, w, CHANNELS)
        src = self._buf("spot_src", shape, np.uint8, img)
        lamps, count = self._lamp_buffer(lights)
        out = self._buf("spot_out", shape, np.uint8)
        red, green, blue = (np.float32(c) for c in tint)
        self._fn("k_spotlights")(src, out, np.int32(w), np.int32(h), lamps,
                                 np.int32(count), np.float32(ambient),
                                 red, green, blue, grid=self._grid(w, h),
                                 block=BLOCK)
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

    def ripple_ring(self, img, cx, cy, radius, width, amp):
        """Expanding ring of the goal: warp plus bright edge."""
        h, w = img.shape[:2]
        shape = (h, w, CHANNELS)
        src = self._buf("ring_src", shape, np.uint8, img)
        out = self._buf("ring_out", shape, np.uint8)
        self._fn("k_ripple")(src, out, np.int32(w), np.int32(h),
                             np.float32(cx), np.float32(cy),
                             np.float32(radius), np.float32(width),
                             np.float32(amp), grid=self._grid(w, h),
                             block=BLOCK)
        return self._get(out, shape, np.uint8)

    def trail_blend(self, cur, prev, decay):
        """Maximum of the frame and the decayed previous one (no ghosts)."""
        h, w = cur.shape[:2]
        shape = (h, w, CHANNELS)
        now = self._buf("tbl_cur", shape, np.uint8, cur)
        before = self._buf("tbl_prev", shape, np.uint8, prev)
        out = self._buf("tbl_out", shape, np.uint8)
        self._fn("k_trail_blend")(now, before, out, np.int32(w), np.int32(h),
                                  np.float32(decay), grid=self._grid(w, h),
                                  block=BLOCK)
        return self._get(out, shape, np.uint8)

    # --------------------------------------- tribuna animada (F11, solo FULL)
    def tribuna(self, img, t, side, boost, cfg, pal):
        """Crowd of the stands: seats, people and flags (k_tribuna)."""
        h, w = img.shape[:2]
        shape = (h, w, CHANNELS)
        src = self._buf("crowd_src", shape, np.uint8, img)
        out = self._buf("crowd_out", shape, np.uint8)
        table = self._buf("crowd_cfg", (CROWD_CFG,), np.float32,
                          np.asarray(cfg, np.float32))
        colours = self._buf("crowd_pal", (CROWD_PAL,), np.float32,
                            np.asarray(pal, np.float32))
        self._fn("k_tribuna")(src, out, np.int32(w), np.int32(h),
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

    # ----------------------------------------------------- replay and VAR (F5)
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

    # ------------------------------------------- heat map of the match (F6)
    def heat_reset(self, cols, rows):
        """Starts an empty heat map on the device (no trip to the host)."""
        shape = (CHANNELS, rows, cols)
        self._buf("heat_grids", shape, np.uint32,
                  np.zeros(shape, np.uint32))
        self._buf("heat_max", (CHANNELS,), np.uint32,
                  np.zeros(CHANNELS, np.uint32))

    def heat_accumulate(self, channel, points, cols, rows, cell_w, cell_h):
        """Adds every (x, y) point of a channel to its cell (atomicAdd)."""
        pts = np.asarray(points, np.float32).reshape(-1, POINT_FIELDS)
        if len(pts) == 0:
            return
        table = self._point_buffer(pts)
        grids = self._buf("heat_grids", (CHANNELS, rows, cols), np.uint32)
        maxes = self._buf("heat_max", (CHANNELS,), np.uint32)
        blocks = max(1, (len(pts) + BLOCK[0] - 1) // BLOCK[0])
        self._fn("k_heat_accumulate")(table, np.int32(len(pts)),
                                      np.int32(channel), np.int32(cols),
                                      np.int32(rows), np.float32(cell_w),
                                      np.float32(cell_h), grids, maxes,
                                      grid=(blocks, 1, 1), block=BLOCK1D)

    def heat_download(self, cols, rows):
        """Copies the grid and the maximums back (the only DtoH of F6)."""
        if not any(key[0] == "heat_grids" for key in self._buffers):
            return (np.zeros((CHANNELS, rows, cols), np.uint32),
                    np.zeros(CHANNELS, np.uint32))
        grids = self._buf("heat_grids", (CHANNELS, rows, cols), np.uint32)
        maxes = self._buf("heat_max", (CHANNELS,), np.uint32)
        return (self._get(grids, (CHANNELS, rows, cols), np.uint32),
                self._get(maxes, (CHANNELS,), np.uint32))

    def heat_render(self, img, grids, maxes, cols, rows, channel, alpha, gain):
        """Draws the grid of a channel over the image (ramp and mix)."""
        shape = img.shape
        src = self._buf("heat_src", shape, np.uint8, img.reshape(-1))
        maps = self._heat_map(grids, maxes, rows, cols)
        out = self._buf("heat_out", shape, np.uint8)
        self._fn("k_heat_render")(src, *maps, out, np.int32(shape[1]),
                                  np.int32(shape[0]), np.int32(cols),
                                  np.int32(rows), np.int32(channel),
                                  np.float32(alpha), np.float32(gain),
                                  grid=self._grid(shape[1], shape[0]),
                                  block=BLOCK)
        return self._get(out, shape, np.uint8)

    def _heat_map(self, grids, maxes, rows, cols):
        """Device copies of the grid of the match and of its maximums."""
        gbuf = self._buf("heat_g", (CHANNELS, rows, cols), np.uint32,
                         np.ascontiguousarray(grids, np.uint32))
        mbuf = self._buf("heat_m", (CHANNELS,), np.uint32,
                         np.ascontiguousarray(maxes, np.uint32))
        return gbuf, mbuf

    def _point_buffer(self, pts):
        """Device table of points (always at least one row)."""
        shape = (max(len(pts), 1), POINT_FIELDS)
        host = pts if len(pts) else np.zeros(shape, np.float32)
        return self._buf("heat_pts", shape, np.float32, host)
