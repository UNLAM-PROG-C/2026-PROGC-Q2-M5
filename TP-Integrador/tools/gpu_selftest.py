"""Compares every GPU kernel with its numpy version (fdc.gpu.cpu_ref).

Usage (PowerShell, from the repository):
    py tools\\gpu_selftest.py

It needs the toolchain folder next to the repository (see INSTALACION.md).
Prints the biggest difference of each operation and the milliseconds.
"""
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fdc.gpu import backend  # noqa: E402  pylint: disable=wrong-import-position
from fdc.gpu import cpu_ref  # noqa: E402  pylint: disable=wrong-import-position
from fdc.gpu import env      # noqa: E402  pylint: disable=wrong-import-position

W, H = 320, 180
TOLERANCE = 3           # levels of gray: rounding of the average
SEED = 7


def timed(fn, *args):
    start = time.perf_counter()
    out = fn(*args)
    return out, (time.perf_counter() - start) * 1000.0


def diff(a, b):
    return float(np.abs(a.astype(np.float32) - b.astype(np.float32)).max())


def report(name, ours, ref, limit=TOLERANCE, mean=False):
    delta = diff(ours, ref)
    if mean:
        delta = float(np.abs(ours.astype(np.float32)
                             - ref.astype(np.float32)).mean())
    state = "OK " if delta <= limit else "BAD"
    print(f"  {state} {name:<12} max diff {delta:6.2f}")
    return delta <= limit


def check_images(gpu, cpu, img):
    ok = True
    ok &= report("blur", gpu.blur(img, 3), cpu.blur(img, 3))
    ok &= report("heat", gpu.heat(img, 1.0, 4.0, 24.0),
                 cpu.heat(img, 1.0, 4.0, 24.0), 6, True)
    ok &= report("ripple", gpu.ripple(img, 1.0, 4.0, 40.0),
                 cpu.ripple(img, 1.0, 4.0, 40.0), 6, True)
    ok &= report("mix", gpu.mix(img, img[::-1], 0.35),
                 cpu.mix(img, img[::-1], 0.35))
    ok &= report("stretch", gpu.stretch(img, 20.0, 200.0),
                 cpu.stretch(img, 20.0, 200.0))
    field = gpu.glow(img, 0.55, 3, 2)
    ok &= report("glow", field, cpu.glow(img, 0.55, 3, 2), 6)
    ok &= report("composite", gpu.composite(img, field, 1.15, 1.0, 0.3, 0.6),
                 cpu.composite(img, field, 1.15, 1.0, 0.3, 0.6), 6)
    return ok


def check_lights(gpu, cpu, img):
    pos = np.array([[40.0, 50.0], [120.0, 90.0], [300.0, 170.0]],
                   np.float32)
    col = np.array([[1.0, 0.2, 0.1, 3.0], [0.2, 1.0, 0.3, 2.0],
                    [0.9, 0.9, 1.0, 4.0]], np.float32)
    lights = np.array([[50.0, 60.0, 90.0, 1.5, 1.0, 0.9, 0.6],
                       [250.0, 120.0, 70.0, 0.8, 0.2, 0.4, 1.0]], np.float32)
    ok = report("particles", gpu.particles(img, pos, col, 1.0),
                cpu.particles(img, pos, col, 1.0))
    ok &= report("lights", gpu.lights(img, lights, 1.0),
                 cpu.lights(img, lights, 1.0))
    ok &= report("trail", gpu.trail(img, img[::-1], 0.4)[0],
                 cpu.trail(img, img[::-1], 0.4)[0])
    return ok


def check_analysis(gpu, cpu, img):
    ok = report("histogram", gpu.histogram(img), cpu.histogram(img), 0)
    grid_gpu = gpu.minimap(img, 64, 36)
    grid_cpu = cpu.minimap(img, 64, 36)
    ok &= report("minimap", grid_gpu * 255.0, grid_cpu * 255.0, 6)
    heat = np.zeros((36, 64), np.float32)
    points = np.array([[10.0, 5.0], [30.0, 20.0], [63.0, 35.0]], np.float32)
    ok &= report("heat_splat", gpu.heat_splat(points, heat, 2.0),
                 cpu.heat_splat(points, heat.copy(), 2.0), 0)
    ok &= report("heat_colors", gpu.heat_colors(heat + 1.0, 3.0),
                 cpu.heat_colors(heat + 1.0, 3.0))
    return ok


def main():
    if not env.setup():
        print("No toolchain: set FDC_GPU_TOOLCHAIN (see INSTALACION.md)")
        return 1
    if not backend.available():
        print("PyCUDA/CUDA not available")
        return 1
    rng = np.random.default_rng(SEED)
    img = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)
    img[40:90, 100:180] = 240          # a bright patch for the glow
    gpu = backend.Gpu()
    cpu = cpu_ref.Cpu()
    print(f"GPU: {backend.device_name()}  arch {gpu.arch}  {W}x{H}")
    ok = check_images(gpu, cpu, img)
    ok &= check_lights(gpu, cpu, img)
    ok &= check_analysis(gpu, cpu, img)
    _, ms = timed(gpu.composite, img, gpu.glow(img, 0.55, 3, 2),
                  1.15, 1.0, 0.3, 0.6)
    points, ms_blur = timed(gpu.blur, img, 3)
    print(f"  gpu blur 3px: {ms_blur:.3f} ms   gpu composite: {ms:.3f} ms")
    print("SELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
