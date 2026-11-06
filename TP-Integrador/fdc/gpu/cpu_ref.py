"""CPU (numpy) reference of every GPU kernel of the effects chain.

It has exactly the same API as fdc.gpu.backend.Gpu, so the tests can run
both and compare, and the game can fall back to this version when there is
no CUDA. Numpy is only imported here (the game works without it).
"""
import numpy as np

from fdc.gpu import primitives

CHANNELS = 3            # interleaved RGB
BYTE_MAX = 255.0        # top of the 8 bit range
BIT_HALF_W = 3          # column of the half width of a paper bit
BIT_HALF_H = 4          # column of the half height of a paper bit
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
# --- F11: the crowd of the stands (same numbers as k_tribuna) -------------
CROWD_W, CROWD_H, CROWD_JUMP = 0, 1, 2      # seat size and jump (cfg cols)
CROWD_HZ, CROWD_GOAL_JUMP, CROWD_GOAL_HZ = 3, 4, 5
CROWD_WAVE, CROWD_FLAG_W, CROWD_FLAG_H = 6, 7, 8
CROWD_FILL, CROWD_EVERY = 9, 10             # occupancy and one flag each N
CROWD_ROWS = 2          # rows that can cover a pixel (back and front)
CROWD_HEAD = 2.2        # px: radius of the head
CROWD_SIDE = 1.0        # px of air at the sides of the body
CROWD_FEET = 1.0        # px between the floor of the seat and the feet
CROWD_BODY_GAP = 4.0    # px of the seat height that is not body
CROWD_FLAG_HZ = 4.0     # rad/s of the fluttering flag
CROWD_FLAG_CURVE = 0.35  # rad per pixel of height: the flag bends
CROWD_PHASE = 0.01      # rad per hash unit (the phase of each person)
CROWD_PHASE_TOP = 628   # 628 * CROWD_PHASE = one turn
CROWD_RAIL = 0.6        # px: dark line at the edge of the seat
CROWD_SHADE = 0.82      # how much that line darkens
CROWD_FLAG_LIGHT = 0.45    # how much white the flag carries (0-1)
CROWD_HASH_C = 73856093    # prime of the column hash
CROWD_HASH_R = 19349663    # prime of the row hash
CROWD_HASH_MUL = 1274126177    # multiplier of the xorshift hash
CROWD_SHIFT_1 = 13      # shifts of that hash
CROWD_SHIFT_2 = 16      # second shift (the low bits are the noisiest)
CROWD_FULL = 100        # % (100 of hash space)
CROWD_EVERY_SEAT = 7    # hash / 7 separates the amplitudes
CROWD_JUMP_LOW = 0.4    # smallest jump of a person (share of CROWD_JUMP)
CROWD_JUMP_SPREAD = 0.6   # how much the hash adds to that jump
CROWD_ONE = 1            # 1 in the hash space (widening)
# Rows of the colour table (pal, one rgb triplet per row).
CROWD_SHIRT_A = 0       # shirt of the left team
CROWD_SHIRT_B = 1       # shirt of the right team
CROWD_HAIR_ROW = 2      # hair
CROWD_SKIN_ROW = 3      # skin
CROWD_SEAT_A = 4        # one row of seats
CROWD_SEAT_B = 5        # the other one


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

    def confetti(self, img, pos, col, gain):
        """Confetti: pos (n,2), col (n,5) r,g,b, half width, half height."""
        h, w = img.shape[:2]
        base = _rgb(img)
        acc = np.zeros((h, w, CHANNELS), dtype=np.float32)
        for (x, y), bit in zip(pos, col):
            self._paper(acc, base, (x, y), bit, gain)
        return _clamp(base + acc)

    def _paper(self, acc, base, centre, bit, gain):
        """Blends one paper bit over its rectangle of the accumulator."""
        half_w, half_h = int(bit[BIT_HALF_W]), int(bit[BIT_HALF_H])
        height, width = base.shape[:2]
        x0, x1 = max(int(centre[0]) - half_w, 0), min(
            int(centre[0]) + half_w + 1, width)
        y0, y1 = max(int(centre[1]) - half_h, 0), min(
            int(centre[1]) + half_h + 1, height)
        if x1 > x0 and y1 > y0:
            acc[y0:y1, x0:x1] += (bit[:CHANNELS] - base[y0:y1, x0:x1]) * gain

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

    # ------------------------------------- tribuna animada (F11, solo FULL)
    def tribuna(self, img, t, side, boost, cfg, pal):
        """Crowd of the stands: seats, people and flags (numpy version)."""
        return _Crowd(cfg, pal, t, side, boost).paint(img)


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


class _Crowd:
    """numpy version of k_tribuna: the stands, pixel by pixel.

    It is the slow path on purpose: in FULL mode on a CPU every pixel of the
    band pays its sines and hashes, which is exactly what the projector demo
    wants to show before switching to the optimized mode.
    """

    def __init__(self, cfg, pal, t, side, boost):
        self.cfg = np.asarray(cfg, np.float32)
        self.pal = np.asarray(pal, np.float32).reshape(-1, CHANNELS)
        self.t = float(t)
        self.side = int(side)
        self.boost = float(boost)
        self.w = 0
        self.xs = np.zeros((1, 1), np.float32)
        self.ys = np.zeros((1, 1), np.float32)

    def paint(self, img):
        """The whole band: seats, then the people of the two rows."""
        h, w = img.shape[:2]
        self.w, self.xs = w, np.arange(w, dtype=np.float32)[None, :]
        self.ys = np.arange(h, dtype=np.float32)[:, None]
        row = (self.ys / self.cfg[CROWD_H]).astype(np.int32)
        colours = self._seats(row)
        for k in range(CROWD_ROWS):
            colours = self._row(row + k, colours)
        line = (self.ys - row * self.cfg[CROWD_H]) < CROWD_RAIL
        colours = np.where(line[..., None], colours * CROWD_SHADE, colours)
        return primitives._to_byte(np.clip(colours, 0.0, 1.0))

    def _seats(self, row):
        """Two tones of seat (one per row parity), filled up to the edges."""
        tones = np.where((row % 2 == 0)[..., None], self.pal[CROWD_SEAT_A],
                         self.pal[CROWD_SEAT_B])
        return np.array(np.broadcast_to(
            tones, (self.ys.shape[0], self.w, CHANNELS)), np.float32)

    def _row(self, r, colours):
        """People (and flags) of one row of seats over the current image."""
        cfg = self.cfg
        cx = self.xs + ((r % 2) * (cfg[CROWD_W] // 2)).astype(np.float32)
        col = (cx / cfg[CROWD_W]).astype(np.int32)
        lx = cx - col * cfg[CROWD_W]
        hsh = _crowd_hash(col, r)
        free = (hsh % np.uint32(CROWD_FULL)) < cfg[CROWD_FILL]
        team = self._team()
        up = ((r + CROWD_ONE).astype(np.float32) * cfg[CROWD_H] - self.ys
              - self._jump(hsh, team))
        return self._people(lx, up, team, free, hsh, colours)

    def _people(self, lx, up, team, free, hsh, colours):
        """Bodies and flags over the seats that are already painted."""
        person, covered = self._body(lx, up, team, free)
        colours = np.where(covered[..., None], person, colours)
        flag, pole = self._flag(hsh, lx, up, free & ~covered)
        shirt = self.pal[CROWD_SHIRT_A + team]
        light = CROWD_FLAG_LIGHT + (1.0 - CROWD_FLAG_LIGHT) * shirt
        colours = np.where(flag[..., None], light, colours)
        return np.where(pole[..., None], self.pal[CROWD_SEAT_A], colours)

    def _team(self):
        """Team of each half of the stands (left player, right player)."""
        return np.where(self.xs < self.w / 2.0, 0, 1).astype(np.int32)

    def _jump(self, hsh, team):
        """Little jump of each person; the jumping stand goes higher."""
        cfg = self.cfg
        phase = (hsh % np.uint32(CROWD_PHASE_TOP)).astype(np.float32) \
            * CROWD_PHASE
        spread = ((hsh // CROWD_EVERY_SEAT) % np.uint32(CROWD_FULL))
        amp = cfg[CROWD_JUMP] * (CROWD_JUMP_LOW + CROWD_JUMP_SPREAD
                                 * spread.astype(np.float32) * CROWD_PHASE)
        same = team == self.side
        amp = amp + np.where(same, cfg[CROWD_GOAL_JUMP] * self.boost, 0.0)
        hz = cfg[CROWD_HZ] + np.where(same,
                                      cfg[CROWD_GOAL_HZ] * self.boost, 0.0)
        return amp * (0.5 + 0.5 * np.sin(self.t * hz + phase))

    def _body(self, lx, up, team, free):
        """Body and head of the person of that seat: (colour, mask)."""
        cfg = self.cfg
        body = cfg[CROWD_H] - CROWD_BODY_GAP
        head_y = body + CROWD_HEAD
        torso = (free & (up >= CROWD_FEET) & (up <= body)
                 & (lx >= CROWD_SIDE) & (lx <= cfg[CROWD_W] - CROWD_SIDE))
        dx, dy = lx - cfg[CROWD_W] * 0.5, up - head_y
        head = free & (dx * dx + dy * dy <= CROWD_HEAD * CROWD_HEAD)
        colour = np.where(torso[..., None], self.pal[CROWD_SHIRT_A + team],
                          self.pal[CROWD_SKIN_ROW])
        colour = np.where((head & (up > head_y))[..., None],
                          self.pal[CROWD_HAIR_ROW], colour)
        return colour, torso | head

    def _flag(self, hsh, lx, up, free):
        """Flag of the seat (if it has one): (ribbon, pole) masks."""
        cfg = self.cfg
        base = (cfg[CROWD_H] - CROWD_BODY_GAP + 2.0 * CROWD_HEAD
                + CROWD_FEET)
        box = free & (hsh % cfg[CROWD_EVERY].astype(np.uint32) == 0)
        box = box & (up >= base) & (up < base + cfg[CROWD_FLAG_H])
        phase = (hsh % np.uint32(CROWD_PHASE_TOP)).astype(np.float32) \
            * CROWD_PHASE
        wave = cfg[CROWD_WAVE] * np.sin(self.t * CROWD_FLAG_HZ + phase
                                       + up * CROWD_FLAG_CURVE)
        pole = box & (lx < CROWD_SIDE)
        fx = lx - wave - CROWD_SIDE
        ribbon = box & (fx >= 0.0) & (fx < cfg[CROWD_FLAG_W]) & ~pole
        return ribbon, pole


def _crowd_hash(col, row):
    """Same xorshift hash as `crowd_hash` in the kernel (uint32 maths)."""
    hsh = (col.astype(np.uint32) * np.uint32(CROWD_HASH_C)) ^ (
        row.astype(np.uint32) * np.uint32(CROWD_HASH_R))
    hsh ^= hsh >> np.uint32(CROWD_SHIFT_1)
    hsh *= np.uint32(CROWD_HASH_MUL)
    hsh ^= hsh >> np.uint32(CROWD_SHIFT_2)
    return hsh


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
