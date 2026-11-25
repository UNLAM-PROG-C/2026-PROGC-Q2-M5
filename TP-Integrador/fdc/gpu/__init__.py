"""GPU package: post-processing effects of the game (optional).

The game runs without it. When CUDA is available the frames go through the
kernels of kernels.cu; if not, fdc.gpu.postfx falls back to the numpy
version (cpu_ref) or to no effects at all.
"""
