"""The university demo, headless: ten segments, both backends, one CSV.

It prints one line per segment and backend with the real FPS, the mean and
p95 of the frame, the cost of the chain and the path of the CSV. The
command is `py tools\\run_demo.py` (see the README).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
EFFECT_WIDTH = 32           # columns of the effect name in the table
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from fdc.gpu import demo  # noqa: E402  pylint: disable=wrong-import-position
from fdc.gpu import env   # noqa: E402  pylint: disable=wrong-import-position


def main(argv):
    """Runs the demo and prints its table."""
    env.setup()
    report = demo.run_demo(argv)
    _table(report)
    print(f"\nCSV: {report['csv']}")
    if not report["finished"]:
        print("La demo no llegó al final (¿pocos frames?).")
    return 0


def _table(report):
    """One line per row of the measurement log."""
    print(f"{'#':>2} {'efecto':<{EFFECT_WIDTH}} {'backend':<6} {'fps':>7} "
          f"{'work':>7} {'p95':>7} {'fx':>7}")
    for row in report["rows"]:
        effect = row["effect"][:EFFECT_WIDTH]
        print(f"{row['segment_index']:>2} {effect:<{EFFECT_WIDTH}} "
              f"{row['backend']:<6} {row['fps_real_mean']:>7.1f} "
              f"{row['work_ms_mean']:>7.2f} {row['work_ms_p95']:>7.2f} "
              f"{row['fx_ms_mean']:>7.2f}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
