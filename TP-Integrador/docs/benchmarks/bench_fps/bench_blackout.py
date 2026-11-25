"""FPS of the plain mode with and without the blackout (no 60 FPS cap).

Usage (project root):
  python docs/benchmarks/bench_fps/bench_blackout.py SECONDS OUT.json
Same method as bench_fps.py: the real App, SDL "dummy", 1280x720, frames as
fast as possible; the blackout row presses key 5 again whenever it expires.
"""
import json
from pathlib import Path
import sys

import bench_fps
import driver
import pygame

BACKEND = "cpu"
QUALITY = "sin-efectos"
START_TIMEOUT_S = 60
WARMUP_S = 2.0


def run(secs, out):
  game = bench_fps.make(BACKEND, QUALITY)
  d = driver.Driver(game)
  res = {"backend": BACKEND, "quality": QUALITY, "secs": secs}
  try:
    d.until(lambda: bench_fps.playing(d), timeout=START_TIMEOUT_S)
    d.seconds(WARMUP_S)
    res["window"] = list(game.screen.get_size())
    res["full"] = game.postfx.enabled
    res["rows"] = rows(d, secs)
  finally:
    Path(out).write_text(json.dumps(res, indent=1, ensure_ascii=False),
                         encoding="utf-8")
    game.shutdown()


def rows(d, secs):
  plain = bench_fps.measure(d, secs)
  print("sin apagon", plain, flush=True)
  dark = bench_fps.measure(d, secs, pygame.K_5, "blackout")
  print("con apagon", dark, flush=True)
  dark["builds"] = d.app.simple_blackout.builds
  return {"sin apagon": plain, "con apagon": dark}


if __name__ == "__main__":
  run(float(sys.argv[1]), sys.argv[2])
