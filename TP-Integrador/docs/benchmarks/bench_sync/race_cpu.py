"""Race without the GIL: processes share one histogram and use += unlocked.

Separate processes run truly in parallel, so `shared[b] += 1` (read, add,
write) loses updates when two processes touch the same bin at once.
"""
import multiprocessing

import numpy as np

from frames import BINS, luma_bins

PROCESSES = 4  # parallel workers, each one with its own interpreter


def _add_unlocked(chunk, shared, barrier):
  bins = luma_bins(chunk).tolist()
  barrier.wait()  # start together so the increments really overlap
  for b in bins:
    shared[b] += 1


def processes_no_lock(rgb):
  """Shared memory (multiprocessing.Array without lock) and plain +=."""
  shared = multiprocessing.Array('I', BINS, lock=False)
  barrier = multiprocessing.Barrier(PROCESSES)
  workers = [multiprocessing.Process(target=_add_unlocked,
                                     args=(chunk, shared, barrier))
             for chunk in np.array_split(rgb, PROCESSES, axis=0)]
  for worker in workers:
    worker.start()
  for worker in workers:
    worker.join()
  return np.frombuffer(shared, dtype=np.uint32).copy()
