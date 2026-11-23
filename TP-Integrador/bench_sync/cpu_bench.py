"""CPU luma histogram: shared lock, private histograms and numpy."""
import statistics
import threading
import time

import numpy as np

from frames import BINS, luma_bins

THREADS = 8  # Python threads for (d) and (e)
MS_PER_SECOND = 1000  # milliseconds per second


def _chunks(rgb, parts):
  """Split the frame by rows so each thread owns a band of pixels."""
  return np.array_split(rgb, parts, axis=0)


def _run_threads(target, rgb, *args):
  workers = [threading.Thread(target=target, args=(chunk,) + args)
             for chunk in _chunks(rgb, THREADS)]
  for worker in workers:
    worker.start()
  for worker in workers:
    worker.join()


def _add_locked(chunk, hist, lock):
  for b in luma_bins(chunk).tolist():
    with lock:
      hist[b] += 1


def lock_per_increment(rgb):
  """(d) One shared histogram, one threading.Lock taken per pixel."""
  hist, lock = [0] * BINS, threading.Lock()
  _run_threads(_add_locked, rgb, hist, lock)
  return np.array(hist, dtype=np.uint32)


def _add_private(chunk, partials, lock):
  local = [0] * BINS
  for b in luma_bins(chunk).tolist():
    local[b] += 1
  with lock:
    partials.append(local)


def private_merge(rgb):
  """(e) Each thread fills its own histogram; one merge at the end."""
  partials, lock = [], threading.Lock()
  _run_threads(_add_private, rgb, partials, lock)
  return np.array(partials, dtype=np.uint32).sum(axis=0, dtype=np.uint32)


def numpy_bincount(rgb):
  """(f) Single thread, vectorized: the reference."""
  return np.bincount(luma_bins(rgb), minlength=BINS).astype(np.uint32)


def _add_unlocked(chunk, hist):
  for b in luma_bins(chunk).tolist():
    hist[b] += 1


def threads_no_lock(rgb):
  """Race attempt with threads: += on a shared list without a lock."""
  hist = [0] * BINS
  _run_threads(_add_unlocked, rgb, hist)
  return np.array(hist, dtype=np.uint32)


def median_ms(method, rgb, runs):
  """Median wall-clock time of `runs` calls and the last histogram."""
  times = []
  for _ in range(runs):
    start = time.perf_counter()
    result = method(rgb)
    times.append((time.perf_counter() - start) * MS_PER_SECOND)
  return statistics.median(times), result
