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
