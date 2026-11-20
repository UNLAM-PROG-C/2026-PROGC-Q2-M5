// Kernels de los efectos de imagen de Futbol De Cabeza.
//
// Estilo de la catedra: un hilo por pixel, indice 2D (x, y) calculado con
// blockIdx/blockDim/threadIdx, chequeo de bordes al principio, solo memoria
// global (sin memoria compartida) y atomicos donde dos hilos escriben el
// mismo pixel (particulas y luces).
//
// Convenciones:
//   - las imagenes son RGB de 8 bits, sin fila de relleno: i = (y*w + x)*3
//   - los buffers intermedios son float de 3 canales (luz acumulada)
//   - todo lo que recibe 'w' y 'h' es el tamano del buffer de salida
#define CH 3

// ---------------------------------------------------------------- desenfoque
// Promedio horizontal de una ventana de radio r (bordes recortados).
__global__ void blur_rows(const unsigned char *src, unsigned char *dst,
                          int w, int h, int r)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;              // chequeo de bordes
  int x0 = max(0, x - r);
  int x1 = min(w - 1, x + r);
  int a0 = 0, a1 = 0, a2 = 0, n = 0;
  for (int k = x0; k <= x1; ++k)
  {
    int i = (y * w + k) * CH;
    a0 += src[i]; a1 += src[i + 1]; a2 += src[i + 2];
    ++n;
  }
  int o = (y * w + x) * CH;
  dst[o] = (unsigned char)(a0 / n);
  dst[o + 1] = (unsigned char)(a1 / n);
  dst[o + 2] = (unsigned char)(a2 / n);
}

// Promedio vertical: completa el desenfoque de caja separable.
__global__ void blur_cols(const unsigned char *src, unsigned char *dst,
                          int w, int h, int r)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int y0 = max(0, y - r);
  int y1 = min(h - 1, y + r);
  int a0 = 0, a1 = 0, a2 = 0, n = 0;
  for (int k = y0; k <= y1; ++k)
  {
    int i = (k * w + x) * CH;
    a0 += src[i]; a1 += src[i + 1]; a2 += src[i + 2];
    ++n;
  }
  int o = (y * w + x) * CH;
  dst[o] = (unsigned char)(a0 / n);
  dst[o + 1] = (unsigned char)(a1 / n);
  dst[o + 2] = (unsigned char)(a2 / n);
}

// ---------------------------------------------------------------- brillo/glow
// Ganancia de saturacion del halo: lo blanco (carteles, lineas) no brilla y
// lo saturado (chispas, hielo) brilla mas. Se recorta a 1.
#define GLOW_SAT_GAIN 1.5f
// Pasa solo lo que supera el umbral, a media resolucion (muestrea 1 de cada
// 2x2 pixeles): el halo no necesita detalle.
__global__ void bright_pass(const unsigned char *src, float *dst,
                            int hw, int hh, int w, float threshold)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= hw || y >= hh) return;
  int i = ((2 * y) * w + 2 * x) * CH;
  float l = (0.299f * src[i] + 0.587f * src[i + 1]
             + 0.114f * src[i + 2]) / 255.0f;
  float k = l > threshold ? (l - threshold) / (1.0f - threshold) : 0.0f;
  float hi = fmaxf(src[i], fmaxf(src[i + 1], src[i + 2])) / 255.0f;
  float lo = fminf(src[i], fminf(src[i + 1], src[i + 2])) / 255.0f;
  float sat = hi > 0.0f ? (hi - lo) / hi : 0.0f;
  k *= fminf(sat * GLOW_SAT_GAIN, 1.0f);   // sin halo sobre lo blanco
  int o = (y * hw + x) * CH;
  dst[o] = src[i] * k / 255.0f;
  dst[o + 1] = src[i + 1] * k / 255.0f;
  dst[o + 2] = src[i + 2] * k / 255.0f;
}

// Desenfoque horizontal de un buffer float (el halo).
__global__ void glow_rows(const float *src, float *dst, int w, int h, int r)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int x0 = max(0, x - r), x1 = min(w - 1, x + r);
  float a0 = 0.0f, a1 = 0.0f, a2 = 0.0f;
  for (int k = x0; k <= x1; ++k)
  {
    int i = (y * w + k) * CH;
    a0 += src[i]; a1 += src[i + 1]; a2 += src[i + 2];
  }
  float n = (float)(x1 - x0 + 1);
  int o = (y * w + x) * CH;
  dst[o] = a0 / n; dst[o + 1] = a1 / n; dst[o + 2] = a2 / n;
}

// Desenfoque vertical del buffer float.
__global__ void glow_cols(const float *src, float *dst, int w, int h, int r)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int y0 = max(0, y - r), y1 = min(h - 1, y + r);
  float a0 = 0.0f, a1 = 0.0f, a2 = 0.0f;
  for (int k = y0; k <= y1; ++k)
  {
    int i = (k * w + x) * CH;
    a0 += src[i]; a1 += src[i + 1]; a2 += src[i + 2];
  }
  float n = (float)(y1 - y0 + 1);
  int o = (y * w + x) * CH;
  dst[o] = a0 / n; dst[o + 1] = a1 / n; dst[o + 2] = a2 / n;
}

// Composicion final: exposicion, gamma, halo sumado y vineta.
__global__ void composite(const unsigned char *base, const float *glow,
                          unsigned char *out, int w, int h, int gw, int gh,
                          float exposure, float gamma, float vignette,
                          float glow_strength)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
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

// ---------------------------------------------------------------- particulas
// Cada particula reparte su luz en un cuadrado de lado 'size' (en pixeles).
// Varios hilos pueden caer en el mismo pixel: atomicAdd.
__global__ void splat_particles(const float *pos, const float *col, int n,
                                float *acc, int w, int h, float gain)
{
  int p = blockIdx.x * blockDim.x + threadIdx.x;
  if (p >= n) return;                        // chequeo de bordes
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

// Confeti del festejo de gol: un hilo por papelito, que pinta su rectangulo.
// El papel se mezcla con la imagen (no se suma luz, si no el color se
// pierde sobre el cesped): el atomico guarda la diferencia contra el fondo y
// `add_light` la devuelve. Sin memoria compartida, como las particulas.
__global__ void confetti(const float *pos, const float *col, int n,
                         const unsigned char *img, float *acc, int w, int h,
                         float gain)
{
  int p = blockIdx.x * blockDim.x + threadIdx.x;
  if (p >= n) return;                        // chequeo de bordes
  int cx = (int)pos[2 * p];
  int cy = (int)pos[2 * p + 1];
  int hw = (int)col[5 * p + 3];              // medio ancho del papel
  int hh = (int)col[5 * p + 4];              // media altura (de canto, ~0)
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

// Suma la luz acumulada a la imagen (particulas y spotlights).
__global__ void add_light(const unsigned char *base, const float *acc,
                          unsigned char *out, int w, int h, float gain)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  for (int k = 0; k < CH; ++k)
  {
    float p = base[i + k] / 255.0f + acc[i + k] * gain;
    p = p > 1.0f ? 1.0f : p;
    out[i + k] = (unsigned char)(p * 255.0f);
  }
}

// ---------------------------------------------------------------- spotlights
// Luces aditivas con caida radial: 'lights' trae x, y, radio, intensidad,
// r, g, b. Se recorre al reves que antes: un hilo por pixel suma todas las
// lamparas (son pocas) y escribe el resultado, sin acumulador en la placa ni
// atomicas: antes habia un hilo por lampara pintando su circulo entero con
// atomicAdd sobre 8 MB de acumulador, y eso costaba decenas de milisegundos.
__global__ void k_light_pixels(const unsigned char *src, unsigned char *dst,
                               const float *lights, int n, int w, int h,
                               float gain)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  float red = 0.0f, green = 0.0f, blue = 0.0f;
  for (int k = 0; k < n; ++k)
  {
    float cx = lights[7 * k], cy = lights[7 * k + 1];
    float rad = lights[7 * k + 2];
    float dx = x - cx, dy = y - cy;
    float d2 = (dx * dx + dy * dy) / (rad * rad);
    if (d2 >= 1.0f) continue;
    float fall = (1.0f - d2) * (1.0f - d2) * lights[7 * k + 3] * gain;
    red += lights[7 * k + 4] * fall;
    green += lights[7 * k + 5] * fall;
    blue += lights[7 * k + 6] * fall;
  }
  int i = (y * w + x) * CH;
  float add[3];
  add[0] = red; add[1] = green; add[2] = blue;
  for (int c = 0; c < CH; ++c)
  {
    float p = src[i + c] / 255.0f + add[c];
    p = p > 1.0f ? 1.0f : p;
    dst[i + c] = (unsigned char)(p * 255.0f);
  }
}

// ------------------------------------------------------------ distorsiones
// Ondas de calor: desplaza cada pixel leyendo otro lugar de la imagen.
__global__ void heat_distort(const unsigned char *src, unsigned char *out,
                             int w, int h, float phase, float amp,
                             float period)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int sx = x + (int)(amp * sinf(y / period + phase));
  int sy = y + (int)(amp * 0.5f * cosf(x / period + phase));
  sx = min(max(sx, 0), w - 1);
  sy = min(max(sy, 0), h - 1);
  int i = (y * w + x) * CH;
  int j = (sy * w + sx) * CH;
  out[i] = src[j]; out[i + 1] = src[j + 1]; out[i + 2] = src[j + 2];
}

// Ondas concentricas (pantalla de rebobinado).
__global__ void ripple(const unsigned char *src, unsigned char *out, int w,
                       int h, float phase, float amp, float period)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  float dx = x - w * 0.5f, dy = y - h * 0.5f;
  float d = sqrtf(dx * dx + dy * dy);
  float k = amp * sinf(d / period - phase);
  int sx = min(max(x + (int)(k * dx / (d + 1.0f)), 0), w - 1);
  int sy = min(max(y + (int)(k * dy / (d + 1.0f)), 0), h - 1);
  int i = (y * w + x) * CH;
  int j = (sy * w + sx) * CH;
  out[i] = src[j]; out[i + 1] = src[j + 1]; out[i + 2] = src[j + 2];
}

// Mezcla lineal de dos imagenes (alpha 0 = a, alpha 1 = b).
__global__ void mix_layers(const unsigned char *a, const unsigned char *b,
                           unsigned char *out, int w, int h, float alpha)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  for (int k = 0; k < CH; ++k)
    out[i + k] = (unsigned char)(a[i + k] * (1.0f - alpha)
                                 + b[i + k] * alpha);
}

// Estela: la imagen anterior deja una copia tenue en la actual.
__global__ void trail(const unsigned char *cur, unsigned char *prev,
                      unsigned char *out, int w, int h, float alpha)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  for (int k = 0; k < CH; ++k)
  {
    float p = cur[i + k] * (1.0f - alpha) + prev[i + k] * alpha;
    out[i + k] = (unsigned char)p;
    prev[i + k] = out[i + k];
  }
}

// ---------------------------------------------------------------- histograma
// Luminancia a 256 baldes; muchos hilos escriben el mismo balde: atomico.
__global__ void luma_hist(const unsigned char *src, int *hist, int w, int h)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  float l = (0.299f * src[i] + 0.587f * src[i + 1]
             + 0.114f * src[i + 2]);
  int bin = (int)l;
  bin = bin < 0 ? 0 : (bin > 255 ? 255 : bin);
  atomicAdd(&hist[bin], 1);
}

// Estiramiento de contraste entre dos niveles (los calcula la CPU). La vineta
// va aca para no tener que pagar una pasada extra cuando no hay glow.
__global__ void stretch(const unsigned char *src, unsigned char *out, int w,
                        int h, float lo, float hi, float vignette)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
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

// ---------------------------------------------------------------- mapa de calor
// Reduce la imagen a una grilla chica (promedio del bloque).
__global__ void minimap(const unsigned char *src, float *grid, int w, int h,
                        int cols, int rows)
{
  int cx = blockIdx.x * blockDim.x + threadIdx.x;
  int cy = blockIdx.y * blockDim.y + threadIdx.y;
  if (cx >= cols || cy >= rows) return;
  int bw = w / cols, bh = h / rows;
  int x0 = cx * bw, y0 = cy * bh;
  float a0 = 0.0f, a1 = 0.0f, a2 = 0.0f;
  int n = 0;
  for (int y = y0; y < min(y0 + bh, h); ++y)
  {
    for (int x = x0; x < min(x0 + bw, w); ++x)
    {
      int i = (y * w + x) * CH;
      a0 += src[i]; a1 += src[i + 1]; a2 += src[i + 2];
      ++n;
    }
  }
  if (n == 0) n = 1;
  int o = (cy * cols + cx) * CH;
  grid[o] = a0 / n / 255.0f;
  grid[o + 1] = a1 / n / 255.0f;
  grid[o + 2] = a2 / n / 255.0f;
}

// Color del mapa de calor: azul (frio) -> verde -> amarillo -> rojo (caliente).
__global__ void heat_colors(const float *heat, unsigned char *out, int n,
                            float max_value)
{
  int p = blockIdx.x * blockDim.x + threadIdx.x;
  if (p >= n) return;
  float v = heat[p] / (max_value > 0.0f ? max_value : 1.0f);
  v = v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
  // Rampa de cuatro tramos, sin memoria compartida ni tablas.
  float r = v < 0.5f ? 0.0f : (v - 0.5f) * 2.0f;
  float g = v < 0.25f ? v * 4.0f : (v < 0.75f ? 1.0f : (1.0f - v) * 4.0f);
  float b = v < 0.5f ? (0.5f - v) * 2.0f : 0.0f;
  int i = p * CH;
  out[i] = (unsigned char)(r * 255.0f);
  out[i + 1] = (unsigned char)(g * 255.0f);
  out[i + 2] = (unsigned char)(b * 255.0f);
}

// Acumula posiciones (jugadores, pelota) en la grilla del mapa de calor.
__global__ void heat_splat(const float *pos, int n, float *heat, int cols,
                           int rows, float amount)
{
  int p = blockIdx.x * blockDim.x + threadIdx.x;
  if (p >= n) return;
  int cx = (int)pos[2 * p], cy = (int)pos[2 * p + 1];
  if (cx < 0 || cx >= cols || cy < 0 || cy >= rows) return;
  atomicAdd(&heat[cy * cols + cx], amount);
}

// ------------------------------------------------- primitivas de imagen (F1)
// Estas son las operaciones chicas que pide la catedra: un hilo por pixel,
// indice 2D, chequeo de bordes y solo memoria global.

constexpr int kGrayChannels = 3;        // interleaved RGB channels
constexpr float kGrayRed = 0.299f;     // BT.601 red luma weight
constexpr float kGrayGreen = 0.587f;   // BT.601 green luma weight
constexpr float kGrayBlue = 0.114f;    // BT.601 blue luma weight
constexpr float kGrayRound = 0.5f;    // round to nearest byte

// One thread per pixel; spare threads return before reading global memory.
__global__ void k_gray(const unsigned char *src, unsigned char *dst,
                       int width, int height)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= width || y >= height) return;
  int i = (y * width + x) * kGrayChannels;
  float luma = kGrayRed * src[i] + kGrayGreen * src[i + 1]
               + kGrayBlue * src[i + 2];
  unsigned char gray = (unsigned char)(luma + kGrayRound);
  dst[i] = dst[i + 1] = dst[i + 2] = gray;
}

// Negativo: 255 - canal.
__global__ void k_invert(const unsigned char *src, unsigned char *dst,
                         int w, int h)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  dst[i] = 255 - src[i];
  dst[i + 1] = 255 - src[i + 1];
  dst[i + 2] = 255 - src[i + 2];
}

// Brillo y contraste: (v - 0.5) * c + 0.5 + b, en escala 0..1.
__global__ void k_brightness_contrast(const unsigned char *src,
                                      unsigned char *dst, int w, int h,
                                      float brightness, float contrast)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  for (int c = 0; c < CH; ++c)
  {
    float v = src[i + c] / 255.0f;
    v = (v - 0.5f) * contrast + 0.5f + brightness;
    v = v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
    dst[i + c] = (unsigned char)(v * 255.0f + 0.5f);
  }
}

// Ganancia: multiplica (noche, autoexposicion).
__global__ void k_gain(const unsigned char *src, unsigned char *dst,
                       int w, int h, float gain)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  for (int c = 0; c < CH; ++c)
  {
    float v = src[i + c] * gain;
    v = v < 0.0f ? 0.0f : (v > 255.0f ? 255.0f : v);
    dst[i + c] = (unsigned char)(v + 0.5f);
  }
}

// Tinte: mezcla el canal con un color (0..1 por canal).
__global__ void k_tint(const unsigned char *src, unsigned char *dst,
                       int w, int h, float r, float g, float b)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  dst[i] = (unsigned char)(src[i] * r + 0.5f);
  dst[i + 1] = (unsigned char)(src[i + 1] * g + 0.5f);
  dst[i + 2] = (unsigned char)(src[i + 2] * b + 0.5f);
}

// Rotacion alrededor del centro (muestreo al vecino mas cercano, bordes
// recortados: lo que cae afuera queda negro).
__global__ void k_rotate(const unsigned char *src, unsigned char *dst,
                         int w, int h, float angle)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
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

// Luminancia en float 0..1 (entrada para sobel y el histograma fino).
__global__ void k_to_gray_f32(const unsigned char *src, float *dst,
                              int w, int h)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  dst[y * w + x] = (0.299f * src[i] + 0.587f * src[i + 1]
                    + 0.114f * src[i + 2]) / 255.0f;
}

// Sobel: magnitud del gradiente (bordes). Bordes repetidos (clamp).
__global__ void k_sobel(const float *gray, float *edges, int w, int h)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int x0 = max(0, x - 1), x1 = min(w - 1, x + 1);
  int y0 = max(0, y - 1), y1 = min(h - 1, y + 1);
  float a = gray[y0 * w + x0], b = gray[y0 * w + x], c = gray[y0 * w + x1];
  float d = gray[y * w + x0],  f = gray[y * w + x1];
  float g = gray[y1 * w + x0], hh = gray[y1 * w + x], k = gray[y1 * w + x1];
  float gx = (c + 2.0f * f + k) - (a + 2.0f * d + g);
  float gy = (g + 2.0f * hh + k) - (a + 2.0f * b + c);
  edges[y * w + x] = sqrtf(gx * gx + gy * gy) * 0.25f;
}

// Normaliza las magnitudes de sobel a 0..255 sobre la imagen entera.
__global__ void k_sobel_normalize(const float *edges, unsigned char *dst,
                                  int w, int h, float max_value)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  float v = edges[y * w + x] / (max_value > 0.0f ? max_value : 1.0f);
  v = v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
  int i = (y * w + x) * CH;
  unsigned char u = (unsigned char)(v * 255.0f + 0.5f);
  dst[i] = u; dst[i + 1] = u; dst[i + 2] = u;
}

// Bordes brillantes: suma el sobel normalizado sobre la imagen original.
__global__ void k_edge_glow(const unsigned char *src,
                            const unsigned char *edges, unsigned char *dst,
                            int w, int h, float strength)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  for (int c = 0; c < CH; ++c)
  {
    float v = src[i + c] + edges[i + c] * strength;
    v = v < 0.0f ? 0.0f : (v > 255.0f ? 255.0f : v);
    dst[i + c] = (unsigned char)(v + 0.5f);
  }
}

// ----------------------------------------------- poder del hielo (F11)
// El hielo era la cadena gris -> sobel -> normalizar -> bordes -> tinte ->
// mezcla, con seis viajes de la imagen entre el host y la placa. Ahora son
// dos kernels y la imagen sube y baja una sola vez:
//   1. k_ice_edges guarda el sobel en la placa y acumula el maximo global
//      con atomicMax sobre los bits del float (los bordes son positivos y,
//      para ellos, el orden de los bits es el orden de los numeros).
//   2. k_ice_apply normaliza con ese maximo, suma los bordes, tinta de azul y
//      mezcla, todo por pixel y redondeando igual que cada kernel suelto.

// Gris de un pixel (la misma cuenta que k_to_gray_f32).
__device__ float ice_gray(const unsigned char *src, int i)
{
  return (0.299f * src[i] + 0.587f * src[i + 1] + 0.114f * src[i + 2]) /
      255.0f;
}

__global__ void k_ice_edges(const unsigned char *src, float *edges,
                            unsigned int *top, int w, int h)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
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
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
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

// --------------------------------------- poderes y noche (F3/F4)
// Lámparas de la cátedra: un hilo por píxel, índice 2D, borde y luz en
// memoria global. Cada lámpara (x, y, radio, potencia) suma su luz y el
// total multiplica al píxel: es la noche y también el apagón.
// `tope` > 0 hace que la suma se acerque a ese tope sin pasarlo nunca
// (cada lámpara suma una fracción de lo que falta): seis lámparas juntas
// no pueden dejar el píxel más claro que el día ni quemar el sprite.
// `tope` = 0 deja la suma clásica del apagón, que no tiene techo.
#define SPOT_MAX 8          // lámparas que se recorren por píxel
__global__ void k_spotlights(const unsigned char *src, unsigned char *dst,
                             int w, int h, const float *lights, int n,
                             float ambient, float tr, float tg, float tb,
                             float tope)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
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
      float fall = 1.0f - d2;     // caída suave desde el centro
      if (tope > 0.0f)
      {
        light += power * fall * fall * (tope - light);
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

// Aire caliente alrededor de la pelota (poder de fuego). Fuera del radio
// el píxel se copia tal cual: el costo no depende del tamaño del radio.
#define HEAT_FREQ_Y 0.12f       // ondas por píxel en vertical
#define HEAT_SPEED_Y 18.0f      // rad/s de esas ondas
#define HEAT_FREQ_X 0.09f       // ondas por píxel en horizontal
#define HEAT_SPEED_X 14.0f      // rad/s de esas ondas
#define HEAT_LATERAL 0.4f       // el desplazamiento horizontal es menor
__global__ void k_heat_distort(const unsigned char *src, unsigned char *dst,
                               int w, int h, float cx, float cy, float rad,
                               float t, float amp)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  float dx = x - cx, dy = y - cy;
  float d = sqrtf(dx * dx + dy * dy);
  int sx = x, sy = y;
  if (d < rad)
  {
    float fall = 1.0f - d / rad;    // se apaga en el borde del radio
    sx = x + (int)(amp * sinf(y * HEAT_FREQ_Y + t * HEAT_SPEED_Y) * fall);
    sy = y + (int)(amp * HEAT_LATERAL
                   * sinf(x * HEAT_FREQ_X + t * HEAT_SPEED_X) * fall);
  }
  sx = sx < 0 ? 0 : (sx >= w ? w - 1 : sx);   // borde: se recorta
  sy = sy < 0 ? 0 : (sy >= h ? h - 1 : sy);
  int i = (y * w + x) * CH;
  int j = (sy * w + sx) * CH;
  dst[i] = src[j];
  dst[i + 1] = src[j + 1];
  dst[i + 2] = src[j + 2];
}

// Onda expansiva del gol: un anillo que crece y deforma lo que atraviesa,
// con un realce de brillo en el borde del anillo. Arriba de 'y_min' (la
// tribuna y los carteles) el pixel se copia tal cual: nada se mueve ahi.
#define RIPPLE_PI 3.14159265f   // para el seno del anillo
#define RIPPLE_GLOW 60.0f       // brillo máximo del anillo (0..255)
__global__ void k_ripple(const unsigned char *src, unsigned char *dst,
                         int w, int h, float cx, float cy, float radius,
                         float width, float amp, int y_min)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  if (y < y_min)
  {                       // fuera de la cancha: no se toca
    dst[i] = src[i]; dst[i + 1] = src[i + 1]; dst[i + 2] = src[i + 2];
    return;
  }
  float dx = x - cx, dy = y - cy;
  float d = sqrtf(dx * dx + dy * dy);
  float k = (d - radius) / (width > 0.0f ? width : 1.0f);
  int sx = x, sy = y;
  float glow = 0.0f;
  if (k > -1.0f && k < 1.0f)
  {
    float off = amp * sinf(RIPPLE_PI * k);
    sx = (int)(x + off * dx / (d + 1.0f));
    sy = (int)(y + off * dy / (d + 1.0f));
    glow = RIPPLE_GLOW * (1.0f - fabsf(k));
  }
  sx = sx < 0 ? 0 : (sx >= w ? w - 1 : sx);
  sy = sy < y_min ? y_min : (sy >= h ? h - 1 : sy);
  int j = (sy * w + sx) * CH;
  for (int c = 0; c < CH; ++c)
  {
    float v = src[j + c] + glow;
    v = v < 0.0f ? 0.0f : (v > 255.0f ? 255.0f : v);
    dst[i + c] = (unsigned char)(v + 0.5f);
  }
}

// Estela de la pelota: cada píxel queda con el máximo entre el frame
// actual y el anterior atenuado. No es un promedio: no deja fantasmas.
__global__ void k_trail_blend(const unsigned char *cur,
                              const unsigned char *prev, unsigned char *dst,
                              int w, int h, float decay)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  for (int c = 0; c < CH; ++c)
  {
    float v = fmaxf((float)cur[i + c], (float)prev[i + c] * decay);
    dst[i + c] = (unsigned char)(v + 0.5f);
  }
}

// Histograma de luma de la noche (F4): 256 bins con atomicAdd y el máximo
// con atomicMax. Las dos escrituras son compartidas: ahí van las atómicas.
__global__ void k_luma_hist(const unsigned char *src, unsigned int *hist,
                            unsigned int *luma_max, int w, int h)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;
  int i = (y * w + x) * CH;
  float l = 0.299f * src[i] + 0.587f * src[i + 1] + 0.114f * src[i + 2];
  unsigned int bin = (unsigned int)(l + 0.5f);   // mismo redondeo que k_gray
  atomicAdd(&hist[bin], 1u);
  atomicMax(luma_max, bin);
}

// ===========================================================================
// F5: repetición y VAR
// ===========================================================================

// Televisión vieja de la repetición: gris con tinte, líneas de barrido,
// viñeta y grano. Un hilo por píxel y sólo memoria global.
// El ruido sale de (x, y, frame) con una cuenta entera: el mismo frame da
// siempre el mismo grano, así que numpy lo puede reproducir exacto.
#define CRT_NOISE_MUL 2654435761u   // multiplicador de la cuenta de ruido
#define CRT_NOISE_SHIFT 24          // bits altos que se usan del ruido
#define CRT_DIAGONAL 0.70710678f    // 1/sqrt(2): lleva la viñeta a 0..1

__global__ void k_crt(const unsigned char *src, unsigned char *dst,
                      int w, int h, int frame, float amount, float scan,
                      float vignette, float noise, int rows,
                      float tr, float tg, float tb)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;              // chequeo de bordes
  int i = (y * w + x) * CH;
  float l = (0.299f * src[i] + 0.587f * src[i + 1]
             + 0.114f * src[i + 2]) / 255.0f;
  // Una línea oscura cada `rows` filas: el barrido del tubo.
  float band = (rows > 0 && y % rows == rows - 1) ? (1.0f - scan) : 1.0f;
  // Viñeta radial: 0 en el centro y 1 en las esquinas.
  float nx = 2.0f * x / (float)(w > 1 ? w - 1 : 1) - 1.0f;
  float ny = 2.0f * y / (float)(h > 1 ? h - 1 : 1) - 1.0f;
  float d = sqrtf(nx * nx + ny * ny) * CRT_DIAGONAL;
  float vig = 1.0f - vignette * d * d;
  // Grano pseudoaleatorio, entero sin signo: desborda a propósito.
  unsigned int seed = (unsigned int)(x * 1973 + y * 9277 + frame * 26699) *
      CRT_NOISE_MUL;
  float grain = (float)((seed >> CRT_NOISE_SHIFT) & 255u) / 255.0f - 0.5f;
  float crt = l * band * vig + grain * noise;
  float v = l + (crt - l) * amount;           // 0: imagen original
  float out[CH];
  out[0] = v * tr; out[1] = v * tg; out[2] = v * tb;
  for (int c = 0; c < CH; ++c)
  {
    float b = out[c] * 255.0f;
    b = b < 0.0f ? 0.0f : (b > 255.0f ? 255.0f : b);
    dst[i + c] = (unsigned char)(b + 0.5f);
  }
}

// ===========================================================================
// F6: mapa de calor
// ===========================================================================

// px: la celda nunca mide menos que esto (division por cero en el host)
#define HEAT_MIN_CELL 1.0f
// Acumula los puntos (x, y) de un canal en la grilla de celdas. Un hilo por
// punto y atomicAdd: muchos puntos pueden caer en la misma celda. Ademas
// guarda en `maxes` la celda mas caliente del canal con atomicAdd + atomicMax
// (la escritura es la del atomicAdd: el valor viejo + 1). Los puntos que caen
// fuera de la cancha se descartan (chequeo de bordes).
__global__ void k_heat_accumulate(const float *pts, int n, int channel,
                                  int cols, int rows, float cw, float ch,
                                  unsigned int *grids, unsigned int *maxes)
{
  int k = blockIdx.x * blockDim.x + threadIdx.x;
  if (k >= n) return;
  float cell_w = cw > 0.0f ? cw : HEAT_MIN_CELL;
  float cell_h = ch > 0.0f ? ch : HEAT_MIN_CELL;
  int cx = (int)(pts[k * 2] / cell_w);
  int cy = (int)(pts[k * 2 + 1] / cell_h);
  if (cx < 0 || cx >= cols || cy < 0 || cy >= rows) return;
  unsigned int old = atomicAdd(&grids[channel * cols * rows + cy * cols + cx], 1u);
  atomicMax(&maxes[channel], old + 1u);
}

// Dibuja la grilla de un canal sobre la imagen: lectura bilineal de las
// celdas, rampa azul -> cian -> amarillo -> rojo y mezcla con
// alpha * min(1, v * gain). El maximo del canal se lee de `maxes` (no viaja
// al host) y normaliza la rampa.
__global__ void k_heat_render(const unsigned char *src, const unsigned int *grids,
                              const unsigned int *maxes, unsigned char *dst,
                              int w, int h, int cols, int rows, int channel,
                              float alpha, float gain)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;              // chequeo de bordes
  // Tamanio de celda en px y centro del pixel llevado a celdas.
  float cw = (float)w / (float)cols;
  float ch = (float)h / (float)rows;
  float fx = ((float)x + 0.5f) / cw - 0.5f;
  float fy = ((float)y + 0.5f) / ch - 0.5f;
  fx = fx < 0.0f ? 0.0f : (fx > cols - 1 ? (float)(cols - 1) : fx);
  fy = fy < 0.0f ? 0.0f : (fy > rows - 1 ? (float)(rows - 1) : fy);
  int x0 = (int)fx, y0 = (int)fy;
  int x1 = x0 + 1 < cols ? x0 + 1 : cols - 1;
  int y1 = y0 + 1 < rows ? y0 + 1 : rows - 1;
  float tx = fx - x0, ty = fy - y0;
  const unsigned int *cells = grids + channel * cols * rows;
  float v00 = (float)cells[y0 * cols + x0], v10 = (float)cells[y0 * cols + x1];
  float v01 = (float)cells[y1 * cols + x0], v11 = (float)cells[y1 * cols + x1];
  float v = (1.0f - tx) * (1.0f - ty) * v00 + tx * (1.0f - ty) * v10
            + (1.0f - tx) * ty * v01 + tx * ty * v11;
  float top = (float)maxes[channel];
  v = top > 0.0f ? v / top : 0.0f;
  v = v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
  float a = alpha * fminf(1.0f, v * gain);
  // Rampa de la spec: azul, cian, amarillo, rojo.
  float r = (v - 0.5f) * 2.0f;
  r = r < 0.0f ? 0.0f : (r > 1.0f ? 1.0f : r);
  float g = v < 0.25f ? v * 4.0f : (v < 0.75f ? 1.0f : (1.0f - v) * 4.0f);
  float b = (0.5f - v) * 2.0f;
  b = b < 0.0f ? 0.0f : (b > 1.0f ? 1.0f : b);
  float ramp[CH];
  ramp[0] = r; ramp[1] = g; ramp[2] = b;
  int i = (y * w + x) * CH;
  for (int c = 0; c < CH; ++c)
  {
    float px = (float)src[i + c] / 255.0f;
    float out = px * (1.0f - a) + ramp[c] * a;
    out = out * 255.0f;
    out = out < 0.0f ? 0.0f : (out > 255.0f ? 255.0f : out);
    dst[i + c] = (unsigned char)(out + 0.5f);
  }
}

// ------------------------------------- tribuna con gente (F11, solo FULL)
// La franja de tribunas se pinta entera: gradas escalonadas y personas. Cada
// hilo escribe su propio pixel y todo sale de un hash de la butaca (columna,
// fila), asi que no hace falta memoria compartida ni atomicas.
//
// Una butaca mide cfg[CC_W] x cfg[CC_H] px. Abajo esta la grada: el escalon
// oscuro con su filo claro. La persona se para en ese filo y crece hacia
// arriba: torso, cabeza redonda con pelo y, en algunas butacas, una bandera
// que flamea. El saltito es un seno desfasado por butaca, asi que la tribuna
// se mueve como una ola; la del equipo que metio el gol (side) salta mas
// alto y mas rapido mientras dura el festejo (boost 0-1).
//
// Las filas de arriba se pintan mas oscuras (profundidad) y cada pixel puede
// estar tapado por dos filas: la suya y la de atras, cuya cabeza y bandera se
// meten en la butaca de arriba (por eso el lazo CROWD_ROWS, de la fila de
// atras a la de adelante).
#define CROWD_HASH_C 73856093u   // primo del hash de la columna
#define CROWD_HASH_R 19349663u   // primo del hash de la fila
#define CROWD_ROWS 2             // filas que se prueban por pixel
#define CROWD_FLAG_HZ 3.2f       // rad/s del flameo de la bandera
#define CROWD_FLAG_CURVE 0.30f   // rad por px de alto: la tela se curva
#define CROWD_SHOULDER 2.0f      // px que se angosta el torso en los hombros
#define CROWD_POLE_W 1.0f        // medio ancho del palo de la bandera
#define CROWD_RISER 1.0f         // px del filo claro del escalon
#define CROWD_JUMP_LOW 0.4f      // saltito mas chico (parte del maximo)
#define CROWD_JUMP_SPREAD 0.6f   // lo que el hash le suma al saltito
#define CROWD_PHASE 0.01f        // rad por unidad del hash (desfase)
#define CROWD_PHASE_TOP 628u     // 628 * CROWD_PHASE = una vuelta
#define CROWD_SPREAD 0.01f       // unidad del hash -> 0..1
#define CROWD_SKINS 3            // tonos de piel de la tabla
#define CROWD_HAIRS 3            // tonos de pelo
#define CROWD_FULL 100u          // el hash se reparte en 0..100

// Indices de la tabla de parametros que manda el host.
#define CC_W 0                   // px: ancho de la butaca
#define CC_H 1                   // px: alto
#define CC_JUMP 2                // px del saltito
#define CC_HZ 3                  // rad/s del saltito
#define CC_GOAL_JUMP 4           // px extra de la tribuna que festeja
#define CC_GOAL_HZ 5             // rad/s extra del festejo
#define CC_WAVE 6                // px que flamea la bandera
#define CC_FLAG_W 7              // px: ancho de la bandera
#define CC_FLAG_H 8              // px: alto
#define CC_FILL 9                // % de butacas ocupadas
#define CC_EVERY 10              // una bandera cada N butacas
#define CC_BODY_W 11             // px: ancho del torso
#define CC_BODY_H 12             // px: alto del torso
#define CC_HEAD_R 13             // px: radio de la cabeza
#define CC_STEP 14               // px: alto del escalon de la fila
#define CC_POLE_H 15             // px: el palo sube esto desde el hombro
#define CC_SHADE_TOP 16          // oscurecimiento de la fila de arriba
#define CC_SHADE_BOTTOM 17       // ... y de la de abajo (cerca)
#define CC_VAR_MIN 18            // brillo de la camiseta mas apagada
#define CC_VAR_RANGE 19          // lo que el hash le suma al brillo
#define CC_HEAD_CUT 20           // parte de la cabeza que es pelo (0-1)
#define CC_OUTLINE 21            // px del borde oscuro de la cabeza
#define CC_SHOULDER_EDGE 22      // px de la linea oscura de los hombros
#define CC_SHOULDER_SHADE 23     // cuanto la oscurece

// Filas de la tabla de colores (cada una es un rgb).
#define CP_SHIRT_A 0             // camiseta del equipo de la izquierda
#define CP_SHIRT_B 1             // camiseta del de la derecha
#define CP_SKIN 2                // CP_SKIN .. CP_SKIN + CROWD_SKINS - 1
#define CP_HAIR 5                // CP_HAIR .. CP_HAIR + CROWD_HAIRS - 1
#define CP_TREAD 8               // piso de la grada
#define CP_RISER 9               // frente oscuro del escalon
#define CP_EDGE 10               // filo claro del escalon
#define CP_POLE 11               // palo de la bandera
#define CP_FLAG_WHITE 12         // franja blanca de la bandera
#define CP_FLAG_A 13             // bandera del equipo de la izquierda
#define CP_FLAG_B 14             // bandera del de la derecha
#define CP_OUTLINE 15            // borde oscuro de las cabezas

// Hash de la butaca: barato y bien repartido (xorshift multiplicativo).
__device__ unsigned int crowd_hash(int c, int r)
{
  unsigned int hsh = ((unsigned int)c * CROWD_HASH_C) ^
      ((unsigned int)r * CROWD_HASH_R);
  hsh ^= hsh >> 13;
  hsh *= 1274126177u;
  hsh ^= hsh >> 16;
  return hsh;
}

// Copia en rgb la fila `row` de la tabla, aclarada u oscurecida por `var`.
__device__ void crowd_paint(const float *pal, int row, float var, float *rgb)
{
  rgb[0] = pal[3 * row] * var;
  rgb[1] = pal[3 * row + 1] * var;
  rgb[2] = pal[3 * row + 2] * var;
}

// Brillo de la camiseta de esa butaca (el hash reparte la variedad).
__device__ float crowd_var(unsigned int hsh, const float *cfg)
{
  return cfg[CC_VAR_MIN] + cfg[CC_VAR_RANGE]
         * (float)((hsh >> 13) % CROWD_FULL) * CROWD_SPREAD;
}

// Medio ancho del torso a esa altura: los hombros se redondean arriba.
__device__ float crowd_half(float up, const float *cfg)
{
  float half = cfg[CC_BODY_W] * 0.5f;
  if (up > cfg[CC_BODY_H] - CROWD_SHOULDER)
    return half - CROWD_SHOULDER * 0.5f;
  return half;
}

// Saltito de la persona en px (0..amplitud), desfasado por butaca.
__device__ float crowd_jump(unsigned int hsh, float t, float boost,
                            int team, int side, const float *cfg)
{
  float phase = (float)(hsh % CROWD_PHASE_TOP) * CROWD_PHASE;
  float amp = cfg[CC_JUMP]
              * (CROWD_JUMP_LOW + CROWD_JUMP_SPREAD
                 * (float)((hsh / 7u) % CROWD_FULL) * CROWD_SPREAD);
  float hz = cfg[CC_HZ];
  if (team == side)
  {                 // la tribuna que metio el gol
    amp += cfg[CC_GOAL_JUMP] * boost;
    hz += cfg[CC_GOAL_HZ] * boost;
  }
  return amp * (0.5f + 0.5f * sinf(t * hz + phase));
}

// Persona de una butaca en el punto (lx, up) de su celda: torso, cabeza y
// pelo. Devuelve 1 si el pixel es de la persona (deja el color en rgb).
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
    if (up > body_h - cfg[CC_SHOULDER_EDGE])     // hombros
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
  {                // pelo: la parte de arriba
    crowd_paint(pal, CP_HAIR + (int)((hsh >> 9) % CROWD_HAIRS),
                crowd_var(hsh, cfg), rgb);
    return 1;
  }
  float inner = r - cfg[CC_OUTLINE];
  if (d2 > inner * inner)
  {                        // borde oscuro de la cara
    crowd_paint(pal, CP_OUTLINE, 1.0f, rgb);
    return 1;
  }
  crowd_paint(pal, CP_SKIN + (int)((hsh >> 5) % CROWD_SKINS), 1.0f, rgb);
  return 1;
}

// Bandera de la butaca (si le toca): el palo y una tela bicolor que flamea.
// Se apoya arriba de la cabeza y se corre con un seno, fila por fila.
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
    crowd_paint(pal, CP_POLE, 1.0f, rgb);            // el palo
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

// Grada de la fila: el piso oscuro y el escalon con su filo claro arriba.
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

// Oscurecimiento de la fila: las de arriba quedan mas lejos (profundidad).
__device__ float crowd_shade(int row, int rows, const float *cfg)
{
  float far = (float)row / (float)(rows > 1 ? rows - 1 : 1);
  return cfg[CC_SHADE_TOP]
         + (cfg[CC_SHADE_BOTTOM] - cfg[CC_SHADE_TOP]) * far;
}

// Pinta la franja de tribunas: un hilo por pixel, borde y memoria global.
__global__ void k_tribuna(const unsigned char *src, unsigned char *dst,
                          int w, int h, float t, int side, float boost,
                          const float *cfg, const float *pal)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;
  if (x >= w || y >= h) return;              // chequeo de bordes
  int i = (y * w + x) * CH;
  int row = (int)((float)y / cfg[CC_H]);
  int rows = (int)((float)h / cfg[CC_H]);
  float rgb[3];
  crowd_step(y, row, cfg, pal, rgb);         // la grada de esa fila
  int team = (x < w / 2) ? 0 : 1;            // cada mitad es un equipo
  for (int k = 0; k < CROWD_ROWS; ++k)
  {
    int r = row + k;                       // de la de atras a la de adelante
    float stagger = (float)((r & 1) * ((int)cfg[CC_W] / 2));
    float cx = (float)x + stagger;         // filas trabadas
    int c = (int)(cx / cfg[CC_W]);
    float lx = cx - (float)c * cfg[CC_W];
    unsigned int hsh = crowd_hash(c, r);
    if ((float)(hsh % CROWD_FULL) >= cfg[CC_FILL])
      continue;                            // butaca vacia
    float up = (float)(r + 1) * cfg[CC_H] - cfg[CC_STEP] - (float)y
               - crowd_jump(hsh, t, boost, team, side, cfg);
    if (crowd_person(lx, up, hsh, cfg, pal, team, rgb))
      continue;                            // la persona tapa la bandera
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
