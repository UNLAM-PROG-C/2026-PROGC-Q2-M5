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


def _grid_xy(w, h):
    """Two float32 arrays with the x and the y of every pixel."""
    ys, xs = np.mgrid[0:h, 0:w]
    return xs.astype(np.float32), ys.astype(np.float32)


def _light_field(xs, ys, lights, ambient):
    """Light 0..1 of each pixel: ambient plus every lamp (kernel formula)."""
    total = np.full(xs.shape, ambient, np.float32)
    for x, y, radius, power in list(lights)[:SPOT_MAX]:
        d2 = ((xs - x) ** 2 + (ys - y) ** 2) / (radius * radius)
        fall = np.clip(1.0 - d2, 0.0, None)
        total += power * fall * fall
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

    # ------------------------------------------------ pods and night (F3/F4)
    def spotlights(self, img, lights, ambient, tint):
        """Multiplies the light of every lamp (0..1) and the warm colour."""
        h, w = img.shape[:2]
        xs, ys = _grid_xy(w, h)
        light = _light_field(xs, ys, lights, ambient)
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

    def ripple_ring(self, img, cx, cy, radius, width, amp):
        """Expanding ring of the goal: warp plus a bright edge."""
        h, w = img.shape[:2]
        xs, ys = _grid_xy(w, h)
        dx, dy = xs - cx, ys - cy
        d = np.sqrt(dx * dx + dy * dy)
        k = (d - radius) / (width if width > 0 else 1.0)
        inside = (k > -1.0) & (k < 1.0)
        off = amp * np.sin(RIPPLE_PI * k)
        sx = xs + np.trunc(off * dx / (d + 1.0)).astype(np.float32)
        sy = ys + np.trunc(off * dy / (d + 1.0)).astype(np.float32)
        glow = np.where(inside, RIPPLE_GLOW * (1.0 - np.abs(k)), 0.0)
        v = _sample(img, np.where(inside, sx, xs),
                    np.where(inside, sy, ys)).astype(np.float32)
        return _byte(v + glow[..., None])

    def trail_blend(self, cur, prev, decay):
        """Pixel-wise maximum of the frame and the decayed previous one."""
        v = np.maximum(cur.astype(np.float32),
                       prev.astype(np.float32) * decay)
        return _byte(v)

    def luma_stats(self, img):
        """(mean, p95, top) of the 0..255 luma histogram."""
        return _stats(*self._luma_hist(img))

    def _luma_hist(self, img):
        """256 bins of luma and its top level (same rounding as k_gray)."""
        v = self.to_gray(img) * BYTE_MAX + HALF
        bins = np.clip(v.astype(np.int32), 0, BINS - 1)
        return np.bincount(bins.ravel(), minlength=BINS), int(bins.max())

