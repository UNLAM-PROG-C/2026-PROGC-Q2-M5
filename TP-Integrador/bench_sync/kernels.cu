// Luma histogram kernels: the same problem with different synchronization.
// Every kernel uses a grid-stride loop, so the launch is identical and only
// the way the threads update the 256 shared counters changes.
#include "kernels_config.cuh"

__device__ unsigned int luma_bin(const unsigned char *src, int pixel)
{
  int i = pixel * CH;
  return (LUMA_R * src[i] + LUMA_G * src[i + GREEN] + LUMA_B * src[i + BLUE]
          + LUMA_ROUND) >> LUMA_SHIFT;
}

// (a) Every thread adds straight into global memory: all the threads of
// the GPU compete for the same 256 addresses.
__global__ void k_hist_global(const unsigned char *src, unsigned int *hist,
                              int pixels)
{
  int stride = blockDim.x * gridDim.x;
  for (int p = blockIdx.x * blockDim.x + threadIdx.x; p < pixels; p += stride)
  {
    atomicAdd(&hist[luma_bin(src, p)], HIST_INCREMENT);
  }
}

// (b) Privatization per block: atomics on a __shared__ copy (only the
// threads of one block compete), then one global atomic per bin and block.
__device__ void clear_bins(unsigned int *local)
{
  for (int b = threadIdx.x; b < BINS; b += blockDim.x)
  {
    local[b] = EMPTY_BIN;
  }
}

__device__ void merge_bins(const unsigned int *local, unsigned int *hist)
{
  for (int b = threadIdx.x; b < BINS; b += blockDim.x)
  {
    if (local[b] > EMPTY_BIN)
    {
      atomicAdd(&hist[b], local[b]);
    }
  }
}

__global__ void k_hist_shared(const unsigned char *src, unsigned int *hist,
                              int pixels)
{
  __shared__ unsigned int local[BINS];
  clear_bins(local);
  __syncthreads();  // every bin is zero before anyone adds
  int stride = blockDim.x * gridDim.x;
  for (int p = blockIdx.x * blockDim.x + threadIdx.x; p < pixels; p += stride)
  {
    atomicAdd(&local[luma_bin(src, p)], HIST_INCREMENT);
  }
  __syncthreads();  // the block finished counting before the merge
  merge_bins(local, hist);
}

// Race condition on purpose: read, add and write are three separate steps,
// so concurrent increments of the same bin overwrite each other.
__global__ void k_hist_racy(const unsigned char *src,
                            volatile unsigned int *hist, int pixels)
{
  int stride = blockDim.x * gridDim.x;
  for (int p = blockIdx.x * blockDim.x + threadIdx.x; p < pixels; p += stride)
  {
    unsigned int b = luma_bin(src, p);
    hist[b] = hist[b] + HIST_INCREMENT;
  }
}
