"""Benchmark of the kernels: resolutions, repetitions and block sizes (F8).

It measures gray, sobel, glow_composite, crt and the VAR look with the GPU
and with numpy, writes a CSV in the measurements folder and a Markdown
table, and with --blocks tries the block sizes of the spec (8x8 ... 32x32):
the ones CUDA rejects (more than 1024 threads or too many registers) are
listed as 'error' instead of breaking the run. The commands are in the
README (`py tools\\bench_gpu.py`).
"""
import csv
import datetime
import os
import shutil
import subprocess
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fdc import config                             # noqa: E402
from fdc.gpu import backend                         # noqa: E402
from fdc.gpu import cpu_ref                         # noqa: E402
from fdc.gpu import env                             # noqa: E402

G = config.Gpu
REPEAT = 20                      # runs of each stage (the mean is reported)
MS_PER_S = 1000.0                # milliseconds in a second
SEED = 5                         # fixed scene (repeatable)
BYTE = 256                       # gray levels of the random scene
CHANNELS = 3                     # RGB
FRAME = 7                        # frame number of the CRT grain
QUARTER = 4                      # the bright patch starts at 1/4
HALF = 2                         # ... and ends at 1/2
BRIGHT = 240                     # gray level of that patch
NSYS_TIMEOUT = 600               # s before giving up on Nsight
DEFAULT_RES = "1280x720"
BLOCKS = ("8x8", "16x8", "16x16", "32x8", "32x16", "32x32")
FOLDER = os.path.join(ROOT, "mediciones")
STAMP = "%Y%m%d-%H%M%S"
CSV_COLUMNS = ("kernel", "backend", "resolution", "block", "ms", "speedup")
ROUND = 3                        # decimals of the CSV
STAGES = ("gray", "sobel", "glow_composite", "crt", "var_look")
NSYS = "nsys"


def scene(width, height):
  """Random RGB frame with a bright patch (repeatable)."""
  rng = np.random.default_rng(SEED)
  img = rng.integers(0, BYTE, (height, width, CHANNELS), dtype=np.uint8)
  img[height // QUARTER:height // HALF, width // QUARTER:width // HALF] = (
      BRIGHT)
  return img


def mean_ms(ops, name, *args):
  """Mean milliseconds of one call of `name` (sync before and after)."""
  method = getattr(ops, name)
  backend.sync()
  method(*args)                    # warm up (compile, allocations)
  backend.sync()
  start = time.perf_counter()
  for _ in range(REPEAT):
    method(*args)
  backend.sync()
  return (time.perf_counter() - start) * MS_PER_S / REPEAT


def var_look(ops, img):
  """The VAR look: five ops of the chain (spec 5.4)."""
  edges = ops.sobel(ops.to_gray(img))
  norm = ops.sobel_normalize(edges, float(edges.max() or 1.0))
  return ops.edge_glow(ops.gray(img), ops.tint(norm, G.VAR_TINT),
                       G.VAR_EDGES)


def mean_fn(ops, fn, *args):
  """Mean milliseconds of a Python function of the ops."""
  backend.sync()
  fn(ops, *args)
  backend.sync()
  start = time.perf_counter()
  for _ in range(REPEAT):
    fn(ops, *args)
  backend.sync()
  return (time.perf_counter() - start) * MS_PER_S / REPEAT


def stage_rows(gpu, cpu, img, size):
  """[(kernel, gpu ms, cpu ms)] of the stages at one resolution."""
  args = _stage_args(img, cpu)
  rows = []
  for name in STAGES[:-1]:
    gpu_ms = mean_ms(gpu, name, *args[name]) if gpu else 0.0
    rows.append((name, gpu_ms, mean_ms(cpu, name, *args[name])))
  gpu_ms = mean_fn(gpu, var_look, img) if gpu else 0.0
  rows.append(("var_look", gpu_ms, mean_fn(cpu, var_look, img)))
  return [(name, gpu_ms, cpu_ms, size) for name, gpu_ms, cpu_ms in rows]


def _stage_args(img, cpu):
  """Arguments of each kernel for this image."""
  return {
      "gray": (img,),
      "sobel": (cpu.to_gray(img),),
      "glow_composite": (img, G.GLOW_THRESHOLD, G.GLOW_RADIUS,
                         G.GLOW_PASSES, (G.EXPOSURE, G.GAMMA, G.VIGNETTE,
                                         G.GLOW_STRENGTH)),
      "crt": (img, FRAME, G.CRT_AMOUNT, G.CRT_SCAN, G.CRT_VIGNETTE,
              G.CRT_NOISE, G.CRT_ROWS, G.CRT_TINT),
  }


def block_rows(gpu, img):
  """[(block, ms, error)] with each block size of the spec."""
  rows = []
  for name in BLOCKS:
    try:
      backend.set_block(name)
      rows.append((name, mean_ms(gpu, "gray", img), None))
    except Exception as exc:        # pylint: disable=broad-except
      rows.append((name, 0.0, type(exc).__name__))
  backend.set_block("32x8")
  return rows


def write_csv(rows, path):
  """CSV with one row per kernel, backend and resolution."""
  with open(path, "w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(CSV_COLUMNS)
    for name, gpu_ms, cpu_ms, size in rows:
      speed = round(cpu_ms / gpu_ms, ROUND) if gpu_ms else 0.0
      writer.writerow([name, "gpu", size, "", round(gpu_ms, ROUND),
                       speed])
      writer.writerow([name, "cpu", size, "", round(cpu_ms, ROUND), 1.0])
  return path


def markdown(rows):
  """Markdown table of the benchmark."""
  lines = ["| kernel | resolución | GPU ms | numpy ms | x |",
           "|---|---|---|---|---|"]
  for name, gpu_ms, cpu_ms, size in rows:
    speed = cpu_ms / gpu_ms if gpu_ms else 0.0
    lines.append(f"| {name} | {size} | {gpu_ms:.2f} | {cpu_ms:.2f} | "
                 f"{speed:.1f} |")
  return "\n".join(lines)


def show(rows, blocks):
  """Prints the tables and the totals."""
  print(markdown(rows))
  total_gpu = sum(gpu for _, gpu, _, _ in rows)
  total_cpu = sum(cpu for _, _, cpu, _ in rows)
  print(f"\ntotal GPU {total_gpu:.2f} ms · numpy {total_cpu:.2f} ms · "
        f"x{total_cpu / total_gpu if total_gpu else 0:.1f}")
  if blocks:
    print(f"\n{'bloque':8} {'gray ms':>9}  estado")
    for name, ms, error in blocks:
      print(f"{name:8} {ms:9.3f}  {error or 'ok'}")


def nsys_attempt():
  """Runs Nsight Systems if it is installed; returns True if it ran."""
  if not shutil.which(NSYS):
    print("nsys no está en el PATH: se mide con time.perf_counter()")
    return False
  out = os.path.join(FOLDER, "nsys_bench")
  command = [NSYS, "profile", "--stats=true", "-o", out, sys.executable,
             os.path.abspath(__file__), "--reps", "3"]
  print("corriendo: " + " ".join(command))
  try:
    subprocess.run(command, check=False, timeout=NSYS_TIMEOUT)
    return True
  except (OSError, subprocess.SubprocessError) as exc:
    print(f"nsys falló: {exc}")
    return False


def main(argv):
  """Benchmark with the GPU if there is one (numpy only if not)."""
  global REPEAT                  # pylint: disable=global-statement
  os.makedirs(FOLDER, exist_ok=True)
  sizes = _resolutions(argv)
  REPEAT = _int_option(argv, "--reps", REPEAT)
  gpu = _gpu()
  rows = _measure(sizes, gpu, cpu_ref.Cpu())
  blocks = _blocks(argv, gpu, sizes)
  path = _save(rows)
  _report(rows, blocks, path, argv)
  return 0


def _report(rows, blocks, path, argv):
  """Tables, path of the CSV and the optional Nsight run."""
  show(rows, blocks)
  print(f"\nCSV: {path}")
  if "--nsys" in argv:
    nsys_attempt()


def _gpu():
  """The GPU backend, or None when there is no CUDA."""
  if env.setup() and backend.available():
    print(f"GPU: {backend.device_name()}")
    return backend.Gpu()
  print("no hay CUDA ni toolchain (ver INSTALACION.md): solo numpy")
  return None


def _measure(sizes, gpu, cpu):
  """Every stage at every resolution."""
  rows = []
  for size in sizes:
    width, height = _pair(size)
    rows.extend(stage_rows(gpu, cpu, scene(width, height), size))
  return rows


def _blocks(argv, gpu, sizes):
  """Block sweep when --blocks is asked and there is a GPU."""
  if "--blocks" not in argv or not gpu:
    return []
  return block_rows(gpu, scene(*_pair(sizes[0])))


def _save(rows):
  """Writes the CSV and returns its path."""
  path = os.path.join(FOLDER, "bench_" +
                      datetime.datetime.now().strftime(STAMP) + ".csv")
  return write_csv(rows, path)


def _pair(size):
  """'1280x720' -> (1280, 720)."""
  width, height = (int(part) for part in size.split("x"))
  return width, height


def _resolutions(argv):
  """`--resolutions a,b` or the default 1280x720."""
  if "--resolutions" in argv:
    index = argv.index("--resolutions")
    if index + 1 < len(argv):
      return argv[index + 1].split(",")
  return [DEFAULT_RES]


def _int_option(argv, name, default):
  """Integer value of `name` in the command line."""
  if name in argv:
    index = argv.index(name)
    if index + 1 < len(argv):
      return int(argv[index + 1])
  return default


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
