"""CPU (numpy) vs GPU benchmark of five representative kernels.

Cases: k_gray, ice (k_ice_edges + k_ice_apply), k_spotlights, k_crt
and k_luma_hist (uses atomicAdd). Resolutions: 640x360, 1280x720, 1920x1080.

Each GPU run follows the five steps of the course (reserve, upload, kernel,
download, free) and records the kernel alone with CUDA events. The CPU run
is the numpy reference of `fdc.gpu.cpu_ref`. After a warm-up, every
measurement repeats `--runs` times (at least 50) and the median is kept.

Run it on the PC with the GPU (PowerShell, from the repo root):

    py tools\\benchmark_cpu_gpu.py
    py tools\\benchmark_cpu_gpu.py --runs 100 --out mediciones\\bench.json

The JSON has one entry per kernel and resolution, with the median of each
step, the kernel-only time, the total with transfers, the CPU time and the
two speedups (kernel only and total with transfers).
"""
import argparse
import datetime
import json
import os
import statistics
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fdc.gpu import backend                         # noqa: E402
from fdc.gpu import cpu_ref                         # noqa: E402

RESOLUTIONS = ((640, 360), (1280, 720), (1920, 1080))   # width, height
DEFAULT_RUNS = 50                # measured runs of each measurement
MIN_RUNS = 50                    # the spec asks for at least 50
WARMUP = 5                       # runs that are thrown away
MS_PER_S = 1000.0                # milliseconds in a second
STEPS = ("reserve", "upload", "kernel", "download", "free")
SEED = 7                         # fixed scene (repeatable)
BYTE = 256                       # gray levels of the random scene
CHANNELS = 3                     # RGB
ICE_ARGS = (0.6, (0.55, 0.85, 1.0), 1.0)   # edge strength, tint, blend
CRT_FRAME = 5                     # frame index for repeatable noise
CRT_ROWS = 3                      # rows between scan lines
CRT_LOOK = (0.9, 0.35, 0.45, 0.1)  # blend, scan, vignette, grain
CRT_TINT = (0.80, 1.0, 0.85)      # phosphor tint (RGB)
ICE_DST = 3                       # buffer index of the final ice result
LAMPS = ((0.3, 0.4, 0.25, 1.0), (0.7, 0.5, 0.3, 0.8))   # x, y, r, power
AMBIENT = 0.35                   # light of the unlit scene
LAMP_TINT = (1.0, 0.9, 0.7)      # warm colour of the lamps
LAMP_CAP = 0.0                   # no brightness limit
BINS = 256                       # bins of the luma histogram
ROUND = 4                        # decimals of the JSON
FOLDER = os.path.join(ROOT, "mediciones")
STAMP = "%Y%m%d-%H%M%S"


def scene(width, height):
  """Random RGB frame (repeatable)."""
  rng = np.random.default_rng(SEED)
  return rng.integers(0, BYTE, (height, width, CHANNELS), dtype=np.uint8)


def buf(host, up=False, down=False):
  """A device buffer: (host array, upload it?, download into it?)."""
  return host, up, down


def case_gray(img):
  """(buffers, launches) of k_gray: src, dst."""
  h, w = img.shape[:2]
  size = (np.int32(w), np.int32(h))
  bufs = [buf(img, up=True), buf(np.empty_like(img), down=True)]
  return bufs, [("k_gray", (0, 1, *size))]


def case_ice(img):
  """Ice edges and maximum, then the tint in a second launch."""
  h, w = img.shape[:2]
  size = (np.int32(w), np.int32(h))
  bufs = [buf(img, up=True), buf(np.empty((h, w), np.float32)),
          buf(np.zeros(1, np.uint32), up=True),
          buf(np.empty_like(img), down=True)]
  strength, tint, amount = ICE_ARGS
  params = tuple(map(np.float32, (strength, *tint, amount)))
  return bufs, [("k_ice_edges", (0, 1, 2, *size)),
                ("k_ice_apply", (0, 1, 2, ICE_DST, *size, *params))]


def lamps_in_pixels(w, h):
  """Lamps (x, y, radius, power) with the position in pixels."""
  scale = np.array((w, h, h, 1.0), np.float32)
  return np.asarray(LAMPS, np.float32) * scale


def case_spotlights(img):
  """k_spotlights: src, dst and the table of lamps."""
  h, w = img.shape[:2]
  lamps = lamps_in_pixels(w, h)
  tint = tuple(np.float32(c) for c in LAMP_TINT)
  tail = (np.int32(len(lamps)), np.float32(AMBIENT), *tint,
          np.float32(LAMP_CAP))
  bufs = [buf(img, up=True), buf(np.empty_like(img), down=True),
          buf(lamps.reshape(-1), up=True)]
  return bufs, [("k_spotlights", (0, 1, np.int32(w), np.int32(h), 2, *tail))]


def case_crt(img):
  """The CRT pass: source, destination and scalar TV settings."""
  h, w = img.shape[:2]
  size = (np.int32(w), np.int32(h))
  look = tuple(map(np.float32, CRT_LOOK))
  tint = tuple(map(np.float32, CRT_TINT))
  args = (0, 1, *size, np.int32(CRT_FRAME), *look, np.int32(CRT_ROWS),
          *tint)
  return [buf(img, up=True), buf(np.empty_like(img), down=True)], [
      ("k_crt", args)]


def case_luma_hist(img):
  """k_luma_hist (atomicAdd): src, histogram and maximum."""
  h, w = img.shape[:2]
  hist = np.zeros(BINS, np.uint32)
  top = np.zeros(1, np.uint32)
  bufs = [buf(img, up=True), buf(hist, up=True, down=True),
          buf(top, up=True, down=True)]
  return bufs, [("k_luma_hist", (0, 1, 2, np.int32(w), np.int32(h)))]


def cpu_spotlights(cpu, img):
  """Same lamps as the GPU case."""
  h, w = img.shape[:2]
  return cpu.spotlights(img, lamps_in_pixels(w, h), AMBIENT, LAMP_TINT,
                        LAMP_CAP)


CASES = (
    ("k_gray", case_gray, lambda cpu, img: cpu.gray(img)),
    ("ice", case_ice, lambda cpu, img: cpu.ice(img, *ICE_ARGS)),
    ("k_spotlights", case_spotlights, cpu_spotlights),
    ("k_crt", case_crt, lambda cpu, img: cpu.crt(
        img, CRT_FRAME, *CRT_LOOK, CRT_ROWS, CRT_TINT)),
    ("k_luma_hist", case_luma_hist, lambda cpu, img: cpu.luma_stats(img)),
)


def sync_step(gpu, times, name, start):
  """Wait for the device and store the milliseconds since `start`."""
  gpu.driver.Context.synchronize()
  times[name] = (time.perf_counter() - start) * MS_PER_S


def alloc(gpu, bufs, times):
  """Step 1: one device buffer per host array."""
  start = time.perf_counter()
  devs = [gpu.driver.mem_alloc(host.nbytes) for host, _, _ in bufs]
  sync_step(gpu, times, "reserve", start)
  return devs


def upload(gpu, bufs, devs, times):
  """Step 2: host to device copies."""
  start = time.perf_counter()
  for (host, up, _), dev in zip(bufs, devs):
    if up:
      gpu.driver.memcpy_htod(dev, np.ascontiguousarray(host))
  sync_step(gpu, times, "upload", start)


def launch(gpu, devs, launches, shape):
  """Queue every kernel of the case (grid for a w x h image)."""
  height, width = shape
  for name, args in launches:
    real = [devs[a] if isinstance(a, int) else a for a in args]
    gpu._fn(name)(*real, grid=backend.grid_for(width, height),
                  block=backend.BLOCK)


def run_kernel(gpu, devs, launches, shape, times):
  """Step 3: the kernel, timed with wall clock and with CUDA events."""
  begin, end = gpu.driver.Event(), gpu.driver.Event()
  start = time.perf_counter()
  begin.record()
  launch(gpu, devs, launches, shape)
  end.record()
  end.synchronize()
  sync_step(gpu, times, "kernel", start)
  times["kernel_events"] = begin.time_till(end)


def download(gpu, bufs, devs, times):
  """Step 4: device to host copies."""
  start = time.perf_counter()
  for (host, _, down), dev in zip(bufs, devs):
    if down:
      gpu.driver.memcpy_dtoh(host, dev)
  sync_step(gpu, times, "download", start)


def release(gpu, devs, times):
  """Step 5: free the device memory."""
  start = time.perf_counter()
  for dev in devs:
    dev.free()
  sync_step(gpu, times, "free", start)


def gpu_run(gpu, builder, img):
  """One full five-step run: dict of milliseconds."""
  bufs, launches = builder(img)
  times = {}
  devs = alloc(gpu, bufs, times)
  try:
    upload(gpu, bufs, devs, times)
    run_kernel(gpu, devs, launches, img.shape[:2], times)
    download(gpu, bufs, devs, times)
  finally:
    release(gpu, devs, times)
  times["total"] = sum(times[name] for name in STEPS)
  return times


def cpu_run(cpu, fn, img):
  """Milliseconds of one numpy run."""
  start = time.perf_counter()
  fn(cpu, img)
  return {"ms": (time.perf_counter() - start) * MS_PER_S}


def repeat(fn, runs):
  """Warm up, then `runs` results of `fn`."""
  for _ in range(WARMUP):
    fn()
  return [fn() for _ in range(runs)]


def medians(samples):
  """Median of each key over a list of dicts."""
  return {key: round(statistics.median(s[key] for s in samples), ROUND)
          for key in samples[0]}


def speedup(cpu_ms, gpu_ms):
  """CPU time over GPU time (0 if the GPU time is 0)."""
  return round(cpu_ms / gpu_ms, ROUND) if gpu_ms else 0.0


def measure(gpu, cpu, case, size, runs):
  """Result of one kernel at one resolution."""
  name, builder, cpu_fn = case
  img = scene(*size)
  gpu_ms = medians(repeat(lambda: gpu_run(gpu, builder, img), runs))
  cpu_ms = medians(repeat(lambda: cpu_run(cpu, cpu_fn, img), runs))["ms"]
  return {"kernel": name, "resolution": f"{size[0]}x{size[1]}",
          "gpu_steps_ms": {step: gpu_ms[step] for step in STEPS},
          "gpu_kernel_events_ms": gpu_ms["kernel_events"],
          "gpu_total_ms": gpu_ms["total"], "cpu_ms": cpu_ms,
          "speedup_kernel": speedup(cpu_ms, gpu_ms["kernel_events"]),
          "speedup_total": speedup(cpu_ms, gpu_ms["total"])}


def run_all(runs):
  """Every kernel at every resolution."""
  gpu, cpu = backend.Gpu(), cpu_ref.Cpu()
  return [measure(gpu, cpu, case, size, runs)
          for size in RESOLUTIONS for case in CASES]


def parse_args(argv):
  """Command line: --runs (at least 50) and --out."""
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--runs", type=int, default=DEFAULT_RUNS,
                      help="measured runs (at least %d)" % MIN_RUNS)
  parser.add_argument("--out", help="JSON file to write")
  args = parser.parse_args(argv)
  if args.runs < MIN_RUNS:
    parser.error("--runs must be at least %d" % MIN_RUNS)
  return args


def default_out():
  """Timestamped file in the measurements folder."""
  stamp = datetime.datetime.now().strftime(STAMP)
  return os.path.join(FOLDER, f"benchmark_cpu_gpu-{stamp}.json")


def write_report(results, runs, path):
  """Write the JSON report and return its path."""
  report = {"device": backend.device_name(), "runs": runs,
            "warmup": WARMUP, "statistic": "median", "results": results}
  os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
  with open(path, "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2)
  return path


def main(argv=None):
  args = parse_args(argv)
  print(write_report(run_all(args.runs), args.runs,
                     args.out or default_out()))


if __name__ == "__main__":
  main()
