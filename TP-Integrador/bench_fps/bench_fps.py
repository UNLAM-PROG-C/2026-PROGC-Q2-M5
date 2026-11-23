"""FPS per visual effect, without the 60 FPS cap (Presentation mode).

Usage (project root, GPU venv active):
  python bench_fps/bench_fps.py BACKEND QUALITY SECONDS OUT.json
    BACKEND: gpu | cpu      QUALITY: full | sin-efectos
Runs the real App with SDL "dummy" (tests/driver.py) at the default
1280x720 window. For each effect it presses its key and renders frames as
fast as possible for SECONDS, pressing the key again whenever the effect
expires. Reports the average FPS, the 1% low (FPS at the 99th percentile
frame time) and the minimum FPS.
"""
import json
from pathlib import Path
import statistics
import sys
import time

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "tests")]

import driver  # noqa: E402  (SDL dummy)
import main  # noqa: E402
import pygame  # noqa: E402
from fdc import protocol  # noqa: E402
from fdc.ui import presentation  # noqa: E402

PERCENTILE_99 = 0.99
RETRY_S = 1.0        # s to wait for the simulation before pressing again
CLEAR_TIMEOUT_S = 30.0  # s for the leftover effects to end between rows


def make(backend, quality):
  args = ["--presentation", "--backend", backend, "--calidad", quality,
          "--no-audio", "--seed", "7", "--overlay", "off"]
  options = main.parse_args(args)
  main.apply_gpu_options(options)
  options.profile_path = driver.profile_file()
  return driver._TestApp(options)  # pylint: disable=protected-access


def playing(d):
  s = d.screen()
  return (isinstance(s, presentation.PresentationScreen) and s.state
          and s.state["phase"] == protocol.PHASE_PLAYING)


def stats(times, total):
  ordered = sorted(times)
  p99 = ordered[min(len(ordered) - 1, int(len(ordered) * PERCENTILE_99))]
  return {"frames": len(times), "seconds": round(total, 2),
          "fps_avg": round(len(times) / total, 1),
          "fps_p1": round(1.0 / p99, 1),
          "fps_min": round(1.0 / ordered[-1], 1),
          "fps_median": round(1.0 / statistics.median(ordered), 1)}


def is_active(d, name):
  """Sim powers (ice, fire) live in the simulation: ask the effects chain."""
  if name in presentation.SIM_DURATIONS:
    return d.app.postfx.active_effects() != "ninguno"
  return d.screen().effects.left(name) > 0


def press(key):
  pygame.event.post(driver._key_event(pygame.KEYDOWN, key))  # pylint: disable=protected-access
  pygame.event.post(driver._key_event(pygame.KEYUP, key))  # pylint: disable=protected-access


def measure(d, secs, key=None, name=None):
  """Uncapped frames for secs; re-presses key when the effect expires."""
  d.app.clock.sleep = False
  times, active, presses, seen = [], 0, 0, set()
  t0 = last = time.perf_counter()
  if key is not None:
    press(key); presses += 1
  while time.perf_counter() - t0 < secs:
    now = time.perf_counter()
    if key is not None and now - last > RETRY_S and not is_active(d, name):
      press(key); presses += 1; last = now
    d.app.frame()
    times.append(time.perf_counter() - now)
    if key is not None and is_active(d, name):
      active += 1
      seen.add(d.app.postfx.active_effects())
  r = stats(times, time.perf_counter() - t0)
  d.app.clock.sleep = True
  if key is not None:
    r.update(active_share=round(active / len(times), 3), presses=presses,
             seen=sorted(seen))
  return r


def run(backend, quality, secs, out):
  game = make(backend, quality)
  d = driver.Driver(game)
  res = {"backend": backend, "quality": quality, "secs": secs}
  try:
    d.until(lambda: playing(d), timeout=60)
    d.seconds(2.0)
    res["window"] = list(game.screen.get_size())
    res["full"] = game.postfx.enabled
    res["rows"] = {"sin efecto": measure(d, secs)}
    print("sin efecto", res["rows"]["sin efecto"], flush=True)
    if quality == "full":
      for key, (name, label) in presentation.SHORTCUTS.items():
        res["rows"][label] = measure(d, secs, key, name)
        res["rows"][label]["full"] = game.postfx.enabled
        print(label, res["rows"][label], flush=True)
        d.tap(pygame.K_0, frames_after=10)
        d.until(lambda: d.app.postfx.active_effects() == "ninguno",
                timeout=CLEAR_TIMEOUT_S)
        d.frames(10)
  finally:
    text = json.dumps(res, indent=1, ensure_ascii=False)
    Path(out).write_text(text, encoding="utf-8")
    game.shutdown()


if __name__ == "__main__":
  run(sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4])
