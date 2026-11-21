// Post-processing kernels for the football game.
//
// Image kernels use one thread per pixel, 2D indexing with
// blockIdx/blockDim/threadIdx and an early border check. Buffers are in
// global memory. Use atomics when threads update the same output element.
//
// Images: packed RGB bytes, no row padding, i = (y*w + x)*3.
// Intermediate light buffers: three float channels per pixel.
// Unless otherwise noted, w and h describe the output.
#define CH 3

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

// Glow: scale the halo by saturation, with a peak gain of 1.
// White signs and lines produce no halo; saturated sparks and ice do.
#define GLOW_SAT_GAIN 1.5f
// Keep only samples above the threshold, one pixel per 2x2 block.
// The halo does not need full-resolution detail.
__global__ void bright_pass(const unsigned char *src, float *dst,
                            int hw, int hh, int w, float threshold)
{
  int x, y;
  if (!pixel_coords(x, y, hw, hh)) return;
  int i = ((2 * y) * w + 2 * x) * CH;
  float l = (0.299f * src[i] + 0.587f * src[i + 1]
             + 0.114f * src[i + 2]) / 255.0f;
  float k = l > threshold ? (l - threshold) / (1.0f - threshold) : 0.0f;
  float hi = fmaxf(src[i], fmaxf(src[i + 1], src[i + 2])) / 255.0f;
  float lo = fminf(src[i], fminf(src[i + 1], src[i + 2])) / 255.0f;
  float sat = hi > 0.0f ? (hi - lo) / hi : 0.0f;
  k *= fminf(sat * GLOW_SAT_GAIN, 1.0f);  // suppress halos on white
  int o = (y * hw + x) * CH;
  dst[o] = src[i] * k / 255.0f;
  dst[o + 1] = src[i + 1] * k / 255.0f;
  dst[o + 2] = src[i + 2] * k / 255.0f;
}

// Horizontal blur of the float halo buffer.
__global__ void glow_rows(const float *src, float *dst, int w, int h, int r)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int x0 = max(0, x - r), x1 = min(w - 1, x + r);
  float a0 = 0.0f, a1 = 0.0f, a2 = 0.0f;
  for (int k = x0; k <= x1; ++k)
  {
    int i = (y * w + k) * CH;
    a0 += src[i]; a1 += src[i + 1]; a2 += src[i + 2];
  }
  float n = (float)(x1 - x0 + 1); int o = (y * w + x) * CH;
  dst[o] = a0 / n; dst[o + 1] = a1 / n; dst[o + 2] = a2 / n;
}

// Vertical blur of the float halo buffer.
__global__ void glow_cols(const float *src, float *dst, int w, int h, int r)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int y0 = max(0, y - r), y1 = min(h - 1, y + r);
  float a0 = 0.0f, a1 = 0.0f, a2 = 0.0f;
  for (int k = y0; k <= y1; ++k)
  {
    int i = (k * w + x) * CH;
    a0 += src[i]; a1 += src[i + 1]; a2 += src[i + 2];
  }
  float n = (float)(y1 - y0 + 1); int o = (y * w + x) * CH;
  dst[o] = a0 / n; dst[o + 1] = a1 / n; dst[o + 2] = a2 / n;
}

// Final composition: exposure, gamma, additive halo and vignette.
__global__ void composite(const unsigned char *base, const float *glow,
                          unsigned char *out, int w, int h, int gw, int gh,
                          float exposure, float gamma, float vignette,
                          float glow_strength)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int gx = x / 2 < gw ? x / 2 : gw - 1;
  int gy = y / 2 < gh ? y / 2 : gh - 1;
  int gi = (gy * gw + gx) * CH;
  int i = (y * w + x) * CH;
  float cx = (x / (float)w) - 0.5f;
  float cy = (y / (float)h) - 0.5f;
  float d = sqrtf(cx * cx + cy * cy) * 1.41421356f;
  float v = 1.0f - vignette * d * d;
  float c[CH];
  for (int k = 0; k < CH; ++k)
  {
    float p = (base[i + k] / 255.0f) * exposure
              + glow[gi + k] * glow_strength;
    p = powf(p > 0.0f ? p : 0.0f, gamma) * v;
    p = p > 1.0f ? 1.0f : p;
    c[k] = p * 255.0f;
  }
  out[i] = (unsigned char)c[0];
  out[i + 1] = (unsigned char)c[1];
  out[i + 2] = (unsigned char)c[2];
}

// Each particle spreads light over a square of side `size` pixels.
// Use atomicAdd so overlapping writes to a pixel are not lost.
__global__ void splat_particles(const float *pos, const float *col, int n,
                                float *acc, int w, int h, float gain)
{
  int p;
  if (!thread_index(p, n)) return;
  int cx = (int)pos[2 * p];
  int cy = (int)pos[2 * p + 1];
  int r = (int)col[4 * p + 3];
  float cr = col[4 * p], cg = col[4 * p + 1], cb = col[4 * p + 2];
  for (int y = cy - r; y <= cy + r; ++y)
  {
    if (y < 0 || y >= h) continue;
    for (int x = cx - r; x <= cx + r; ++x)
    {
      if (x < 0 || x >= w) continue;
      int i = (y * w + x) * CH;
      atomicAdd(&acc[i], cr * gain);
      atomicAdd(&acc[i + 1], cg * gain);
      atomicAdd(&acc[i + 2], cb * gain);
    }
  }
}

// Goal confetti: one thread per piece, painting its rectangle.
// Blend with the background to preserve paper colors over the pitch.
// Atomics accumulate the difference; add_light adds it to the image.
__global__ void confetti(const float *pos, const float *col, int n,
                         const unsigned char *img, float *acc, int w, int h,
                         float gain)
{
  int p;
  if (!thread_index(p, n)) return;
  int cx = (int)pos[2 * p];
  int cy = (int)pos[2 * p + 1];
  int hw = (int)col[5 * p + 3];  // paper half-width
  int hh = (int)col[5 * p + 4];  // paper half-height (near 0 edge-on)
  float tr = col[5 * p], tg = col[5 * p + 1], tb = col[5 * p + 2];
  for (int y = cy - hh; y <= cy + hh; ++y)
  {
    if (y < 0 || y >= h) continue;
    for (int x = cx - hw; x <= cx + hw; ++x)
    {
      if (x < 0 || x >= w) continue;
      int i = (y * w + x) * CH;
      atomicAdd(&acc[i], (tr - img[i] / 255.0f) * gain);
      atomicAdd(&acc[i + 1], (tg - img[i + 1] / 255.0f) * gain);
      atomicAdd(&acc[i + 2], (tb - img[i + 2] / 255.0f) * gain);
    }
  }
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
    float p = base[i + k] / 255.0f + acc[i + k] * gain;
    p = p > 1.0f ? 1.0f : p;
    out[i + k] = (unsigned char)(p * 255.0f);
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
  int sy = y + (int)(amp * 0.5f * cosf(x / period + phase));
  sx = min(max(sx, 0), w - 1);
  sy = min(max(sy, 0), h - 1);
  int i = (y * w + x) * CH;
  int j = (sy * w + sx) * CH;
  out[i] = src[j]; out[i + 1] = src[j + 1]; out[i + 2] = src[j + 2];
}

// Linear blend of two images (alpha 0 = a, alpha 1 = b).
__global__ void mix_layers(const unsigned char *a, const unsigned char *b,
                           unsigned char *out, int w, int h, float alpha)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  for (int k = 0; k < CH; ++k)
    out[i + k] = (unsigned char)(a[i + k] * (1.0f - alpha)
                                 + b[i + k] * alpha);
}

// Use atomics to count luma in 256 bins: threads can share a bin.
__global__ void luma_hist(const unsigned char *src, int *hist, int w, int h)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  float l = (0.299f * src[i] + 0.587f * src[i + 1]
             + 0.114f * src[i + 2]);
  int bin = (int)l;
  bin = bin < 0 ? 0 : (bin > 255 ? 255 : bin);
  atomicAdd(&hist[bin], 1);
}

// Stretch contrast between two levels computed on the CPU. Apply the
// vignette here to avoid an extra pass when glow is off.
__global__ void stretch(const unsigned char *src, unsigned char *out, int w,
                        int h, float lo, float hi, float vignette)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  float span = hi - lo > 1.0f ? hi - lo : 1.0f;
  float cx = (x / (float)w) - 0.5f;
  float cy = (y / (float)h) - 0.5f;
  float d = sqrtf(cx * cx + cy * cy) * 1.41421356f;
  float v = 1.0f - vignette * d * d;
  for (int k = 0; k < CH; ++k)
  {
    float p = (src[i + k] - lo) / span;
    p = p < 0.0f ? 0.0f : (p > 1.0f ? 1.0f : p);
    out[i + k] = (unsigned char)(p * v * 255.0f);
  }
}

// F1 image primitives: one thread per pixel, 2D indices, early border
// checks and global memory buffers.

#define GRAY_RED 0.299f    // BT.601 red luma weight
#define GRAY_GREEN 0.587f  // BT.601 green luma weight
#define GRAY_BLUE 0.114f   // BT.601 blue luma weight
#define GRAY_ROUND 0.5f    // round to nearest byte

// One thread per pixel; the border check protects global memory reads.
__global__ void k_gray(const unsigned char *src, unsigned char *dst,
                       int width, int height)
{
  int x, y;
  if (!pixel_coords(x, y, width, height)) return;
  int i = (y * width + x) * CH;
  float luma = GRAY_RED * src[i] + GRAY_GREEN * src[i + 1]
               + GRAY_BLUE * src[i + 2];
  unsigned char gray = (unsigned char)(luma + GRAY_ROUND);
  dst[i] = dst[i + 1] = dst[i + 2] = gray;
}

// Negative: subtract each channel from 255.
__global__ void k_invert(const unsigned char *src, unsigned char *dst,
                         int w, int h)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  dst[i] = 255 - src[i];
  dst[i + 1] = 255 - src[i + 1];
  dst[i + 2] = 255 - src[i + 2];
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
    v = v < 0.0f ? 0.0f : (v > 255.0f ? 255.0f : v);
    dst[i + c] = (unsigned char)(v + 0.5f);
  }
}

// Tint: multiply by a color (0..1 per channel).
__global__ void k_tint(const unsigned char *src, unsigned char *dst,
                       int w, int h, float r, float g, float b)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  dst[i] = (unsigned char)(src[i] * r + 0.5f);
  dst[i + 1] = (unsigned char)(src[i + 1] * g + 0.5f);
  dst[i + 2] = (unsigned char)(src[i + 2] * b + 0.5f);
}

// Rotate about the center using nearest-neighbor sampling.
// Samples outside the image become black.
__global__ void k_rotate(const unsigned char *src, unsigned char *dst,
                         int w, int h, float angle)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  float cx = (w - 1) * 0.5f, cy = (h - 1) * 0.5f;
  float c = cosf(angle), s = sinf(angle);
  float dx = x - cx, dy = y - cy;
  int sx = (int)(cx + c * dx + s * dy + 0.5f);
  int sy = (int)(cy - s * dx + c * dy + 0.5f);
  int o = (y * w + x) * CH;
  if (sx < 0 || sx >= w || sy < 0 || sy >= h)
  {
    dst[o] = 0; dst[o + 1] = 0; dst[o + 2] = 0;
    return;
  }
  int i = (sy * w + sx) * CH;
  dst[o] = src[i];
  dst[o + 1] = src[i + 1];
  dst[o + 2] = src[i + 2];
}

// Ice power (F11): two passes, one image upload and one download.
// k_ice_edges writes Sobel magnitudes in global memory and uses atomicMax
// for the maximum. Nonnegative float bits sort in the same order as floats.
// k_ice_apply uses that maximum, adds edges, tints and blends, preserving
// the rounding of the original standalone passes.

// Normalized luma of one pixel for the ice edges.
__device__ float ice_gray(const unsigned char *src, int i)
{
  return (0.299f * src[i] + 0.587f * src[i + 1] + 0.114f * src[i + 2]) /
      255.0f;
}

__global__ void k_ice_edges(const unsigned char *src, float *edges,
                            unsigned int *top, int w, int h)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int x0 = max(0, x - 1), x1 = min(w - 1, x + 1);
  int y0 = max(0, y - 1), y1 = min(h - 1, y + 1);
  float a = ice_gray(src, (y0 * w + x0) * CH);
  float b = ice_gray(src, (y0 * w + x) * CH);
  float c = ice_gray(src, (y0 * w + x1) * CH);
  float d = ice_gray(src, (y * w + x0) * CH);
  float f = ice_gray(src, (y * w + x1) * CH);
  float g = ice_gray(src, (y1 * w + x0) * CH);
  float hh = ice_gray(src, (y1 * w + x) * CH);
  float k = ice_gray(src, (y1 * w + x1) * CH);
  float gx = (c + 2.0f * f + k) - (a + 2.0f * d + g);
  float gy = (g + 2.0f * hh + k) - (a + 2.0f * b + c);
  float v = sqrtf(gx * gx + gy * gy) * 0.25f;
  edges[y * w + x] = v;
  atomicMax(top, __float_as_uint(v));
}

__global__ void k_ice_apply(const unsigned char *src, const float *edges,
                            const unsigned int *top, unsigned char *dst,
                            int w, int h, float strength, float tr,
                            float tg, float tb, float amount)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  float max_value = __uint_as_float(top[0]);
  float v = edges[y * w + x] / (max_value > 0.0f ? max_value : 1.0f);
  v = v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
  float edge = (float)(unsigned char)(v * 255.0f + 0.5f);
  float tint[3];
  tint[0] = tr; tint[1] = tg; tint[2] = tb;
  for (int c = 0; c < CH; ++c)
  {
    float lit = src[i + c] + edge * strength;
    lit = lit < 0.0f ? 0.0f : (lit > 255.0f ? 255.0f : lit);
    float glow = (float)(unsigned char)(lit + 0.5f);
    float blue = (float)(unsigned char)(glow * tint[c] + 0.5f);
    float mixed = glow * (1.0f - amount) + blue * amount;
    dst[i + c] = (unsigned char)mixed;
  }
}

// Night and blackout (F3/F4): one thread per pixel with an early border
// check. Read lights (x, y, radius, power) from global memory and multiply
// the pixel by their combined light. With limit > 0 each lamp adds a
// fraction of the remaining headroom. With limit == 0 the sum is uncapped.
#define SPOT_MAX 8  // maximum lights per pixel
__global__ void k_spotlights(const unsigned char *src, unsigned char *dst,
                             int w, int h, const float *lights, int n,
                             float ambient, float tr, float tg, float tb,
                             float limit)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  float light = ambient;
  for (int k = 0; k < n && k < SPOT_MAX; ++k)
  {
    float dx = x - lights[4 * k];
    float dy = y - lights[4 * k + 1];
    float r = lights[4 * k + 2];
    float power = lights[4 * k + 3];
    float d2 = (dx * dx + dy * dy) / (r * r);
    if (d2 < 1.0f)
    {
      float fall = 1.0f - d2;  // smooth falloff from the center
      if (limit > 0.0f)
      {
        light += power * fall * fall * (limit - light);
      }
      else
      {
        light += power * fall * fall;
      }
    }
  }
  int i = (y * w + x) * CH;
  float r = src[i] * light * tr;
  float g = src[i + 1] * light * tg;
  float b = src[i + 2] * light * tb;
  r = r < 0.0f ? 0.0f : (r > 255.0f ? 255.0f : r);
  g = g < 0.0f ? 0.0f : (g > 255.0f ? 255.0f : g);
  b = b < 0.0f ? 0.0f : (b > 255.0f ? 255.0f : b);
  dst[i] = (unsigned char)(r + 0.5f);
  dst[i + 1] = (unsigned char)(g + 0.5f);
  dst[i + 2] = (unsigned char)(b + 0.5f);
}

// Hot air around the ball during fire power. Pixels outside the radius
// are copied unchanged. The launch size is independent of the radius.
#define HEAT_FREQ_Y 0.12f  // vertical wave radians per pixel
#define HEAT_SPEED_Y 18.0f  // vertical wave radians per second
#define HEAT_FREQ_X 0.09f  // horizontal wave radians per pixel
#define HEAT_SPEED_X 14.0f  // horizontal wave radians per second
#define HEAT_LATERAL 0.4f  // scale the horizontal displacement
__global__ void k_heat_distort(const unsigned char *src, unsigned char *dst,
                               int w, int h, float cx, float cy, float rad,
                               float t, float amp)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  float dx = x - cx, dy = y - cy;
  float d = sqrtf(dx * dx + dy * dy);
  int sx = x, sy = y;
  if (d < rad)
  {
    float fall = 1.0f - d / rad;  // fall off to zero at the radius
    sx = x + (int)(amp * sinf(y * HEAT_FREQ_Y + t * HEAT_SPEED_Y) * fall);
    sy = y + (int)(amp * HEAT_LATERAL
                   * sinf(x * HEAT_FREQ_X + t * HEAT_SPEED_X) * fall);
  }
  sx = sx < 0 ? 0 : (sx >= w ? w - 1 : sx);  // clamp to the image border
  sy = sy < 0 ? 0 : (sy >= h ? h - 1 : sy);
  int i = (y * w + x) * CH;
  int j = (sy * w + sx) * CH;
  dst[i] = src[j];
  dst[i + 1] = src[j + 1];
  dst[i + 2] = src[j + 2];
}

// Night luma histogram (F4): atomicAdd for the bins and atomicMax for
// the peak because threads can update the same global memory locations.
__global__ void k_luma_hist(const unsigned char *src, unsigned int *hist,
                            unsigned int *luma_max, int w, int h)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  float l = 0.299f * src[i] + 0.587f * src[i + 1] + 0.114f * src[i + 2];
  unsigned int bin = (unsigned int)(l + 0.5f);  // same rounding as k_gray
  atomicAdd(&hist[bin], 1u);
  atomicMax(luma_max, bin);
}

// ===========================================================================
// F5: replay
// ===========================================================================

// CRT replay: tinted gray, scanlines, vignette and grain. Each thread
// processes one pixel in global memory. Integer noise depends only on
// (x, y, frame), so NumPy can reproduce it exactly.
#define CRT_NOISE_MUL 2654435761u  // integer noise multiplier
#define CRT_NOISE_SHIFT 24  // keep the high bits of the noise
#define CRT_DIAGONAL 0.70710678f  // 1/sqrt(2): normalize the vignette

__global__ void k_crt(const unsigned char *src, unsigned char *dst,
                      int w, int h, int frame, float amount, float scan,
                      float vignette, float noise, int rows,
                      float tr, float tg, float tb)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  float l = (0.299f * src[i] + 0.587f * src[i + 1]
             + 0.114f * src[i + 2]) / 255.0f;
  // Darken every `rows`-th row to simulate CRT scanlines.
  float band = (rows > 0 && y % rows == rows - 1) ? (1.0f - scan) : 1.0f;
  // Radial vignette: 0 at the center, 1 at the corners.
  float nx = 2.0f * x / (float)(w > 1 ? w - 1 : 1) - 1.0f;
  float ny = 2.0f * y / (float)(h > 1 ? h - 1 : 1) - 1.0f;
  float d = sqrtf(nx * nx + ny * ny) * CRT_DIAGONAL;
  float vig = 1.0f - vignette * d * d;
  // Pseudorandom grain with intentional unsigned overflow.
  unsigned int seed = (unsigned int)(x * 1973 + y * 9277 + frame * 26699) *
      CRT_NOISE_MUL;
  float grain = (float)((seed >> CRT_NOISE_SHIFT) & 255u) / 255.0f - 0.5f;
  float crt = l * band * vig + grain * noise;
  float v = l + (crt - l) * amount;  // amount 0 keeps the original luma
  float out[CH];
  out[0] = v * tr; out[1] = v * tg; out[2] = v * tb;
  for (int c = 0; c < CH; ++c)
  {
    float b = out[c] * 255.0f;
    b = b < 0.0f ? 0.0f : (b > 255.0f ? 255.0f : b);
    dst[i + c] = (unsigned char)(b + 0.5f);
  }
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
#define CROWD_HASH_C 73856093u  // column hash prime
#define CROWD_HASH_R 19349663u  // row hash prime
#define CROWD_ROWS 2  // rows checked per pixel
#define CROWD_FLAG_HZ 3.2f  // flag wave radians per second
#define CROWD_FLAG_CURVE 0.30f  // flag curvature in radians per vertical pixel
#define CROWD_SHOULDER 2.0f  // torso narrowing at the shoulders in pixels
#define CROWD_POLE_W 1.0f  // flagpole half-width in pixels
#define CROWD_RISER 1.0f  // bright step edge in pixels
#define CROWD_JUMP_LOW 0.4f  // minimum jump as a fraction of the peak
#define CROWD_JUMP_SPREAD 0.6f  // extra jump fraction from the hash
#define CROWD_PHASE 0.01f  // phase radians per hash unit
#define CROWD_PHASE_TOP 628u  // roughly one cycle in hash units
#define CROWD_SPREAD 0.01f  // scale a hash bucket to 0..1
#define CROWD_SKINS 3  // skin tones in the palette
#define CROWD_HAIRS 3  // hair tones in the palette
#define CROWD_FULL 100u  // number of hash buckets

// Indices into the configuration array supplied by the host.
#define CC_W 0  // seat width in pixels
#define CC_H 1  // seat height in pixels
#define CC_JUMP 2  // jump height in pixels
#define CC_HZ 3  // jump radians per second
#define CC_GOAL_JUMP 4  // extra jump height for the scoring side
#define CC_GOAL_HZ 5  // extra jump radians per second
#define CC_WAVE 6  // flag wave amplitude in pixels
#define CC_FLAG_W 7  // flag width in pixels
#define CC_FLAG_H 8  // flag height in pixels
#define CC_FILL 9  // percent of occupied seats
#define CC_EVERY 10  // one flag every N seats
#define CC_BODY_W 11  // torso width in pixels
#define CC_BODY_H 12  // torso height in pixels
#define CC_HEAD_R 13  // head radius in pixels
#define CC_STEP 14  // step height in pixels
#define CC_POLE_H 15  // pole height above the shoulder in pixels
#define CC_SHADE_TOP 16  // shade factor for the farthest row
#define CC_SHADE_BOTTOM 17  // shade factor for the nearest row
#define CC_VAR_MIN 18  // minimum shirt brightness
#define CC_VAR_RANGE 19  // extra brightness from the hash
#define CC_HEAD_CUT 20  // fraction of the head covered by hair
#define CC_OUTLINE 21  // dark outline width in pixels
#define CC_SHOULDER_EDGE 22  // shoulder edge width in pixels
#define CC_SHOULDER_SHADE 23  // shoulder edge shade factor

// Palette rows (one RGB triple each).
#define CP_SHIRT_A 0  // left team shirt
#define CP_SHIRT_B 1  // right team shirt
#define CP_SKIN 2  // first of CROWD_SKINS skin tones
#define CP_HAIR 5  // first of CROWD_HAIRS hair tones
#define CP_TREAD 8  // step floor
#define CP_RISER 9  // dark riser
#define CP_EDGE 10  // bright step edge
#define CP_POLE 11  // flagpole
#define CP_FLAG_WHITE 12  // white flag stripe
#define CP_FLAG_A 13  // left team flag
#define CP_FLAG_B 14  // right team flag
#define CP_OUTLINE 15  // dark head outline

// Mix seat column and row into a deterministic hash.
__device__ unsigned int crowd_hash(int c, int r)
{
  unsigned int hsh = ((unsigned int)c * CROWD_HASH_C) ^
      ((unsigned int)r * CROWD_HASH_R);
  hsh ^= hsh >> 13;
  hsh *= 1274126177u;
  hsh ^= hsh >> 16;
  return hsh;
}

// Copy a palette row into rgb, multiplied by var for shading.
__device__ void crowd_paint(const float *pal, int row, float var, float *rgb)
{
  rgb[0] = pal[3 * row] * var;
  rgb[1] = pal[3 * row + 1] * var;
  rgb[2] = pal[3 * row + 2] * var;
}

// Vary shirt brightness deterministically by seat hash.
__device__ float crowd_var(unsigned int hsh, const float *cfg)
{
  return cfg[CC_VAR_MIN] + cfg[CC_VAR_RANGE]
         * (float)((hsh >> 13) % CROWD_FULL) * CROWD_SPREAD;
}

// Torso half-width at this height, narrowing toward the shoulders.
__device__ float crowd_half(float up, const float *cfg)
{
  float half = cfg[CC_BODY_W] * 0.5f;
  if (up > cfg[CC_BODY_H] - CROWD_SHOULDER)
    return half - CROWD_SHOULDER * 0.5f;
  return half;
}

// Jump height in pixels (0 to amplitude), phase-shifted per seat.
__device__ float crowd_jump(unsigned int hsh, float t, float boost,
                            int team, int side, const float *cfg)
{
  float phase = (float)(hsh % CROWD_PHASE_TOP) * CROWD_PHASE;
  float amp = cfg[CC_JUMP] * (CROWD_JUMP_LOW + CROWD_JUMP_SPREAD
              * (float)((hsh / 7u) % CROWD_FULL) * CROWD_SPREAD);
  float hz = cfg[CC_HZ];
  if (team == side)
  {  // scoring side
    amp += cfg[CC_GOAL_JUMP] * boost;
    hz += cfg[CC_GOAL_HZ] * boost;
  }
  return amp * (0.5f + 0.5f * sinf(t * hz + phase));
}

// Test whether (lx, up) hits the torso, head or hair. Return 1 on a hit
// and write its color into rgb.
__device__ int crowd_person(float lx, float up, unsigned int hsh,
                            const float *cfg, const float *pal, int team,
                            float *rgb)
{
  float centre = cfg[CC_W] * 0.5f;
  float dx = lx - centre;
  float body_h = cfg[CC_BODY_H];
  if (up >= 0.0f && up <= body_h && fabsf(dx) <= crowd_half(up, cfg))
  {
    float var = crowd_var(hsh, cfg);
    if (up > body_h - cfg[CC_SHOULDER_EDGE])  // shoulder edge
      var *= cfg[CC_SHOULDER_SHADE];
    crowd_paint(pal, CP_SHIRT_A + team, var, rgb);
    return 1;
  }
  float dy = up - (body_h + cfg[CC_HEAD_R] * 0.8f);
  float r = cfg[CC_HEAD_R];
  float d2 = dx * dx + dy * dy;
  if (d2 > r * r)
    return 0;
  if (dy < -cfg[CC_HEAD_CUT] * r)
  {  // hair at the top of the head
    crowd_paint(pal, CP_HAIR + (int)((hsh >> 9) % CROWD_HAIRS),
                crowd_var(hsh, cfg), rgb);
    return 1;
  }
  float inner = r - cfg[CC_OUTLINE];
  if (d2 > inner * inner)
  {  // dark outline of the face
    crowd_paint(pal, CP_OUTLINE, 1.0f, rgb);
    return 1;
  }
  crowd_paint(pal, CP_SKIN + (int)((hsh >> 5) % CROWD_SKINS), 1.0f, rgb);
  return 1;
}

// Flag, if present: pole above the head and two-color cloth with a
// sinusoidal displacement that varies by row.
__device__ int crowd_flag(unsigned int hsh, float lx, float up, float t,
                          const float *cfg, const float *pal, int team,
                          float *rgb)
{
  if ((int)(hsh % (unsigned int)cfg[CC_EVERY]) != 0)
    return 0;
  float centre = cfg[CC_W] * 0.5f;
  float base = cfg[CC_BODY_H] + cfg[CC_HEAD_R];
  float top = base + cfg[CC_POLE_H];
  if (up >= base && up <= top && fabsf(lx - centre) <= CROWD_POLE_W)
  {
    crowd_paint(pal, CP_POLE, 1.0f, rgb);  // flagpole
    return 1;
  }
  if (up < top - cfg[CC_FLAG_H] || up > top)
    return 0;
  float phase = (float)(hsh % CROWD_PHASE_TOP) * CROWD_PHASE;
  float wave = cfg[CC_WAVE] * sinf(t * CROWD_FLAG_HZ + phase
                                  + (up - top) * CROWD_FLAG_CURVE);
  float fx = lx - centre + cfg[CC_FLAG_W] * 0.5f - wave;
  if (fx < 0.0f || fx >= cfg[CC_FLAG_W])
    return 0;
  int stripe = ((int)(fx * 3.0f / cfg[CC_FLAG_W]) & 1);
  crowd_paint(pal, stripe ? CP_FLAG_WHITE : CP_FLAG_A + team, 1.0f, rgb);
  return 1;
}

// Paint the step floor and dark riser with a bright top edge.
__device__ void crowd_step(int y, int row, const float *cfg,
                           const float *pal, float *rgb)
{
  float edge = (float)(row + 1) * cfg[CC_H] - cfg[CC_STEP];
  int tone = (float)y >= edge ? CP_RISER : CP_TREAD;
  if ((float)y >= edge && (float)y < edge + CROWD_RISER)
    tone = CP_EDGE;
  rgb[0] = pal[3 * tone];
  rgb[1] = pal[3 * tone + 1];
  rgb[2] = pal[3 * tone + 2];
}

// Depth shading: higher rows are farther away.
__device__ float crowd_shade(int row, int rows, const float *cfg)
{
  float far = (float)row / (float)(rows > 1 ? rows - 1 : 1);
  return cfg[CC_SHADE_TOP]
         + (cfg[CC_SHADE_BOTTOM] - cfg[CC_SHADE_TOP]) * far;
}

// Paint the stands: one thread per pixel, border check and global memory.
__global__ void k_crowd(const unsigned char *src, unsigned char *dst,
                          int w, int h, float t, int side, float boost,
                          const float *cfg, const float *pal)
{
  int x, y;
  if (!pixel_coords(x, y, w, h)) return;
  int i = (y * w + x) * CH;
  int row = (int)((float)y / cfg[CC_H]);
  int rows = (int)((float)h / cfg[CC_H]);
  float rgb[3];
  crowd_step(y, row, cfg, pal, rgb);  // step of the current row
  int team = (x < w / 2) ? 0 : 1;  // one team per half
  for (int k = 0; k < CROWD_ROWS; ++k)
  {
    int r = row + k;  // back to front
    float stagger = (float)((r & 1) * ((int)cfg[CC_W] / 2));
    float cx = (float)x + stagger;  // staggered rows
    int c = (int)(cx / cfg[CC_W]);
    float lx = cx - (float)c * cfg[CC_W];
    unsigned int hsh = crowd_hash(c, r);
    if ((float)(hsh % CROWD_FULL) >= cfg[CC_FILL])
      continue;  // empty seat
    float up = (float)(r + 1) * cfg[CC_H] - cfg[CC_STEP] - (float)y
               - crowd_jump(hsh, t, boost, team, side, cfg);
    if (crowd_person(lx, up, hsh, cfg, pal, team, rgb))
      continue;  // the person occludes the flag
    crowd_flag(hsh, lx, up, t, cfg, pal, team, rgb);
  }
  float shade = crowd_shade(row, rows, cfg);
  for (int c = 0; c < CH; ++c)
  {
    float v = rgb[c] * shade * 255.0f;
    v = v < 0.0f ? 0.0f : (v > 255.0f ? 255.0f : v);
    dst[i + c] = (unsigned char)(v + 0.5f);
  }
}
