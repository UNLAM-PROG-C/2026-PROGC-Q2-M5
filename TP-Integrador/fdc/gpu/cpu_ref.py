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
GLOW_SAT_GAIN = 1.5     # saturated colours glow this much more (white: none)
RAMP_LOW = 0.25         # heat ramp: where the green reaches the top
RAMP_MID = 0.75         # heat ramp: where the red starts to go down
RAMP_SLOPE = 4.0        # heat ramp: slope of the green and red
SQRT2 = 1.41421356      # diagonal of the unit square (vignette)
MEAN_AXES = (1, 3)      # block axes of the minimap reshape
HEAT_FIELDS = 2         # x and y of a recorded point
GRID_MIN = 1e-6         # smallest cell size (never divide by zero)
ONE_COUNT = 1           # each point counts once (atomicAdd of 1 in the GPU)
# --- F11: the crowd of the stands (same numbers as k_crowd) -------------
CROWD_W, CROWD_H, CROWD_JUMP = 0, 1, 2      # seat size and jump (cfg cols)
CROWD_HZ, CROWD_GOAL_JUMP, CROWD_GOAL_HZ = 3, 4, 5
CROWD_WAVE, CROWD_FLAG_W, CROWD_FLAG_H = 6, 7, 8
CROWD_FILL, CROWD_EVERY = 9, 10             # occupancy and one flag each N
CROWD_BODY_W, CROWD_BODY_H = 11, 12         # px: shirt of one person
CROWD_HEAD_R, CROWD_STEP = 13, 14           # head radius and dark step
CROWD_POLE_H, CROWD_SHADE_TOP = 15, 16      # pole height and depth shading
CROWD_SHADE_BOTTOM, CROWD_VAR_MIN = 17, 18  # ... and the shirt variety
CROWD_VAR_RANGE = 19                        # extra brightness of the hash
CROWD_HEAD_CUT, CROWD_OUTLINE = 20, 21      # hair share and rim of the head
CROWD_SHOULDER_EDGE, CROWD_SHOULDER_SHADE = 22, 23   # line and its shade
CROWD_ROWS = 2          # rows that can cover a pixel (back and front)
CROWD_FLAG_HZ = 3.2     # rad/s of the fluttering flag
CROWD_FLAG_CURVE = 0.30  # rad per pixel of height: the flag bends
CROWD_SHOULDER = 2.0    # px the shirt narrows at the shoulders
CROWD_POLE_W = 1.0      # half width of the pole
CROWD_RISER = 1.0       # px of the lit edge of each step
CROWD_JUMP_LOW = 0.4    # smallest jump (share of the maximum)
CROWD_JUMP_SPREAD = 0.6    # what the hash adds to that jump
CROWD_PHASE = 0.01      # rad per hash unit (the phase of each person)
CROWD_PHASE_TOP = 628   # 628 * CROWD_PHASE = one turn
CROWD_HEAD_OFFSET = 0.8  # px: the centre of the head over the shirt
CROWD_SHIFT_VAR = 13    # bits of the hash that the brightness takes
CROWD_SHIFT_SKIN = 5    # bits of the hash of the skin tone
CROWD_SHIFT_HAIR = 9    # ... and of the hair tone
CROWD_STRIPES = 3.0     # stripes of a flag (one of them is white)
CROWD_SPREAD = 0.01     # hash unit -> 0..1
CROWD_HASH_C = 73856093    # prime of the column hash
CROWD_HASH_R = 19349663    # prime of the row hash
CROWD_HASH_MUL = 1274126177    # multiplier of the xorshift hash
CROWD_SHIFT_1 = 13      # shifts of that hash
CROWD_SHIFT_2 = 16      # second shift (the low bits are the noisiest)
CROWD_FULL = 100        # % (100 of hash space)
CROWD_EVERY_SEAT = 7    # hash / 7 separates the amplitudes
CROWD_ONE = 1            # 1 in the hash space (widening)
CROWD_SKINS = 3         # skin tones in the table
CROWD_HAIRS = 3         # hair tones
# Rows of the colour table (pal, one rgb triplet per row).
CROWD_SHIRT_A = 0       # shirt of the left team
CROWD_SHIRT_B = 1       # shirt of the right team
CROWD_SKIN_ROW = 2      # CROWD_SKIN_ROW .. + CROWD_SKINS - 1
CROWD_HAIR_ROW = 5      # CROWD_HAIR_ROW .. + CROWD_HAIRS - 1
CROWD_TREAD_ROW = 8     # floor of one step
CROWD_RISER_ROW = 9     # dark front of the step
CROWD_EDGE_ROW = 10     # lit edge of the step
CROWD_POLE_ROW = 11     # pole of the flag
CROWD_FLAG_WHITE_ROW = 12    # white stripe
CROWD_FLAG_A_ROW = 13   # flag of the left team
CROWD_FLAG_B_ROW = 14   # flag of the right team
CROWD_OUTLINE_ROW = 15  # dark rim of the heads
CACHE_SIZES = 4         # sizes of the band whose steps are kept
_STEP_CACHE = {}        # (h, w) -> (colours (h, 1, 3), shade (h, 1, 1))
_VIGNETTE_CACHE = {}    # (h, w, amount) -> factor of every pixel


def _rgb(img):
  return img.astype(np.float32) / BYTE_MAX


def _clamp(img):
  return np.clip(img * BYTE_MAX, 0.0, BYTE_MAX).astype(np.uint8)


def _saturation(rgb):
  """How colourful each pixel is (0 on white, 1 on a pure colour)."""
  high = rgb.max(axis=-1)
  low = rgb.min(axis=-1)
  sat = (high - low) / np.maximum(high, EPS)
  return np.clip(sat * GLOW_SAT_GAIN, 0.0, 1.0)


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

  def gray_five_steps(self, img, timer):
    """Only host allocation and calculation apply to the numpy path."""
    # Step 1: Allocate host output (malloc).
    out = timer.measure('reserve', np.empty, img.shape, img.dtype)
    # Step 3: Run numpy in place of kernel<<<grid, block>>>.
    timer.measure('kernel', self._gray_into, img, out)
    return out

  def _gray_into(self, img, out):
    out[:] = self._gray_luma(img)[..., None]

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
    over = over * _saturation(small)      # white boards and lines: no halo
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

  def stretch(self, img, lo, hi, vignette=0.0):
    """Contrast stretch between two levels (the vignette comes last)."""
    span = max(hi - lo, 1.0)
    h, w = img.shape[:2]
    out = img.astype(np.float32)
    out -= lo
    out /= span
    np.clip(out, 0.0, 1.0, out=out)
    out *= _vignette(h, w, vignette)[..., None]   # it never goes over 1
    return _clamp(out)

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

  # Animated crowd (F11, FULL only).
  def crowd(self, img, t, side, boost, cfg, pal):
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
  """Darkening of the corners, built once per size and amount."""
  key = (h, w, amount)
  if key not in _VIGNETTE_CACHE:
    if len(_VIGNETTE_CACHE) >= CACHE_SIZES:
      _VIGNETTE_CACHE.pop(next(iter(_VIGNETTE_CACHE)))
    _VIGNETTE_CACHE[key] = _vignette_of(h, w, amount)
  return _VIGNETTE_CACHE[key]


def _vignette_of(h, w, amount):
  """The factor itself: one per pixel, from the centre to the corner."""
  ys = (np.arange(h, dtype=np.float32) / h) - HALF
  xs = (np.arange(w, dtype=np.float32) / w) - HALF
  d = np.sqrt(ys[:, None] ** 2 + xs[None, :] ** 2) * SQRT2
  return 1.0 - amount * d * d


class _Crowd:
  """numpy version of k_crowd: the stands, painted in place.

    The band is a grid of seats of `CROWD_SEAT` px. The steps are the same
    in every frame (they are cached) and every person is written only over
    the pixels it covers, so the cost follows the occupied seats and not
    the whole band. The colours are the ones of the kernel: the same
    comparisons, the same order and the same float32 arithmetic.
    """

  def __init__(self, cfg, pal, t, side, boost):
    self.cfg = np.asarray(cfg, np.float32)
    self.pal = np.asarray(pal, np.float32).reshape(-1, CHANNELS)
    self.t = float(t)
    self.side = int(side)
    self.boost = float(boost)
    self.w = 0
    self.h = 0
    self.rows = 1
    self.xs = np.zeros((1, 1), np.float32)
    self.ys = np.zeros((1, 1), np.float32)

  def paint(self, img):
    """The whole band: the steps, then the people of the two rows."""
    self._setup(img)
    colours, shade = self._steps()
    row = (self.ys / self.cfg[CROWD_H]).astype(np.int32)
    for k in range(CROWD_ROWS):
      self._row(row + k, colours)
    lit = np.multiply(colours, shade, out=colours)
    return primitives._to_byte(np.clip(lit, 0.0, 1.0, out=lit))

  def _setup(self, img):
    """Sizes and the x of every column (once per frame)."""
    self.h, self.w = img.shape[:2]
    self.rows = max(1, int(self.h / self.cfg[CROWD_H]))
    self.xs = np.arange(self.w, dtype=np.float32)[None, :]
    self.ys = np.arange(self.h, dtype=np.float32)[:, None]

  def _steps(self):
    """Steps and shading of the band (they never change: cached)."""
    key = (self.h, self.w)
    if key not in _STEP_CACHE:
      _remember(key, self._step_colours())
    colours, shade = _STEP_CACHE[key]
    band = np.empty((self.h, self.w, CHANNELS), np.float32)
    band[:] = colours               # (h, 1, 3) -> the whole band
    return band, shade

  def _step_colours(self):
    """Colours and shading of the steps: (h, 1, 3) and (h, 1, 1)."""
    row = (self.ys / self.cfg[CROWD_H]).astype(np.int32)
    return self.pal[self._step(row)], self._shade(row)[..., None]

  def _centre(self):
    """x of the middle of the seat."""
    return self.cfg[CROWD_W] * 0.5

  def _dx(self, lx):
    """Distance of the pixel to the middle of its seat."""
    return lx - self._centre()

  def _step(self, row):
    """Tone of the dark step of the row: its floor and its lit edge."""
    cfg = self.cfg
    edge = (row + CROWD_ONE).astype(np.float32) * cfg[CROWD_H] \
        - cfg[CROWD_STEP]
    tone = np.where(self.ys >= edge, CROWD_RISER_ROW, CROWD_TREAD_ROW)
    lit = (self.ys >= edge) & (self.ys < edge + CROWD_RISER)
    return np.where(lit, CROWD_EDGE_ROW, tone)

  def _shade(self, row):
    """The rows above stay farther: they are painted darker."""
    cfg = self.cfg
    far = row.astype(np.float32) / float(max(self.rows - 1, 1))
    span = cfg[CROWD_SHADE_BOTTOM] - cfg[CROWD_SHADE_TOP]
    return cfg[CROWD_SHADE_TOP] + span * far

  def _team(self):
    """Team of each half of the stands (left player, right player)."""
    return np.where(self.xs < self.w / 2.0, 0, 1).astype(np.int32)

  def _var(self, hsh):
    """Brightness of the shirt of that seat (the hash spreads it)."""
    cfg = self.cfg
    noise = ((hsh >> np.uint32(CROWD_SHIFT_VAR)) % np.uint32(CROWD_FULL))
    return cfg[CROWD_VAR_MIN] + (cfg[CROWD_VAR_RANGE]
                                 * noise.astype(np.float32) * CROWD_SPREAD)

  def _half(self, up):
    """Half width of the shirt at that height (rounded shoulders)."""
    cfg = self.cfg
    half = cfg[CROWD_BODY_W] * 0.5
    return np.where(up > cfg[CROWD_BODY_H] - CROWD_SHOULDER,
                    half - CROWD_SHOULDER * 0.5, half)

  def _jump(self, hsh, team):
    """Little jump of each person; the jumping stand goes higher."""
    cfg = self.cfg
    phase = (hsh % np.uint32(CROWD_PHASE_TOP)).astype(np.float32) \
        * CROWD_PHASE
    spread = ((hsh // np.uint32(CROWD_EVERY_SEAT))
              % np.uint32(CROWD_FULL)).astype(np.float32)
    amp = cfg[CROWD_JUMP] * (CROWD_JUMP_LOW
                             + CROWD_JUMP_SPREAD * spread * CROWD_SPREAD)
    same = team == self.side
    amp = amp + np.where(same, cfg[CROWD_GOAL_JUMP] * self.boost, 0.0)
    hz = cfg[CROWD_HZ] + np.where(same,
                                  cfg[CROWD_GOAL_HZ] * self.boost, 0.0)
    return amp * (0.5 + 0.5 * np.sin(self.t * hz + phase))

  def _jumps(self, hsh, team):
    """Jump of every pixel: it is the same in a whole seat row."""
    rows = self._seat_rows()
    if rows is None:
      return self._jump(hsh, team)
    height = hsh.shape[0] // rows
    small = hsh.reshape(rows, height, self.w)[:, 0, :]
    return np.repeat(self._jump(small, team), height, axis=0)

  def _seat_rows(self):
    """Number of seat rows of the band, or None if it does not fit."""
    height = int(self.cfg[CROWD_H])
    return None if self.h % height else self.h // height

  def _row(self, r, colours):
    """People (and flags) of one row of seats over the current image."""
    cfg = self.cfg
    cx = self.xs + (r % 2) * (cfg[CROWD_W] // 2)
    col = (cx / cfg[CROWD_W]).astype(np.int32)
    lx = cx - col * cfg[CROWD_W]
    hsh = _crowd_hash(col, r)
    free = (hsh % np.uint32(CROWD_FULL)) < cfg[CROWD_FILL]
    team = self._team()
    up = ((r + CROWD_ONE).astype(np.float32) * cfg[CROWD_H]
          - cfg[CROWD_STEP] - self.ys - self._jumps(hsh, team))
    self._people(lx, up, team, free, hsh, colours)

  def _people(self, lx, up, team, free, hsh, colours):
    """Bodies and flags over the seats that are already painted."""
    covered = self._body(lx, up, team, free, hsh, colours)
    self._flag(hsh, lx, up, free & ~covered, team, colours)

  def _body(self, lx, up, team, free, hsh, colours):
    """Torso, head, skin, hair and rim of every person (in place)."""
    dx, dy = self._dx(lx), self._dy(up)
    d2 = dx * dx + dy * dy
    torso = free & self._torso(dx, up)
    head = free & (d2 <= self.cfg[CROWD_HEAD_R] ** 2) & ~torso
    skin, hair, rim = self._head_parts(d2, dy)
    self._shirts(colours, torso, team, hsh, up)
    self._heads(colours, head, skin, hair, rim, hsh)
    return torso | head

  def _torso(self, dx, up):
    """Mask of the shirt: a rectangle with the shoulders rounded."""
    cfg = self.cfg
    return ((up >= 0.0) & (up <= cfg[CROWD_BODY_H])
            & (np.abs(dx) <= self._half(up)))

  def _dy(self, up):
    """Height measured from the centre of the head."""
    cfg = self.cfg
    return up - (cfg[CROWD_BODY_H] + cfg[CROWD_HEAD_R] * CROWD_HEAD_OFFSET)

  def _put(self, colours, index, values):
    """Writes `values` at the flat `index` of the band (in place)."""
    if index.size:
      colours.reshape(-1, CHANNELS)[index] = values

  def _skin(self, hsh, index):
    """Skin of those seats (one of the tones of the table)."""
    tone = CROWD_SKIN_ROW + ((hsh[index] >> np.uint32(CROWD_SHIFT_SKIN))
                             % np.uint32(CROWD_SKINS))
    return self.pal[tone]

  def _hair(self, hsh, index):
    """Hair of those seats (a little darker or lighter by hash)."""
    tone = CROWD_HAIR_ROW + ((hsh[index] >> np.uint32(CROWD_SHIFT_HAIR))
                             % np.uint32(CROWD_HAIRS))
    return self.pal[tone] * self._var(hsh[index])[:, None]

  def _shirt(self, team, hsh, up, index):
    """Shirts: team colour, hash brightness and shoulders."""
    lit = self._var(hsh[index]) * self._shoulder(up[index])
    return self.pal[CROWD_SHIRT_A + team[index % self.w]] * lit[:, None]

  def _shoulder(self, up):
    """A darker line at the top of the shirt (it marks the shoulders)."""
    cfg = self.cfg
    return np.where(up > cfg[CROWD_BODY_H] - cfg[CROWD_SHOULDER_EDGE],
                    cfg[CROWD_SHOULDER_SHADE], 1.0)

  def _head_parts(self, d2, dy):
    """(skin, hair, rim) masks of the head."""
    r = self.cfg[CROWD_HEAD_R]
    head = d2 <= r * r
    hair = head & (dy < -self.cfg[CROWD_HEAD_CUT] * r)
    rim = head & ~hair & (d2 > (r - self.cfg[CROWD_OUTLINE]) ** 2)
    return head & ~hair & ~rim, hair, rim

  def _shirts(self, colours, mask, team, hsh, up):
    """Paints the shirts of the mask over the seats (in place)."""
    index = np.flatnonzero(mask)
    if index.size:
      self._put(colours, index,
                self._shirt(team.ravel(), hsh.ravel(), up.ravel(),
                            index))

  def _heads(self, colours, head, skin, hair, rim, hsh):
    """Skin, hair and rim of the heads of the mask (in place)."""
    self._skin_heads(colours, head & skin, hsh.ravel())
    self._hair_heads(colours, head & hair, hsh.ravel())
    self._tone_heads(colours, head & rim, CROWD_OUTLINE_ROW)

  def _skin_heads(self, colours, mask, hsh):
    """Skin of those seats: one of the tones of the table."""
    index = np.flatnonzero(mask)
    self._put(colours, index, self._skin(hsh, index))

  def _hair_heads(self, colours, mask, hsh):
    """Hair of those seats: a tone of the table, darker or lighter."""
    index = np.flatnonzero(mask)
    self._put(colours, index, self._hair(hsh, index))

  def _tone_heads(self, colours, mask, tone):
    """One colour for the whole mask (the dark rim of the head)."""
    self._put(colours, np.flatnonzero(mask), self.pal[tone])

  def _flag_base(self):
    """Height of the shoulder: where the pole starts."""
    return self.cfg[CROWD_BODY_H] + self.cfg[CROWD_HEAD_R]

  def _flag_top(self):
    """Height of the top of the pole."""
    return self._flag_base() + self.cfg[CROWD_POLE_H]

  def _own(self, hsh, free):
    """Seats that got a flag (one out of CROWD_EVERY)."""
    return free & (hsh % self.cfg[CROWD_EVERY].astype(np.uint32) == 0)

  def _wave(self, hsh, up):
    """Sideways shift of the cloth at that height (it flutters)."""
    phase = (hsh % np.uint32(CROWD_PHASE_TOP)).astype(np.float32) \
        * CROWD_PHASE
    y = up - self._flag_top()
    return self.cfg[CROWD_WAVE] * np.sin(self.t * CROWD_FLAG_HZ + phase
                                        + y * CROWD_FLAG_CURVE)

  def _fx(self, hsh, lx, up):
    """Distance to the left edge of the cloth (it moves with the wave)."""
    return (lx - self._centre() + self.cfg[CROWD_FLAG_W] * 0.5
            - self._wave(hsh, up))

  def _pole(self, colours, lx, up, own):
    """Pole of the flag: one column, over the cloth when they cross."""
    mask = (own & (up >= self._flag_base()) & (up <= self._flag_top())
            & (np.abs(self._dx(lx)) <= CROWD_POLE_W))
    self._put(colours, np.flatnonzero(mask), self.pal[CROWD_POLE_ROW])

  def _cloth(self, colours, index, fx, team):
    """Cloth of the flag: the stripes and its border, in place."""
    inside = (fx >= 0.0) & (fx < self.cfg[CROWD_FLAG_W])
    cloth = index[inside]
    stripe = (fx[inside] * CROWD_STRIPES
              / self.cfg[CROWD_FLAG_W]).astype(np.int32) & 1
    tone = np.where(stripe == 1, CROWD_FLAG_WHITE_ROW,
                    CROWD_FLAG_A_ROW + team.ravel()[cloth % self.w])
    self._put(colours, cloth, self.pal[tone])

  def _flag(self, hsh, lx, up, free, team, colours):
    """Flag of that seat (if it has one): the pole and the cloth."""
    own = self._own(hsh, free)
    top = self._flag_top()
    index = np.flatnonzero(own & (up >= top - self.cfg[CROWD_FLAG_H])
                           & (up <= top))
    if index.size:
      self._cloth(colours, index, self._fx_at(hsh, lx, up, index), team)
    self._pole(colours, lx, up, own)

  def _fx_at(self, hsh, lx, up, index):
    """Distance to the left edge of the cloth, only at `index`."""
    return (lx.ravel()[index] - self._centre()
            + self.cfg[CROWD_FLAG_W] * 0.5
            - self._wave(hsh.ravel()[index], up.ravel()[index]))


def _remember(key, pair):
  """Keeps the steps of one size, forgetting the oldest ones."""
  _STEP_CACHE[key] = pair
  while len(_STEP_CACHE) > CACHE_SIZES:
    _STEP_CACHE.pop(next(iter(_STEP_CACHE)))



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
