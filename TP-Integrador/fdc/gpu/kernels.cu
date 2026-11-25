// Post-processing kernels for the football game.
//
// Image kernels use one thread per pixel, 2D indexing with
// blockIdx/blockDim/threadIdx and an early border check. Buffers are in
// global memory. Use atomics when threads update the same output element.
//
// Images: packed RGB bytes, no row padding, i = (y*w + x)*3.
// Intermediate light buffers: three float channels per pixel.
// Unless otherwise noted, w and h describe the output.
#include "kernels_config.cuh"

// Global thread index (blockIdx * blockDim + threadIdx) plus the border
// check. Each helper returns false when the thread falls outside the data,
// so the kernel can return early.
// 2D: one thread per pixel, x is the column and y is the row of a w x h image.
__device__ bool pixel_coords(int &x, int &y, int w, int h)
{
  x = blockIdx.x * blockDim.x + threadIdx.x;
  y = blockIdx.y * blockDim.y + threadIdx.y;
  return x < w && y < h;
}

// 1D: one thread per element, i is the element index in [0, n).
__device__ bool thread_index(int &i, int n)
{
  i = blockIdx.x * blockDim.x + threadIdx.x;
  return i < n;
}

// Copy a packed RGB pixel without conversions.
__device__ __forceinline__ void copy_rgb(const unsigned char *src,
                                         unsigned char *dst)
{
  dst[RED] = src[RED];
  dst[GREEN] = src[GREEN];
  dst[BLUE] = src[BLUE];
}

__device__ __forceinline__ float bright_gain(const unsigned char *src,
                                             int i, float threshold)
{
  float l = (LUMA_RED * src[i] + LUMA_GREEN * src[i + GREEN]
             + LUMA_BLUE * src[i + BLUE]) / PIXEL_MAX;
  float k = l > threshold ? (l - threshold) / (UNIT - threshold) : ZERO;
  float hi = fmaxf(src[i], fmaxf(src[i + GREEN], src[i + BLUE])) / PIXEL_MAX;
  float lo = fminf(src[i], fminf(src[i + GREEN], src[i + BLUE])) / PIXEL_MAX;
  float sat = hi > ZERO ? (hi - lo) / hi : ZERO;
  return k * fminf(sat * GLOW_SAT_GAIN, UNIT);
}

// Glow: scale the halo by saturation, with a peak gain of 1.
// White signs and lines produce no halo; saturated sparks and ice do.
// Keep only samples above the threshold, one pixel per 2x2 block.
// The halo does not need full-resolution detail.
__global__ void bright_pass(const unsigned char *src, float *dst,
                            int hw, int hh, int w, float threshold)
{
  int x, y;
  if (!pixel_coords(x, y, hw, hh)) return;
  int i = ((GLOW_SCALE * y) * w + GLOW_SCALE * x) * CH;
  float k = bright_gain(src, i, threshold);
  int o = (y * hw + x) * CH;
  dst[o] = src[i] * k / PIXEL_MAX;
  dst[o + GREEN] = src[i + GREEN] * k / PIXEL_MAX;
  dst[o + BLUE] = src[i + BLUE] * k / PIXEL_MAX;
}

// Blur along one axis, preserving the sample order of each channel.
__device__ __forceinline__ void glow_average(const float *src, float *dst,
                                             int count, int step)
{
  float rgb[CH] = {ZERO, ZERO, ZERO};
  for (int k = 0; k < count; ++k)
  {
    int i = k * step * CH;
    for (int c = 0; c < CH; ++c)
      rgb[c] += src[i + c];
  }
  for (int c = 0; c < CH; ++c)
    dst[c] = rgb[c] / (float)count;
}

// Horizontal blur of the float halo buffer.
__global__ void glow_rows(const float *src, float *dst, int w, int h, int r)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int x0 = max(0, x - r), x1 = min(w - 1, x + r);
  int i = (y * w + x0) * CH, o = (y * w + x) * CH;
  glow_average(src + i, dst + o, x1 - x0 + 1, 1);
}

// Vertical blur of the float halo buffer.
__global__ void glow_cols(const float *src, float *dst, int w, int h, int r)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int y0 = max(0, y - r), y1 = min(h - 1, y + r);
  int i = (y0 * w + x) * CH, o = (y * w + x) * CH;
  glow_average(src + i, dst + o, y1 - y0 + 1, w);
}

__device__ __forceinline__ float vignette_gain(int x, int y, int w, int h,
                                                float vignette)
{
  float cx = (x / (float)w) - CENTER;
  float cy = (y / (float)h) - CENTER;
  float d = sqrtf(cx * cx + cy * cy) * SQRT2;
  return UNIT - vignette * d * d;
}

__device__ __forceinline__ void composite_rgb(
    const unsigned char *base, const float *glow, unsigned char *out,
    float exposure, float gamma, float v, float glow_strength)
{
  float c[CH];
  for (int k = 0; k < CH; ++k)
  {
    float p = (base[k] / PIXEL_MAX) * exposure + glow[k] * glow_strength;
    p = powf(p > ZERO ? p : ZERO, gamma) * v;
    c[k] = (p > UNIT ? UNIT : p) * PIXEL_MAX;
  }
  for (int k = 0; k < CH; ++k)
    out[k] = (unsigned char)c[k];
}

// Final composition: exposure, gamma, additive halo and vignette.
__global__ void composite(const unsigned char *base, const float *glow,
                          unsigned char *out, int w, int h, int gw, int gh,
                          float exposure, float gamma, float vignette,
                          float glow_strength)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int gx = x / GLOW_SCALE < gw ? x / GLOW_SCALE : gw - 1;
  int gy = y / GLOW_SCALE < gh ? y / GLOW_SCALE : gh - 1;
  int gi = (gy * gw + gx) * CH, i = (y * w + x) * CH;
  float v = vignette_gain(x, y, w, h, vignette);
  composite_rgb(base + i, glow + gi, out + i, exposure, gamma, v,
                glow_strength);
}

__device__ __forceinline__ void splat_row(const float *rgb, float *acc,
                                           int cx, int r, int w, float gain)
{
  for (int x = cx - r; x <= cx + r; ++x)
  {
    if (x < 0 || x >= w) continue;
    int i = x * CH;
    atomicAdd(&acc[i], rgb[RED] * gain);
    atomicAdd(&acc[i + GREEN], rgb[GREEN] * gain);
    atomicAdd(&acc[i + BLUE], rgb[BLUE] * gain);
  }
}

// Each particle spreads light over a square of side `size` pixels.
// Use atomicAdd so overlapping writes to a pixel are not lost.
__global__ void splat_particles(const float *pos, const float *col, int n,
                                float *acc, int w, int h, float gain)
{
  int p;
  if (!thread_index(p, n)) return;
  int cx = (int)pos[POSITION_FIELDS * p];
  int cy = (int)pos[POSITION_FIELDS * p + 1];
  const float *fields = col + PARTICLE_FIELDS * p;
  int r = (int)fields[PARTICLE_RADIUS];
  const float rgb[CH] = {fields[RED], fields[GREEN], fields[BLUE]};
  for (int y = cy - r; y <= cy + r; ++y)
    if (y >= 0 && y < h) splat_row(rgb, acc + y * w * CH, cx, r, w, gain);
}

__device__ __forceinline__ void confetti_row(
    const float *rgb, const unsigned char *img, float *acc,
    int cx, int hw, int w, float gain)
{
  for (int x = cx - hw; x <= cx + hw; ++x)
  {
    if (x < 0 || x >= w) continue;
    int i = x * CH;
    atomicAdd(&acc[i], (rgb[RED] - img[i] / PIXEL_MAX) * gain);
    atomicAdd(&acc[i + GREEN], (rgb[GREEN] - img[i + GREEN] / PIXEL_MAX) * gain);
    atomicAdd(&acc[i + BLUE], (rgb[BLUE] - img[i + BLUE] / PIXEL_MAX) * gain);
  }
}

// Goal confetti: one thread per piece, painting its rectangle.
// Blend with the background to preserve paper colors over the pitch.
// Atomics accumulate the difference; add_light adds it to the image.
__global__ void confetti(const float *pos, const float *col, int n,
    const unsigned char *img, float *acc, int w, int h, float gain)
{
  int p;
  if (!thread_index(p, n)) return;
  int cx = (int)pos[POSITION_FIELDS * p];
  int cy = (int)pos[POSITION_FIELDS * p + 1];
  const float *fields = col + PAPER_FIELDS * p;
  int hw = (int)fields[PAPER_HALF_W], hh = (int)fields[PAPER_HALF_H];
  const float rgb[CH] = {fields[RED], fields[GREEN], fields[BLUE]};
  for (int y = cy - hh; y <= cy + hh; ++y)
    if (y >= 0 && y < h)
      confetti_row(rgb, img + y * w * CH, acc + y * w * CH, cx, hw, w, gain);
}

// Add the accumulated light to the image (particles and spotlights).
__global__ void add_light(const unsigned char *base, const float *acc,
                          unsigned char *out, int w, int h, float gain)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  for (int k = 0; k < CH; ++k)
  {
    float p = base[i + k] / PIXEL_MAX + acc[i + k] * gain;
    p = p > UNIT ? UNIT : p;
    out[i + k] = (unsigned char)(p * PIXEL_MAX);
  }
}

// Heat waves shift each pixel by sampling elsewhere in the image.
__global__ void heat_distort(const unsigned char *src, unsigned char *out,
                             int w, int h, float phase, float amp,
                             float period)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int sx = x + (int)(amp * sinf(y / period + phase));
  int sy = y + (int)(amp * HALF * cosf(x / period + phase));
  sx = min(max(sx, 0), w - 1);
  sy = min(max(sy, 0), h - 1);
  int i = (y * w + x) * CH;
  int j = (sy * w + sx) * CH;
  copy_rgb(src + j, out + i);
}

// Linear blend of two images (alpha 0 = a, alpha 1 = b).
__global__ void mix_layers(const unsigned char *a, const unsigned char *b,
                           unsigned char *out, int w, int h, float alpha)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  for (int k = 0; k < CH; ++k)
    out[i + k] = (unsigned char)(a[i + k] * (UNIT - alpha)
                                 + b[i + k] * alpha);
}

// Use atomics to count luma in 256 bins: threads can share a bin.
__global__ void luma_hist(const unsigned char *src, int *hist, int w, int h)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  float l = (LUMA_RED * src[i] + LUMA_GREEN * src[i + GREEN]
             + LUMA_BLUE * src[i + BLUE]);
  int bin = (int)l;
  bin = bin < 0 ? 0 : (bin > PIXEL_MAX_INT ? PIXEL_MAX_INT : bin);
  atomicAdd(&hist[bin], HIST_INCREMENT);
}

__device__ __forceinline__ float unit_clip(float value)
{
  return value < ZERO ? ZERO : (value > UNIT ? UNIT : value);
}

__device__ __forceinline__ float byte_clip(float value)
{
  return value < ZERO ? ZERO : (value > PIXEL_MAX ? PIXEL_MAX : value);
}

// Stretch contrast between two levels computed on the CPU. Apply the
// vignette here to avoid an extra pass when glow is off.
__global__ void stretch(const unsigned char *src, unsigned char *out, int w,
                        int h, float lo, float hi, float vignette)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  float span = hi - lo > MIN_STRETCH_SPAN ? hi - lo : MIN_STRETCH_SPAN;
  float v = vignette_gain(x, y, w, h, vignette);
  for (int k = 0; k < CH; ++k)
  {
    float p = unit_clip((src[i + k] - lo) / span);
    out[i + k] = (unsigned char)(p * v * PIXEL_MAX);
  }
}

// F1 image primitives: one thread per pixel, 2D indices, early border
// checks and global memory buffers.

// One thread per pixel; the border check protects global memory reads.
__global__ void k_gray(const unsigned char *src, unsigned char *dst,
                       int width, int height)
{
  int x, y;
  if (!pixel_coords(x, y, width, height)) return;
  int i = (y * width + x) * CH;
  float luma = LUMA_RED * src[i] + LUMA_GREEN * src[i + GREEN]
               + LUMA_BLUE * src[i + BLUE];
  unsigned char gray = (unsigned char)(luma + BYTE_ROUND);
  dst[i] = dst[i + GREEN] = dst[i + BLUE] = gray;
}

// Negative: subtract each channel from 255.
__global__ void k_invert(const unsigned char *src, unsigned char *dst,
                         int w, int h)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  dst[i] = PIXEL_MAX_INT - src[i];
  dst[i + GREEN] = PIXEL_MAX_INT - src[i + GREEN];
  dst[i + BLUE] = PIXEL_MAX_INT - src[i + BLUE];
}

// Gain: multiply each channel for night lighting or auto exposure.
__global__ void k_gain(const unsigned char *src, unsigned char *dst,
                       int w, int h, float gain)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  for (int c = 0; c < CH; ++c)
  {
    float v = src[i + c] * gain;
    v = v < ZERO ? ZERO : (v > PIXEL_MAX ? PIXEL_MAX : v);
    dst[i + c] = (unsigned char)(v + BYTE_ROUND);
  }
}

// Tint: multiply by a color (0..1 per channel).
__global__ void k_tint(const unsigned char *src, unsigned char *dst,
                       int w, int h, float r, float g, float b)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  dst[i] = (unsigned char)(src[i] * r + BYTE_ROUND);
  dst[i + GREEN] = (unsigned char)(src[i + GREEN] * g + BYTE_ROUND);
  dst[i + BLUE] = (unsigned char)(src[i + BLUE] * b + BYTE_ROUND);
}

__device__ __forceinline__ void rotate_sample(
    const unsigned char *src, unsigned char *dst, int w, int h, int x, int y)
{
  if (x < 0 || x >= w || y < 0 || y >= h)
  {
    dst[RED] = BLACK;
    dst[GREEN] = BLACK;
    dst[BLUE] = BLACK;
    return;
  }
  copy_rgb(src + (y * w + x) * CH, dst);
}

// Rotate about the center using nearest-neighbor sampling.
// Samples outside the image become black.
__global__ void k_rotate(const unsigned char *src, unsigned char *dst,
                         int w, int h, float angle)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  float cx = (w - 1) * HALF, cy = (h - 1) * HALF;
  float c = cosf(angle), s = sinf(angle);
  float dx = x - cx, dy = y - cy;
  int sx = (int)(cx + c * dx + s * dy + BYTE_ROUND);
  int sy = (int)(cy - s * dx + c * dy + BYTE_ROUND);
  rotate_sample(src, dst + (y * w + x) * CH, w, h, sx, sy);
}

// Ice power (F11): two passes, one image upload and one download.
// k_ice_edges writes Sobel magnitudes in global memory and uses atomicMax
// for the maximum. Nonnegative float bits sort in the same order as floats.
// k_ice_apply uses that maximum, adds edges, tints and blends, preserving
// the rounding of the original standalone passes.

// Normalized luma of one pixel for the ice edges.
__device__ float ice_gray(const unsigned char *src, int i)
{
  return (LUMA_RED * src[i] + LUMA_GREEN * src[i + GREEN]
          + LUMA_BLUE * src[i + BLUE]) / PIXEL_MAX;
}

__device__ __forceinline__ float sobel_edges(
    const unsigned char *src, int w, int x, int x0, int x1, int y0, int y1, int y)
{
  float a = ice_gray(src, (y0 * w + x0) * CH);
  float b = ice_gray(src, (y0 * w + x) * CH);
  float c = ice_gray(src, (y0 * w + x1) * CH);
  float d = ice_gray(src, (y * w + x0) * CH), f = ice_gray(src, (y * w + x1) * CH);
  float g = ice_gray(src, (y1 * w + x0) * CH);
  float hh = ice_gray(src, (y1 * w + x) * CH);
  float k = ice_gray(src, (y1 * w + x1) * CH);
  float gx = (c + SOBEL_NEAR_WEIGHT * f + k) - (a + SOBEL_NEAR_WEIGHT * d + g);
  float gy = (g + SOBEL_NEAR_WEIGHT * hh + k) - (a + SOBEL_NEAR_WEIGHT * b + c);
  return sqrtf(gx * gx + gy * gy) * SOBEL_SCALE;
}

__global__ void k_ice_edges(const unsigned char *src, float *edges,
                            unsigned int *top, int w, int h)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int x0 = max(0, x - 1), x1 = min(w - 1, x + 1);
  int y0 = max(0, y - 1), y1 = min(h - 1, y + 1);
  float v = sobel_edges(src, w, x, x0, x1, y0, y1, y);
  edges[y * w + x] = v;
  atomicMax(top, __float_as_uint(v));
}

__device__ __forceinline__ float ice_edge(float magnitude, unsigned int peak)
{
  float max_value = __uint_as_float(peak);
  float v = magnitude / (max_value > ZERO ? max_value : UNIT);
  return (float)(unsigned char)(unit_clip(v) * PIXEL_MAX + BYTE_ROUND);
}

__device__ __forceinline__ void ice_tint(
    const unsigned char *src, unsigned char *dst, const float *tint,
    float edge, float strength, float amount)
{
  for (int c = 0; c < CH; ++c)
  {
    float lit = byte_clip(src[c] + edge * strength);
    float glow = (float)(unsigned char)(lit + BYTE_ROUND);
    float blue = (float)(unsigned char)(glow * tint[c] + BYTE_ROUND);
    float mixed = glow * (UNIT - amount) + blue * amount;
    dst[c] = (unsigned char)mixed;
  }
}

__global__ void k_ice_apply(const unsigned char *src, const float *edges,
                            const unsigned int *top, unsigned char *dst,
                            int w, int h, float strength, float tr,
                            float tg, float tb, float amount)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  float edge = ice_edge(edges[y * w + x], top[0]);
  float tint[CH] = {tr, tg, tb};
  ice_tint(src + i, dst + i, tint, edge, strength, amount);
}

__device__ __forceinline__ float spotlight_gain(
    const float *lamp, int x, int y, float light, float limit)
{
  float dx = x - lamp[0], dy = y - lamp[1];
  float r = lamp[LAMP_RADIUS], power = lamp[LAMP_POWER];
  float d2 = (dx * dx + dy * dy) / (r * r);
  if (d2 < UNIT)
  {
    float fall = UNIT - d2;
    if (limit > ZERO) light += power * fall * fall * (limit - light);
    else light += power * fall * fall;
  }
  return light;
}

__device__ __forceinline__ unsigned char spot_byte(
    unsigned char value, float light, float tint)
{
  float v = value * light * tint;
  return (unsigned char)(byte_clip(v) + BYTE_ROUND);
}

// Night and blackout (F3/F4): one thread per pixel with an early border
// check. Read lights (x, y, radius, power) from global memory and multiply
// the pixel by their combined light. With limit > 0 each lamp adds a
// fraction of the remaining headroom. With limit == 0 the sum is uncapped.
__global__ void k_spotlights(const unsigned char *src, unsigned char *dst,
                             int w, int h, const float *lights, int n,
                             float ambient, float tr, float tg, float tb, float limit)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  float light = ambient;
  for (int k = 0; k < n && k < SPOT_MAX; ++k)
    light = spotlight_gain(lights + LAMP_FIELDS * k, x, y, light, limit);
  int i = (y * w + x) * CH;
  dst[i] = spot_byte(src[i], light, tr);
  dst[i + GREEN] = spot_byte(src[i + GREEN], light, tg);
  dst[i + BLUE] = spot_byte(src[i + BLUE], light, tb);
}

__device__ __forceinline__ void fire_sample_coords(
    int x, int y, float cx, float cy, float rad, float t, float amp,
    int &sx, int &sy)
{
  float dx = x - cx, dy = y - cy;
  float d = sqrtf(dx * dx + dy * dy);
  if (d < rad)
  {
    float fall = UNIT - d / rad;
    sx = x + (int)(amp * sinf(y * HEAT_FREQ_Y + t * HEAT_SPEED_Y) * fall);
    sy = y + (int)(amp * HEAT_LATERAL
                   * sinf(x * HEAT_FREQ_X + t * HEAT_SPEED_X) * fall);
  }
}

// Hot air around the ball during fire power. Pixels outside the radius
// are copied unchanged. The launch size is independent of the radius.
__global__ void k_heat_distort(const unsigned char *src, unsigned char *dst,
                               int w, int h, float cx, float cy, float rad,
                               float t, float amp)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int sx = x, sy = y;
  fire_sample_coords(x, y, cx, cy, rad, t, amp, sx, sy);
  sx = sx < 0 ? 0 : (sx >= w ? w - 1 : sx);
  sy = sy < 0 ? 0 : (sy >= h ? h - 1 : sy);
  copy_rgb(src + (sy * w + sx) * CH, dst + (y * w + x) * CH);
}

// Night luma histogram (F4): atomicAdd for the bins and atomicMax for
// the peak because threads can update the same global memory locations.
__global__ void k_luma_hist(const unsigned char *src, unsigned int *hist,
                            unsigned int *luma_max, int w, int h)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  float l = LUMA_RED * src[i] + LUMA_GREEN * src[i + GREEN] + LUMA_BLUE * src[i + BLUE];
  unsigned int bin = (unsigned int)(l + BYTE_ROUND);  // same rounding as k_gray
  atomicAdd(&hist[bin], HIST_INCREMENT_U);
  atomicMax(luma_max, bin);
}

// ===========================================================================
// F5: replay
// ===========================================================================

__device__ __forceinline__ float crt_vignette(int x, int y, int w, int h,
                                               float vignette)
{
  float nx = CRT_COORD_SCALE * x / (float)(w > 1 ? w - 1 : 1) - UNIT;
  float ny = CRT_COORD_SCALE * y / (float)(h > 1 ? h - 1 : 1) - UNIT;
  float d = sqrtf(nx * nx + ny * ny) * CRT_DIAGONAL;
  return UNIT - vignette * d * d;
}

// Pseudorandom grain with intentional unsigned overflow.
__device__ __forceinline__ float crt_grain(int x, int y, int frame)
{
  unsigned int seed = (unsigned int)(x * CRT_X_MUL + y * CRT_Y_MUL
                                    + frame * CRT_FRAME_MUL) * CRT_NOISE_MUL;
  return (float)((seed >> CRT_NOISE_SHIFT) & CRT_NOISE_MASK) / PIXEL_MAX - HALF;
}

__device__ __forceinline__ float crt_luma(
    const unsigned char *src, float band, float vig,
    float grain, float noise, float amount)
{
  float l = (LUMA_RED * src[RED] + LUMA_GREEN * src[GREEN]
             + LUMA_BLUE * src[BLUE]) / PIXEL_MAX;
  float crt = l * band * vig + grain * noise;
  return l + (crt - l) * amount;
}

__device__ __forceinline__ void crt_tint(unsigned char *dst, float v,
                                         float tr, float tg, float tb)
{
  float out[CH] = {v * tr, v * tg, v * tb};
  for (int c = 0; c < CH; ++c)
  {
    float b = out[c] * PIXEL_MAX;
    dst[c] = (unsigned char)(byte_clip(b) + BYTE_ROUND);
  }
}

// CRT replay: tinted gray, scanlines, vignette and grain. Each thread
// processes one pixel in global memory. Integer noise depends only on
// (x, y, frame), so NumPy can reproduce it exactly.

__global__ void k_crt(const unsigned char *src, unsigned char *dst,
                      int w, int h, int frame, float amount, float scan,
                      float vignette, float noise, int rows,
                      float tr, float tg, float tb)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  float band = rows > NO_SCANLINES && y % rows == rows - 1 ? UNIT - scan : UNIT;
  float vig = crt_vignette(x, y, w, h, vignette);
  float grain = crt_grain(x, y, frame);
  float v = crt_luma(src + i, band, vig, grain, noise, amount);
  crt_tint(dst + i, v, tr, tg, tb);
}

// Animated crowd (F11, FULL only): hash each seat (column and row) to
// paint steps and people, with one writer per pixel and no atomics.
//
// A seat is cfg[CC_W] by cfg[CC_H] pixels. A person stands on the bright
// edge of the step and extends upward: torso, round head, hair and on
// some seats a waving flag. Each seat has a different sine phase. The
// scoring side jumps higher and faster while the goal boost is active.
//
// Far rows are darker. A head or flag can reach into the row above, so
// check CROWD_ROWS rows per pixel, painting back to front.

// Mix seat column and row into a deterministic hash.
__device__ unsigned int crowd_hash(int c, int r)
{
  unsigned int hsh = ((unsigned int)c * CROWD_HASH_C) ^
      ((unsigned int)r * CROWD_HASH_R);
  hsh ^= hsh >> CROWD_HASH_SHIFT_FIRST;
  hsh *= CROWD_HASH_MUL;
  hsh ^= hsh >> CROWD_HASH_SHIFT_LAST;
  return hsh;
}

// Copy a palette row into rgb, multiplied by var for shading.
__device__ void crowd_paint(const float *pal, int row, float var, float *rgb)
{
  rgb[RED] = pal[CH * row] * var;
  rgb[GREEN] = pal[CH * row + GREEN] * var;
  rgb[BLUE] = pal[CH * row + BLUE] * var;
}

// Vary shirt brightness deterministically by seat hash.
__device__ float crowd_var(unsigned int hsh, const float *cfg)
{
  return cfg[CC_VAR_MIN] + cfg[CC_VAR_RANGE]
         * (float)((hsh >> CROWD_VAR_SHIFT) % CROWD_FULL) * CROWD_SPREAD;
}

// Torso half-width at this height, narrowing toward the shoulders.
__device__ float crowd_half(float up, const float *cfg)
{
  float half = cfg[CC_BODY_W] * HALF;
  if (up > cfg[CC_BODY_H] - CROWD_SHOULDER)
    return half - CROWD_SHOULDER * HALF;
  return half;
}

// Jump height in pixels (0 to amplitude), phase-shifted per seat.
__device__ float crowd_jump(unsigned int hsh, float t, float boost,
                            int team, int side, const float *cfg)
{
  float phase = (float)(hsh % CROWD_PHASE_TOP) * CROWD_PHASE;
  float amp = cfg[CC_JUMP] * (CROWD_JUMP_LOW + CROWD_JUMP_SPREAD
              * (float)((hsh / CROWD_JUMP_DIVISOR) % CROWD_FULL) * CROWD_SPREAD);
  float hz = cfg[CC_HZ];
  if (team == side)
  {  // scoring side
    amp += cfg[CC_GOAL_JUMP] * boost;
    hz += cfg[CC_GOAL_HZ] * boost;
  }
  return amp * (HALF + HALF * sinf(t * hz + phase));
}

__device__ __forceinline__ bool crowd_torso(float dx, float up,
    unsigned int hsh, const float *cfg, const float *pal, int team, float *rgb)
{
  float body_h = cfg[CC_BODY_H];
  if (!(up >= ZERO && up <= body_h && fabsf(dx) <= crowd_half(up, cfg)))
    return false;
  float var = crowd_var(hsh, cfg);
  if (up > body_h - cfg[CC_SHOULDER_EDGE])
    var *= cfg[CC_SHOULDER_SHADE];
  crowd_paint(pal, CP_SHIRT_A + team, var, rgb);
  return true;
}

__device__ __forceinline__ void crowd_head_color(float d2, float dy, float r,
    unsigned int hsh, const float *cfg, const float *pal, float *rgb)
{
  float inner = r - cfg[CC_OUTLINE];
  int hair = CP_HAIR + (int)((hsh >> CROWD_HAIR_SHIFT) % CROWD_HAIRS);
  int skin = CP_SKIN + (int)((hsh >> CROWD_SKIN_SHIFT) % CROWD_SKINS);
  if (dy < -cfg[CC_HEAD_CUT] * r)
    crowd_paint(pal, hair, crowd_var(hsh, cfg), rgb);
  else if (d2 > inner * inner)
    crowd_paint(pal, CP_OUTLINE, UNIT, rgb);
  else
    crowd_paint(pal, skin, UNIT, rgb);
}

// Paint and report a hit on the torso, head or hair.
__device__ bool crowd_person(float lx, float up, unsigned int hsh,
                            const float *cfg, const float *pal, int team,
                            float *rgb)
{
  float centre = cfg[CC_W] * HALF;
  float dx = lx - centre;
  if (crowd_torso(dx, up, hsh, cfg, pal, team, rgb)) return true;
  float r = cfg[CC_HEAD_R];
  float dy = up - (cfg[CC_BODY_H] + r * CROWD_HEAD_OFFSET);
  float d2 = dx * dx + dy * dy;
  if (d2 > r * r) return false;
  crowd_head_color(d2, dy, r, hsh, cfg, pal, rgb);
  return true;
}

__device__ __forceinline__ void crowd_cloth(float lx, float up, float top,
    float t, unsigned int hsh, const float *cfg, const float *pal, int team,
    float *rgb)
{
  if (up < top - cfg[CC_FLAG_H] || up > top) return;
  float phase = (float)(hsh % CROWD_PHASE_TOP) * CROWD_PHASE;
  float wave = cfg[CC_WAVE] * sinf(t * CROWD_FLAG_HZ + phase
                                  + (up - top) * CROWD_FLAG_CURVE);
  float fx = lx + cfg[CC_FLAG_W] * HALF - wave;
  if (fx < ZERO || fx >= cfg[CC_FLAG_W]) return;
  int stripe = ((int)(fx * CROWD_STRIPES / cfg[CC_FLAG_W]) & CROWD_ODD_BIT);
  crowd_paint(pal, stripe ? CP_FLAG_WHITE : CP_FLAG_A + team, UNIT, rgb);
}

// Flag, if present: pole above the head and two-color cloth with a
// sinusoidal displacement that varies by row.
__device__ void crowd_flag(unsigned int hsh, float lx, float up, float t,
                          const float *cfg, const float *pal, int team,
                          float *rgb)
{
  if ((int)(hsh % (unsigned int)cfg[CC_EVERY]) != CROWD_FLAG_BUCKET) return;
  float centre = cfg[CC_W] * HALF;
  float base = cfg[CC_BODY_H] + cfg[CC_HEAD_R];
  float top = base + cfg[CC_POLE_H];
  if (up >= base && up <= top && fabsf(lx - centre) <= CROWD_POLE_W)
    crowd_paint(pal, CP_POLE, UNIT, rgb);
  else
    crowd_cloth(lx - centre, up, top, t, hsh, cfg, pal, team, rgb);
}

// Paint the step floor and dark riser with a bright top edge.
__device__ void crowd_step(int y, int row, const float *cfg,
                           const float *pal, float *rgb)
{
  float edge = (float)(row + 1) * cfg[CC_H] - cfg[CC_STEP];
  int tone = (float)y >= edge ? CP_RISER : CP_TREAD;
  if ((float)y >= edge && (float)y < edge + CROWD_RISER)
    tone = CP_EDGE;
  rgb[RED] = pal[CH * tone];
  rgb[GREEN] = pal[CH * tone + GREEN];
  rgb[BLUE] = pal[CH * tone + BLUE];
}

// Depth shading: higher rows are farther away.
__device__ float crowd_shade(int row, int rows, const float *cfg)
{
  float far = (float)row / (float)(rows > 1 ? rows - 1 : 1);
  return cfg[CC_SHADE_TOP]
         + (cfg[CC_SHADE_BOTTOM] - cfg[CC_SHADE_TOP]) * far;
}

__device__ __forceinline__ void crowd_seat(int x, int y, int r, int team,
    float t, int side, float boost, const float *cfg, const float *pal, float *rgb)
{
  float stagger = (float)((r & CROWD_ODD_BIT) * ((int)cfg[CC_W] / CROWD_HALVES));
  float cx = (float)x + stagger;
  int c = (int)(cx / cfg[CC_W]);
  float lx = cx - (float)c * cfg[CC_W];
  unsigned int hsh = crowd_hash(c, r);
  if ((float)(hsh % CROWD_FULL) >= cfg[CC_FILL]) return;
  float up = (float)(r + 1) * cfg[CC_H] - cfg[CC_STEP] - (float)y
             - crowd_jump(hsh, t, boost, team, side, cfg);
  if (!crowd_person(lx, up, hsh, cfg, pal, team, rgb))
    crowd_flag(hsh, lx, up, t, cfg, pal, team, rgb);
}

__device__ __forceinline__ void crowd_write(
    unsigned char *dst, const float *rgb, float shade)
{
  for (int c = 0; c < CH; ++c)
  {
    float v = rgb[c] * shade * PIXEL_MAX;
    dst[c] = (unsigned char)(byte_clip(v) + BYTE_ROUND);
  }
}

// Paint the stands: one thread per pixel, border check and global memory.
__global__ void k_crowd(const unsigned char *src, unsigned char *dst,
                          int w, int h, float t, int side, float boost,
                          const float *cfg, const float *pal)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int row = (int)((float)y / cfg[CC_H]), rows = (int)((float)h / cfg[CC_H]);
  float rgb[CH];
  crowd_step(y, row, cfg, pal, rgb);
  int team = (x < w / CROWD_HALVES) ? CROWD_LEFT : CROWD_RIGHT;
  for (int k = 0; k < CROWD_ROWS; ++k)
    crowd_seat(x, y, row + k, team, t, side, boost, cfg, pal, rgb);
  crowd_write(dst + (y * w + x) * CH, rgb, crowd_shade(row, rows, cfg));
}
