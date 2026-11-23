// Luma histogram kernels: the same problem with different synchronization.
// Every kernel uses a grid-stride loop, so the launch is identical and only
// the way the threads update the 256 shared counters changes.
#define BINS 256  // one bin per 8-bit luma value
#define LUMA_R 77  // BT.601 weights in 8.8 fixed point (sum = 256)
#define LUMA_G 150
#define LUMA_B 29
#define LUMA_ROUND 128  // half of 256: round to nearest
#define LUMA_SHIFT 8  // divide by 256
#define CH 3  // RGB channels per pixel

__device__ unsigned int luma_bin(const unsigned char *src, int pixel)
{
  int i = pixel * CH;
  return (LUMA_R * src[i] + LUMA_G * src[i + 1] + LUMA_B * src[i + 2]
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
    atomicAdd(&hist[luma_bin(src, p)], 1u);
  }
}

// (b) Privatization per block: atomics on a __shared__ copy (only the
// threads of one block compete), then one global atomic per bin and block.
__device__ void clear_bins(unsigned int *local)
{
  for (int b = threadIdx.x; b < BINS; b += blockDim.x)
  {
    local[b] = 0;
  }
}

__device__ void merge_bins(const unsigned int *local, unsigned int *hist)
{
  for (int b = threadIdx.x; b < BINS; b += blockDim.x)
  {
    if (local[b] > 0)
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
    atomicAdd(&local[luma_bin(src, p)], 1u);
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
    hist[b] = hist[b] + 1;
  }
}
