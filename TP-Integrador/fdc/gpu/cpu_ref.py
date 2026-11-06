"""CPU (numpy) reference of every GPU kernel of the effects chain.

It has exactly the same API as fdc.gpu.backend.Gpu, so the tests can run
both and compare, and the game can fall back to this version when there is
no CUDA. Numpy is only imported here (the game works without it).
"""
import numpy as np

from fdc.gpu import primitives

CHANNELS = 3            # interleaved RGB
BYTE_MAX = 255.0        # top of the 8 bit range
HALF = 0.5              # used to build the vignette and the heat ramp
LUMA_R, LUMA_G, LUMA_B = 0.299, 0.587, 0.114   # luminance (Rec. 601)
EPS = 1e-6              # smallest divisor (never divide by zero)
RAMP_LOW = 0.25         # heat ramp: where the green reaches the top
RAMP_MID = 0.75         # heat ramp: where the red starts to go down
RAMP_SLOPE = 4.0        # heat ramp: slope of the green and red
SQRT2 = 1.41421356      # diagonal of the unit square (vignette)
MEAN_AXES = (1, 3)      # block axes of the minimap reshape
HEAT_FIELDS = 2         # x and y of a recorded point
GRID_MIN = 1e-6         # smallest cell size (never divide by zero)
ONE_COUNT = 1           # each point counts once (atomicAdd of 1 in the GPU)


def _rgb(img):
    return img.astype(np.float32) / BYTE_MAX


def _clamp(img):
    return np.clip(img * BYTE_MAX, 0.0, BYTE_MAX).astype(np.uint8)


def _box_axis(img, radius, axis):
    """Mean of the existing samples of [i-radius, i+radius] (clamped)."""
    if radius <= 0:
        return img.astype(np.float32)
    acc = np.zeros(img.shape, dtype=np.float32)
    count = _sample_count(img.shape[axis], radius, axis, img.ndim)
    _accumulate(img, acc, radius, axis)
    return acc / count


def _sample_count(size, radius, axis, dims):
    """How many samples each index has (the borders have fewer)."""
    count = np.zeros(size, dtype=np.float32)
    base = np.arange(size)
    for k in range(-radius, radius + 1):
        index = base + k
        count += (index >= 0) & (index < size)
    shape = [1] * dims
    shape[axis] = size
    return count.reshape(shape)


def _accumulate(img, acc, radius, axis):
    """Sums the window of every index (repeating the border sample)."""
    size = img.shape[axis]
    base = np.arange(size)
    shape = [1] * img.ndim
    shape[axis] = size
    for k in range(-radius, radius + 1):
        index = base + k
        valid = ((index >= 0) & (index < size)).astype(np.float32)
        acc += np.take(img, np.clip(index, 0, size - 1), axis=axis) \
            * valid.reshape(shape)


class Cpu(primitives.Primitives):
    """Numpy version of the effects (same methods and shapes as Gpu)."""

    def __init__(self):
        # Heat map of the match (F6): empty until the first heat_reset.
        self.heat_grids = np.zeros((CHANNELS, 1, 1), np.uint32)
        self.heat_max = np.zeros(CHANNELS, np.uint32)

    def blur(self, img, radius):
        """Separable box blur, with the same 8 bit rounding as the kernel."""
        tmp = np.clip(_box_axis(img, radius, 1), 0, BYTE_MAX).astype(np.uint8)
        out = np.clip(_box_axis(tmp, radius, 0), 0, BYTE_MAX)
        return out.astype(np.uint8)

    def glow(self, img, threshold, radius, passes):
        """Bright pass at half resolution, then `passes` box blurs."""
        small = img[::2, ::2].astype(np.float32) / BYTE_MAX
        luma = (LUMA_R * small[..., 0] + LUMA_G * small[..., 1]
                + LUMA_B * small[..., 2])
        span = max(1.0 - threshold, EPS)
        over = np.clip((luma - threshold) / span, 0.0, 1.0)
        field = small * over[..., None]
        for _ in range(passes):
            field = _box_axis(field, radius, 1)
            field = _box_axis(field, radius, 0)
        return field.astype(np.float32)

    def composite(self, img, glow, exposure, gamma, vignette, strength):
        """Exposure, glow, gamma and vignette."""
        h, w = img.shape[:2]
        base = _rgb(img) * exposure
        big = np.repeat(np.repeat(glow, 2, axis=0), 2, axis=1)[:h, :w]
        if big.shape[:2] != (h, w):
            pad = ((0, h - big.shape[0]), (0, w - big.shape[1]), (0, 0))
            big = np.pad(big, pad, mode="edge")
        value = base + big * strength
        out = np.power(np.maximum(value, 0.0), gamma)
        out = out * _vignette(h, w, vignette)[..., None]
        return _clamp(np.minimum(out, 1.0))

    def glow_composite(self, img, threshold, radius, passes, params):
        """Same result as glow + composite, in one call."""
        field = self.glow(img, threshold, radius, passes)
        return self.composite(img, field, *params)

    def particles(self, img, pos, col, gain):
        """Additive glowing particles: pos (n,2), col (n,4) r,g,b,size."""
        return self._splat(img, pos, col[:, :CHANNELS] * gain, col[:, CHANNELS],
                           gain)

    def lights(self, img, lights, gain):
        """Additive spotlights: x, y, radius, power, r, g, b."""
        h, w = img.shape[:2]
        acc = np.zeros((h, w, CHANNELS), dtype=np.float32)
        for light in lights:
            acc += _light_layer(light, h, w, gain)
        return _clamp(_rgb(img) + acc)

    def heat(self, img, phase, amp, period):
        """Heat waves: each pixel reads from a shifted place."""
        return _warp(img, "heat", phase, amp, period)

    def ripple(self, img, phase, amp, period):
        """Concentric waves (the replay screen)."""
        return _warp(img, "ripple", phase, amp, period)

    def mix(self, a, b, alpha):
        """Linear mix: alpha 0 keeps `a`, alpha 1 keeps `b`."""
        return _clamp(_rgb(a) * (1.0 - alpha) + _rgb(b) * alpha)

    def trail(self, cur, prev, alpha):
        """Blend the previous frame into the current one."""
        out = _clamp(_rgb(cur) * (1.0 - alpha) + _rgb(prev) * alpha)
        return out, out.copy()

    def histogram(self, img):
        """256 bins of luminance (same scale as the kernel)."""
        weights = np.array([LUMA_R, LUMA_G, LUMA_B], np.float32)
        luma = img.astype(np.float32) @ weights
        bins = np.clip(luma.astype(np.int32), 0, int(BYTE_MAX))
        return np.bincount(bins.ravel(),
                           minlength=int(BYTE_MAX) + 1).astype(np.int32)

    def stretch(self, img, lo, hi):
        """Contrast stretch between two levels."""
        span = max(hi - lo, 1.0)
        return _clamp(np.clip((img.astype(np.float32) - lo) / span, 0.0, 1.0))

    def minimap(self, img, cols, rows):
        """Average of each block, as a float grid (rows, cols, 3)."""
        h, w = img.shape[:2]
        bw, bh = max(w // cols, 1), max(h // rows, 1)
        crop = img[:bh * rows, :bw * cols].astype(np.float32)
        crop = crop.reshape(rows, bh, cols, bw, CHANNELS).mean(axis=MEAN_AXES)
        return crop / BYTE_MAX

    def heat_colors(self, heat, max_value):
        """Blue -> green -> yellow -> red ramp over the grid."""
        v = np.clip(heat / max(max_value, EPS), 0.0, 1.0)
        r = np.clip((v - HALF) * 2.0, 0.0, 1.0)
        g = np.where(v < RAMP_LOW, v * RAMP_SLOPE,
                     np.where(v < RAMP_MID, 1.0, (1.0 - v) * RAMP_SLOPE))
        b = np.clip((HALF - v) * 2.0, 0.0, 1.0)
        return _clamp(np.stack([r, g, b], axis=-1))

    def heat_splat(self, pos, heat, amount):
        """Accumulate points (col, row) into the grid."""
        rows, cols = heat.shape
        for x, y in pos:
            cx, cy = int(x), int(y)
            if 0 <= cx < cols and 0 <= cy < rows:
                heat[cy, cx] += amount
        return heat

    # ------------------------------------------ heat map of the match (F6)
    def heat_reset(self, cols, rows):
        """Starts an empty heat map (both buffers live in this object)."""
        self.heat_grids = np.zeros((CHANNELS, rows, cols), np.uint32)
        self.heat_max = np.zeros(CHANNELS, np.uint32)

    def heat_accumulate(self, channel, points, cols, rows, cell_w, cell_h):
        """Adds every (x, y) point of a channel to its cell (atomicAdd)."""
        pts = np.asarray(points, np.float32).reshape(-1, HEAT_FIELDS)
        if len(pts) == 0:
            return
        cx = (pts[:, 0] / max(cell_w, GRID_MIN)).astype(np.int64)
        cy = (pts[:, 1] / max(cell_h, GRID_MIN)).astype(np.int64)
        inside = (cx >= 0) & (cx < cols) & (cy >= 0) & (cy < rows)
        index = (cy * cols + cx)[inside]
        flat = self.heat_grids.reshape(CHANNELS, -1)[channel]
        np.add.at(flat, index, ONE_COUNT)
        self.heat_max[channel] = flat.max()

    def heat_download(self, cols, rows):
        """Copy of the grid and of the maximums (the only DtoH in the GPU)."""
        del cols, rows
        return self.heat_grids.copy(), self.heat_max.copy()

    def heat_render(self, img, grids, maxes, cols, rows, channel, alpha, gain):
        """Bilinear read of the grid, ramp and mix over the image."""
        h, w = img.shape[:2]
        cell_w, cell_h = w / cols, h / rows
        xs, ys = _bilinear_index(w, h, cols, rows, cell_w, cell_h)
        v = _bilinear(_grid_array(grids[channel], rows, cols), xs, ys)
        top = float(maxes[channel])
        v = np.clip(v / top, 0.0, 1.0) if top > 0 else np.zeros(v.shape,
                                                                 np.float32)
        a = alpha * np.minimum(1.0, v * gain)
        ramp = _heat_ramp(v)
        out = _rgb(img) * (1.0 - a[..., None]) + ramp * a[..., None]
        return primitives._to_byte(np.clip(out, 0.0, 1.0))

    def _splat(self, img, pos, col, size, gain):
        h, w = img.shape[:2]
        acc = np.zeros((h, w, CHANNELS), dtype=np.float32)
        for (x, y), c, r in zip(pos, col, size):
            x0, x1 = max(int(x) - int(r), 0), min(int(x) + int(r) + 1, w)
            y0, y1 = max(int(y) - int(r), 0), min(int(y) + int(r) + 1, h)
            if x1 > x0 and y1 > y0:
                acc[y0:y1, x0:x1] += c
        return _clamp(_rgb(img) + acc)


def _bilinear_index(w, h, cols, rows, cell_w, cell_h):
    """(x0, x1, tx) and (y0, y1, ty) of the bilinear read of the pixels."""
    fx = (np.arange(w, dtype=np.float32) + HALF) / max(cell_w, GRID_MIN)
    fy = (np.arange(h, dtype=np.float32) + HALF) / max(cell_h, GRID_MIN)
    fx = np.clip(fx - HALF, 0.0, cols - 1)
    fy = np.clip(fy - HALF, 0.0, rows - 1)
    return _pair(fx, cols), _pair(fy, rows)


def _pair(pos, size):
    """First cell, second cell and weight of the read of every index."""
    first = pos.astype(np.int32)
    second = np.minimum(first + 1, size - 1)
    return first, second, pos - first


def _bilinear(grid, xs, ys):
    """Bilinear read of a (rows, cols) grid with those indexes."""
    (x0, x1, tx), (y0, y1, ty) = xs, ys
    left, right = (1.0 - tx)[None, :], tx[None, :]
    above = left * grid[y0][:, x0] + right * grid[y0][:, x1]
    below = left * grid[y1][:, x0] + right * grid[y1][:, x1]
    return (1.0 - ty)[:, None] * above + ty[:, None] * below


def _grid_array(grid, rows, cols):
    """The grid as a (rows, cols) float32 array (flat or already 2D)."""
    return np.asarray(grid, np.float32).reshape(rows, cols)


def _heat_ramp(v):
    """Blue -> cyan -> yellow -> red ramp of the heat map (three channels)."""
    red = np.clip((v - HALF) * 2.0, 0.0, 1.0)
    green = np.where(v < RAMP_LOW, v * RAMP_SLOPE,
                     np.where(v < RAMP_MID, 1.0, (1.0 - v) * RAMP_SLOPE))
    blue = np.clip((HALF - v) * 2.0, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


def _vignette(h, w, amount):
    ys = (np.arange(h, dtype=np.float32) / h) - HALF
    xs = (np.arange(w, dtype=np.float32) / w) - HALF
    d = np.sqrt(ys[:, None] ** 2 + xs[None, :] ** 2) * SQRT2
    return 1.0 - amount * d * d


def _light_layer(light, h, w, gain):
    x, y, rad, power, r, g, b = light
    ys = np.arange(h, dtype=np.float32)[:, None]
    xs = np.arange(w, dtype=np.float32)[None, :]
    d2 = ((xs - x) ** 2 + (ys - y) ** 2) / max(rad * rad, 1.0)
    mask = np.clip(1.0 - d2, 0.0, 1.0) ** 2 * power * gain
    return np.stack([mask * r, mask * g, mask * b], axis=-1)


def _warp(img, kind, phase, amp, period):
    h, w = img.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    if kind == "heat":
        sx = xs + amp * np.sin(ys / period + phase)
        sy = ys + amp * HALF * np.cos(xs / period + phase)
    else:
        dx, dy = xs - w * HALF, ys - h * HALF
        d = np.sqrt(dx * dx + dy * dy)
        k = amp * np.sin(d / period - phase)
        sx, sy = xs + k * dx / (d + 1.0), ys + k * dy / (d + 1.0)
    ix = np.clip(sx.astype(np.int32), 0, w - 1)
    iy = np.clip(sy.astype(np.int32), 0, h - 1)
    return img[iy, ix]
