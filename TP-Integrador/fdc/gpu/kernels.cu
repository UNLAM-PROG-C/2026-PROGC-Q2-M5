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
    for (int k = x0; k <= x1; ++k) {
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
    for (int k = y0; k <= y1; ++k) {
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
    for (int k = x0; k <= x1; ++k) {
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
    for (int k = y0; k <= y1; ++k) {
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
    for (int k = 0; k < CH; ++k) {
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
    for (int y = cy - r; y <= cy + r; ++y) {
        if (y < 0 || y >= h) continue;
        for (int x = cx - r; x <= cx + r; ++x) {
            if (x < 0 || x >= w) continue;
            int i = (y * w + x) * CH;
            atomicAdd(&acc[i], cr * gain);
            atomicAdd(&acc[i + 1], cg * gain);
            atomicAdd(&acc[i + 2], cb * gain);
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
    for (int k = 0; k < CH; ++k) {
        float p = base[i + k] / 255.0f + acc[i + k] * gain;
        p = p > 1.0f ? 1.0f : p;
        out[i + k] = (unsigned char)(p * 255.0f);
    }
}

// ---------------------------------------------------------------- spotlights
// Focos con caida radial; 'lights' trae x, y, radio, intensidad, r, g, b.
__global__ void splat_lights(const float *lights, int n, float *acc,
                             int w, int h, float gain)
{
    int p = blockIdx.x * blockDim.x + threadIdx.x;
    if (p >= n) return;
    float cx = lights[7 * p], cy = lights[7 * p + 1];
    float rad = lights[7 * p + 2], power = lights[7 * p + 3];
    float cr = lights[7 * p + 4], cg = lights[7 * p + 5];
    float cb = lights[7 * p + 6];
    int x0 = max(0, (int)(cx - rad)), x1 = min(w - 1, (int)(cx + rad));
    int y0 = max(0, (int)(cy - rad)), y1 = min(h - 1, (int)(cy + rad));
    float r2 = rad * rad;
    for (int y = y0; y <= y1; ++y) {
        for (int x = x0; x <= x1; ++x) {
            float dx = x - cx, dy = y - cy;
            float d2 = (dx * dx + dy * dy) / r2;
            if (d2 >= 1.0f) continue;
            float k = (1.0f - d2) * (1.0f - d2) * power * gain;
            int i = (y * w + x) * CH;
            atomicAdd(&acc[i], cr * k);
            atomicAdd(&acc[i + 1], cg * k);
            atomicAdd(&acc[i + 2], cb * k);
        }
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
    for (int k = 0; k < CH; ++k) {
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

// Estiramiento de contraste entre dos niveles (los calcula la CPU).
__global__ void stretch(const unsigned char *src, unsigned char *out, int w,
                        int h, float lo, float hi)
{
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= w || y >= h) return;
    int i = (y * w + x) * CH;
    float span = hi - lo > 1.0f ? hi - lo : 1.0f;
    for (int k = 0; k < CH; ++k) {
        float p = (src[i + k] - lo) / span;
        p = p < 0.0f ? 0.0f : (p > 1.0f ? 1.0f : p);
        out[i + k] = (unsigned char)(p * 255.0f);
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
    for (int y = y0; y < min(y0 + bh, h); ++y) {
        for (int x = x0; x < min(x0 + bw, w); ++x) {
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

// Copia el canal gris (luma) a 8 bits: gris, blanco y negro y un solo canal.
__global__ void k_gray(const unsigned char *src, unsigned char *dst,
                       int w, int h)
{
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= w || y >= h) return;
    int i = (y * w + x) * CH;
    float v = 0.299f * src[i] + 0.587f * src[i + 1] + 0.114f * src[i + 2];
    unsigned char g = (unsigned char)(v + 0.5f);
    dst[i] = g; dst[i + 1] = g; dst[i + 2] = g;
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
    for (int c = 0; c < CH; ++c) {
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
    for (int c = 0; c < CH; ++c) {
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
    if (sx < 0 || sx >= w || sy < 0 || sy >= h) {
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
    for (int c = 0; c < CH; ++c) {
        float v = src[i + c] + edges[i + c] * strength;
        v = v < 0.0f ? 0.0f : (v > 255.0f ? 255.0f : v);
        dst[i + c] = (unsigned char)(v + 0.5f);
    }
}
