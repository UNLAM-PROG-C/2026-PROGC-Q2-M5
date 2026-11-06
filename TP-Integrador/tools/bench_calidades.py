"""Measures the quality modes on the CPU backend, headless.

Usage (PowerShell, from the repository, with the venv installed):
    py tools\\bench_calidades.py                 # 180 frames, the 3 modes
    py tools\\bench_calidades.py --frames 400
    py tools\\bench_calidades.py --modes full optimizado

It plays a real match with `--backend cpu` (numpy, no CUDA at all) and prints
the real FPS of the loop, the mean frame time and the cost of the chain, so
the machines without NVIDIA know what to expect from FULL and OPTIMIZADO.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DEFAULT_FRAMES = 180        # frames per mode (enough for a stable mean)
MODES = ("full", "optimizado", "auto")
MS = 1000.0                 # ms per second, for the frame time


def parse_args(argv=None):
    """Options of the measurement."""
    parser = argparse.ArgumentParser(description="FPS of the CPU modes.")
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES,
                        help="frames measured per mode")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=MODES,
                        help="quality modes to measure (default: all)")
    return parser.parse_args(argv)


def measure(mode, frames):
    """Runs the real loop in one mode with the numpy backend.

    `--gpu-cpu` is the flag that `PostFx` reads (the demo builds the window
    directly, so `main._apply_gpu_options` never turns `--backend cpu` into
    `force_cpu` for it).
    """
    # pylint: disable-next=import-outside-toplevel
    from fdc.gpu import demo
    return demo.run(frames, ["--backend", "cpu", "--gpu-cpu",
                             "--calidad", mode])


def table(rows):
    """Header and one line per measured mode."""
    print(f"{'modo':<11} {'fps':>7} {'frame':>8} {'efectos':>8} "
          f"{'nivel':>6} {'backend':<4} efectos activos")
    for mode, data in rows:
        print(f"{mode:<11} {data['fps_loop']:>7.1f} {data['ms_frame']:>8.1f} "
              f"{data.get('frame', 0.0):>8.2f} {data['quality_level']:>6} "
              f"{data['mode']:<4} {data['active']}")


def main(argv=None):
    """Measures every requested mode and prints the table."""
    options = parse_args(argv)
    # pylint: disable-next=import-outside-toplevel
    from fdc.gpu import demo
    demo.headless()
    rows = [(mode, measure(mode, options.frames))
            for mode in options.modes]
    table(rows)
    print(f"\nframes por modo: {options.frames}   "
          f"ms de frame = {MS:.0f} / fps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
