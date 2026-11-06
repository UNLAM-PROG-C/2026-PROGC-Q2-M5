"""Image primitives of phase F1, in numpy.

They are the reference of the `k_*` kernels of `kernels.cu` (gray, invert,
brightness/contrast, gain, tint, rotate, luma, sobel, edge glow) and the
fallback when there is no CUDA. `Cpu` and `Gpu` inherit from this class,
so both have the same API.
"""
import math

import numpy as np

BYTE_MAX = 255.0        # top of the 8 bit range
HALF = 0.5              # rounding and mid gray
LUMA_R = 0.299          # luminance of red (Rec. 601)
LUMA_G = 0.587          # luminance of green
LUMA_B = 0.114          # luminance of blue
SOBEL_SCALE = 0.25      # 1/4: the sobel weights add up to 4
CHANNELS = 3            # interleaved RGB
BINS = 256              # luminance levels of the histogram
SPOT_MAX = 8            # lamps the spotlight kernel walks per pixel
HEAT_FREQ_Y = 0.12      # waves per pixel, vertical (fire)
HEAT_SPEED_Y = 18.0     # rad/s of those waves
HEAT_FREQ_X = 0.09      # waves per pixel, horizontal
HEAT_SPEED_X = 14.0     # rad/s of those waves
HEAT_LATERAL = 0.4      # the horizontal move is smaller
RIPPLE_PI = math.pi     # sine of the shock ring
RIPPLE_GLOW = 60.0      # brightest edge of the ring (0..255)
P95 = 0.95              # percentile reported by `luma_stats`
# F5: the old television of the replay (same numbers as k_crt).
CRT_NOISE_MUL = 2654435761   # multiplier of the noise hash
CRT_NOISE_SHIFT = 24         # high bits used from that hash
CRT_NOISE_MAX = 255.0        # levels of the noise byte
CRT_MASK = 0xFFFFFFFF        # 32 bit wrap of the unsigned hash
CRT_DIAGONAL = 0.70710678    # 1/sqrt(2): brings the vignette to 0..1
CRT_HALF = 0.5               # centre of the grain
CRT_SECOND = 2.0             # the vignette and the bands use a factor 2
CRT_X_MUL = 1973             # hash: weight of x
CRT_Y_MUL = 9277             # hash: weight of y
CRT_FRAME_MUL = 26699        # hash: weight of the frame number


def _rgb(img):
    """0..1 float copy of an RGB uint8 image."""
    return img.astype(np.float32) / BYTE_MAX


def _to_byte(v):
    """0..1 float to uint8, rounding like the kernels do."""
    return np.clip(v * BYTE_MAX + HALF, 0.0, BYTE_MAX).astype(np.uint8)


def _nearest(img, sx, sy):
    """Samples `img` at (sx, sy) with the neighbour; outside is black."""
    h, w = img.shape[:2]
    ix = sx.astype(np.int32)
    iy = sy.astype(np.int32)
    inside = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
    ix = np.clip(ix, 0, w - 1)
    iy = np.clip(iy, 0, h - 1)
    out = img[iy, ix].copy()
    out[~inside] = 0
    return out


def _sample(img, sx, sy):
    """Samples `img` with clipping at the border (no black outside)."""
    h, w = img.shape[:2]
    ix = np.clip(np.trunc(sx).astype(np.int32), 0, w - 1)
    iy = np.clip(np.trunc(sy).astype(np.int32), 0, h - 1)
    return img[iy, ix]


def _ring_sample(img, grid, centre, d, k, inside, amp, y_min):
    """Image read by the shock ring: the pixels the ring moves, clipped."""
    xs, ys = grid
    off = amp * np.sin(RIPPLE_PI * k)
    sx = xs + np.trunc(off * (xs - centre[0]) / (d + 1.0))
    sy = np.maximum(ys + np.trunc(off * (ys - centre[1]) / (d + 1.0)), y_min)
    return _sample(img, np.where(inside, sx, xs), np.where(inside, sy, ys))


def _grid_xy(w, h):
    """Two float32 arrays with the x and the y of every pixel."""
    ys, xs = np.mgrid[0:h, 0:w]
    return xs.astype(np.float32), ys.astype(np.float32)


def _light_field(xs, ys, lights, ambient, cap=0.0):
    """Light 0..1 of each pixel: ambient plus every lamp (kernel formula).

    With `cap` > 0 each lamp adds a share of what is missing, so the sum
    gets close to the cap and never passes it (the night).  Without it the
    sum is the classic one of the blackout, which has no ceiling.
    """
    total = np.full(xs.shape, ambient, np.float32)
    for x, y, radius, power in list(lights)[:SPOT_MAX]:
        d2 = ((xs - x) ** 2 + (ys - y) ** 2) / (radius * radius)
        fall = np.clip(1.0 - d2, 0.0, None)
        add = power * fall * fall
        if cap > 0.0:
            add = add * (cap - total)
        total += add
    return total


def _byte(v):
    """0..255 float to uint8, rounding like the kernels do."""
    return np.clip(v + HALF, 0.0, BYTE_MAX).astype(np.uint8)


def _stats(hist, top):
    """(mean, p95, top) of a 256-bin luma histogram."""
    total = float(hist.sum()) or 1.0
    levels = np.arange(BINS, dtype=np.float64)
    mean = float((levels * hist).sum() / total)
    cumulative = np.cumsum(hist)
    over = np.nonzero(cumulative >= P95 * total)[0]
    return mean, int(over[0]) if len(over) else BINS - 1, int(top)


class Primitives:
    """One method per `k_*` kernel of the F1 group."""
    def gray(self, img):
        """Luma in the three channels."""
        v = _rgb(img) @ np.array([LUMA_R, LUMA_G, LUMA_B], np.float32)
        u = _to_byte(v)
        return np.stack([u, u, u], axis=-1)

    def invert(self, img):
        """255 - channel."""
        return (BYTE_MAX - img.astype(np.int16)).astype(np.uint8)

    def brightness_contrast(self, img, brightness, contrast):
        """(v - 0.5) * contrast + 0.5 + brightness, on 0..1."""
        v = _rgb(img)
        return _to_byte(np.clip((v - HALF) * contrast + HALF + brightness,
                                0.0, 1.0))

    def gain(self, img, gain):
        """Multiplies every channel (night, auto exposure)."""
        return _to_byte(np.clip(_rgb(img) * gain, 0.0, 1.0))

    def tint(self, img, rgb):
        """Multiplies each channel by the colour (0..1)."""
        return _to_byte(_rgb(img) * np.array(rgb, np.float32))

    def rotate(self, img, angle):
        """Rotation around the centre, neighbour sample, outside is black."""
        h, w = img.shape[:2]
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        cx, cy = (w - 1) * HALF, (h - 1) * HALF
        dx, dy = xs - cx, ys - cy
        c, s = math.cos(angle), math.sin(angle)
        sx = cx + c * dx + s * dy + HALF
        sy = cy - s * dx + c * dy + HALF
        return _nearest(img, sx, sy)

    def to_gray(self, img):
        """Luma as float 0..1 (input of sobel and of the histogram)."""
        return _rgb(img) @ np.array([LUMA_R, LUMA_G, LUMA_B], np.float32)

    def sobel(self, gray):
        """Gradient magnitude of the image (edges)."""
        pad = np.pad(gray, 1, mode="edge")
        a, b, c = pad[:-2, :-2], pad[:-2, 1:-1], pad[:-2, 2:]
        d, f = pad[1:-1, :-2], pad[1:-1, 2:]
        g, hh, k = pad[2:, :-2], pad[2:, 1:-1], pad[2:, 2:]
        gx = (c + 2.0 * f + k) - (a + 2.0 * d + g)
        gy = (g + 2.0 * hh + k) - (a + 2.0 * b + c)
        return np.sqrt(gx * gx + gy * gy) * SOBEL_SCALE

    def sobel_normalize(self, edges, max_value=None):
        """Edges to 0..255 over the whole image, in the three channels."""
        top = max_value if max_value else float(edges.max() or 1.0)
        u = _to_byte(np.clip(edges / top, 0.0, 1.0))
        return np.stack([u, u, u], axis=-1)

    def edge_glow(self, img, edges, strength):
        """Adds the bright edges to the original image."""
        v = _rgb(img) + _rgb(edges) * strength
        return _to_byte(np.clip(v, 0.0, 1.0))

    def ice(self, img, strength, tint, amount):
        """Ice power: bright edges, then a blue tint weighted by `amount`.

        It is the same chain the GPU does in two passes, here with numpy.
        """
        edges = self.sobel_normalize(self.sobel(self.to_gray(img)))
        out = self.edge_glow(img, edges, strength)
        blue = self.tint(out, tint)
        mixed = _rgb(out) * (1.0 - amount) + _rgb(blue) * amount
        return _to_byte(np.clip(mixed, 0.0, 1.0))

    # ------------------------------------------------ pods and night (F3/F4)
    def spotlights(self, img, lights, ambient, tint, cap=0.0):
        """Multiplies the light of every lamp (0..1) and the warm colour.

        `cap` > 0 is the night: the lamps add up towards the cap and never
        pass it, so the brightest pixel of the frame stays below the day.
        """
        h, w = img.shape[:2]
        xs, ys = _grid_xy(w, h)
        light = _light_field(xs, ys, lights, ambient, cap)
        colour = np.array(tint, np.float32)
        return _to_byte(np.clip(_rgb(img) * light[..., None] * colour,
                                0.0, 1.0))

    def heat_distort(self, img, cx, cy, rad, t, amp):
        """Hot air in a circle: the pixels inside read from a moved place."""
        h, w = img.shape[:2]
        xs, ys = _grid_xy(w, h)
        dx, dy = xs - cx, ys - cy
        d = np.sqrt(dx * dx + dy * dy)
        fall = np.clip(1.0 - d / rad, 0.0, None)
        sx = xs + np.trunc(amp * np.sin(ys * HEAT_FREQ_Y + t * HEAT_SPEED_Y)
                           * fall).astype(np.float32)
        sy = ys + np.trunc(amp * HEAT_LATERAL
                           * np.sin(xs * HEAT_FREQ_X + t * HEAT_SPEED_X)
                           * fall).astype(np.float32)
        inside = d < rad
        return _sample(img, np.where(inside, sx, xs), np.where(inside, sy, ys))

    def ripple_ring(self, img, cx, cy, radius, width, amp, y_min=0.0):
        """Expanding ring of the goal: warp plus a bright edge.

        Rows above `y_min` (the stands and the boards) come back untouched.
        """
        xs, ys = _grid_xy(img.shape[1], img.shape[0])
        d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
        k = (d - radius) / (width if width > 0 else 1.0)
        inside = (k > -1.0) & (k < 1.0)
        v = _ring_sample(img, (xs, ys), (cx, cy), d, k, inside, amp, y_min)
        glow = np.where(inside, RIPPLE_GLOW * (1.0 - np.abs(k)), 0.0)
        out = _byte(v + glow[..., None])
        out[:int(y_min)] = img[:int(y_min)]
        return out

    def trail_blend(self, cur, prev, decay):
        """Pixel-wise maximum of the frame and the decayed previous one."""
        v = np.maximum(cur.astype(np.float32),
                       prev.astype(np.float32) * decay)
        return _byte(v)

    def luma_stats(self, img):
        """(mean, p95, top) of the 0..255 luma histogram."""
        return _stats(*self._luma_hist(img))

    # ------------------------------------------ replay: old television (F5)
    def crt(self, img, frame, amount, scan, vignette, noise, rows, tint):
        """Gray, bands, vignette and grain: the old TV of the replay."""
        h, w = img.shape[:2]
        xs, ys = _grid_xy(w, h)
        luma = self.to_gray(img)
        band = self._crt_bands(ys, scan, rows)
        vig = self._crt_vignette(xs, ys, vignette)
        grain = self._crt_grain(xs, ys, frame)
        look = luma * band * vig + grain * noise
        v = luma + (look - luma) * amount
        return _to_byte(np.clip(v[..., None] * np.array(tint, np.float32),
                                0.0, 1.0))

    def _crt_bands(self, ys, scan, rows):
        """One darker line every `rows` rows (the sweep of the tube)."""
        if rows <= 0:
            return np.ones(ys.shape, np.float32)
        dark = (ys.astype(np.int32) % rows) == rows - 1
        return np.where(dark, 1.0 - scan, 1.0).astype(np.float32)

    def _crt_vignette(self, xs, ys, amount):
        """Radial darkening: 0 in the centre and 1 in the corners."""
        h, w = ys.shape
        nx = CRT_SECOND * xs / float(max(w - 1, 1)) - 1.0
        ny = CRT_SECOND * ys / float(max(h - 1, 1)) - 1.0
        d = np.sqrt(nx * nx + ny * ny) * CRT_DIAGONAL
        return (1.0 - amount * d * d).astype(np.float32)

    def _crt_grain(self, xs, ys, frame):
        """Grain of (x, y, frame) with the same hash as `k_crt`."""
        base = (xs.astype(np.int64) * CRT_X_MUL
                + ys.astype(np.int64) * CRT_Y_MUL + int(frame) * CRT_FRAME_MUL)
        seed = (base * CRT_NOISE_MUL) & CRT_MASK
        byte = (seed >> CRT_NOISE_SHIFT) & int(CRT_NOISE_MAX)
        return byte.astype(np.float32) / CRT_NOISE_MAX - CRT_HALF

    def _luma_hist(self, img):
        """256 bins of luma and its top level (same rounding as k_gray)."""
        v = self.to_gray(img) * BYTE_MAX + HALF
        bins = np.clip(v.astype(np.int32), 0, BINS - 1)
        return np.bincount(bins.ravel(), minlength=BINS), int(bins.max())

