// Compile-time constants for the histogram benchmark.
#pragma once

#define BINS 256  // one bin per 8-bit luma value
#define LUMA_R 77  // BT.601 weights in 8.8 fixed point (sum = 256)
#define LUMA_G 150
#define LUMA_B 29
#define LUMA_ROUND 128  // half of 256: round to nearest
#define LUMA_SHIFT 8  // divide by 256
#define CH 3  // RGB channels per pixel
#define GREEN 1  // green channel offset
#define BLUE 2  // blue channel offset
#define EMPTY_BIN 0u  // no samples yet
#define HIST_INCREMENT 1u  // one sample per input pixel
