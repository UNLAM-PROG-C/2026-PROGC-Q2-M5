"""Run every method on 720p and 1080p frames and save results.json."""
import json
import os
import platform
import sys

import numpy as np

import cpu_bench
import gpu_bench
import race_cpu
from frames import SIZES, make_frame, reference

SCENES = ('uniform', 'night')
GPU_RUNS = 200  # kernel-only launches per case
FIVE_STEP_RUNS = 50  # full cycles per case
CPU_RUNS = {'d_lock': 3, 'e_private': 5, 'f_bincount': 30}
CPU_METHODS = {'d_lock': cpu_bench.lock_per_increment,
               'e_private': cpu_bench.private_merge,
               'f_bincount': cpu_bench.numpy_bincount}
OUTPUT = os.path.join(os.path.dirname(__file__), 'results.json')


def _check(result, expected):
  return {'ok': bool(np.array_equal(result, expected)),
          'total': int(result.sum()), 'expected': int(expected.sum())}


def _gpu_cases(gpu, rgb, expected):
  rows = {}
  for key in ('a_global', 'b_shared'):
    kernel, result = gpu.kernel_ms(key, rgb, GPU_RUNS)
    full = gpu.five_steps_ms(key, rgb, FIVE_STEP_RUNS)
    rows[key] = dict(_check(result, expected), kernel_ms=kernel,
                     five_steps_ms=full)
  return rows


def _cpu_cases(rgb, expected):
  rows = {}
  for key, method in CPU_METHODS.items():
    ms, result = cpu_bench.median_ms(method, rgb, CPU_RUNS[key])
    rows[key] = dict(_check(result, expected), ms=ms)
  return rows


def _race_cases(gpu, rgb, expected):
  return {'gpu_racy': _check(gpu.kernel_ms('race', rgb, 1)[1], expected),
          'threads_no_lock': _check(cpu_bench.threads_no_lock(rgb), expected),
          'processes_no_lock': _check(race_cpu.processes_no_lock(rgb),
                                      expected)}


def _case(gpu, size, scene):
  rgb = make_frame(SIZES[size], scene)
  expected = reference(rgb)
  row = {'size': size, 'scene': scene, 'pixels': int(expected.sum())}
  row.update(_gpu_cases(gpu, rgb, expected))
  row.update(_cpu_cases(rgb, expected))
  row['race'] = _race_cases(gpu, rgb, expected)
  print(json.dumps(row), flush=True)
  return row


def _environment():
  info = gpu_bench.device_info()
  info.update(cpu=platform.processor(), cores=os.cpu_count(),
              os=platform.platform(), python=sys.version.split()[0],
              numpy=np.__version__, threads=cpu_bench.THREADS,
              processes=race_cpu.PROCESSES, gpu_runs=GPU_RUNS,
              five_step_runs=FIVE_STEP_RUNS, cpu_runs=CPU_RUNS)
  return info


def main():
  gpu = gpu_bench.GpuHistogram()
  cases = [_case(gpu, size, scene) for size in SIZES for scene in SCENES]
  with open(OUTPUT, 'w', encoding='utf-8') as handle:
    json.dump({'environment': _environment(), 'cases': cases}, handle,
              indent=2)
  print('saved', OUTPUT)


if __name__ == '__main__':
  main()
