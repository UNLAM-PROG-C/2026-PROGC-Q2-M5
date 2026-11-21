"""Timings of the effects chain and the CSV of the demo (F7).

`Metrics` keeps the milliseconds of each stage and of the whole frame; the
overlay of the game and the measurement script read from there.

`MeasurementLog` writes the CSV of the university demo: one row per segment
and backend, with the mean and the p95 of the work time and of the chain,
plus the mean of every stage (a JSON column). Every row is flushed, so a
demo cut with Ctrl+C keeps what it measured.
"""
import collections
import csv
import datetime
import json
import os

from fdc import config

STAGES = ("glow", "composite", "particles", "confetti", "lights", "heat",
          "histogram", "fire", "confusion", "confusion_rot",
          "ice", "blackout", "night", "exposure", "crt", "crowd")
PER_SECOND = 1000.0     # milliseconds in a second
DECIMALS = 3            # decimals of the stage times
FPS_DECIMALS = 1        # decimals of the frames per second
# --- F7: measurement log ------------------------------------------------
CSV_FOLDER = "mediciones"       # folder of the CSV (ignored by git)
CSV_PREFIX = "demo"             # name of the file
FRAMES_SUFFIX = "_frames"       # suffix of the per-frame CSV
STAMP = "%Y%m%d-%H%M%S"         # date format of the file name
FRAME_COLUMNS = ("t", "work_ms", "fx_ms")   # per-frame CSV
P95 = 95.0              # percentile of the tail
HUNDRED = 100.0         # percent (P95 is a percentage, not a fraction)
ROUND = 2               # decimals of the CSV numbers
WARMUP = config.Gpu.MEASURE_WARMUP   # frames dropped at the start
COLUMNS = ("timestamp", "host", "segment_index", "effect", "backend",
           "device", "resolution", "window", "remote_session", "quality",
           "block", "frames", "fps_real_mean", "fps_real_p5", "work_ms_mean",
           "work_ms_p95", "fx_ms_mean", "fx_ms_p95", "htod_ms", "dtoh_ms",
           "kernel_ms_json")


class Metrics:
  """Milliseconds per stage and per frame (a ring buffer each)."""

  def __init__(self, frames=None):
    size = frames or config.Gpu.METRICS_FRAMES
    self.size = size
    self.stage = {name: collections.deque(maxlen=size) for name in STAGES}
    self.frames = collections.deque(maxlen=size)
    self.skipped = 0       # frames the chain did not touch

  def add(self, name, milliseconds):
    """One sample of a stage (ignored if the stage is not known)."""
    if name in self.stage:
      self.stage[name].append(milliseconds)

  def frame(self, milliseconds):
    """One sample of the whole chain."""
    self.frames.append(milliseconds)

  def skip(self):
    """The chain did not run this frame (paused, menu...)."""
    self.skipped += 1

  def average(self, name):
    """Mean of a stage, 0 if it has no samples."""
    return _mean(self.stage.get(name, ()))

  def total(self):
    """Mean of the whole chain."""
    return _mean(self.frames)

  def fps(self):
    """Frames per second implied by the mean frame time."""
    total = self.total()
    return PER_SECOND / total if total > 0 else 0.0

  def clear(self):
    """Forgets the frames measured so far."""
    self.frames.clear()
    for values in self.stage.values():
      values.clear()

  def summary(self):
    """{stage: ms} plus 'frame', 'fps' and 'frames'."""
    data = {name: round(self.average(name), DECIMALS) for name in STAGES}
    data["frame"] = round(self.total(), DECIMALS)
    data["fps"] = round(self.fps(), FPS_DECIMALS)
    data["frames"] = len(self.frames)
    return data


def _mean(values):
  """Mean of an iterable of numbers (0 if empty)."""
  values = list(values)
  return sum(values) / len(values) if values else 0.0


def percentile(values, fraction=P95):
  """Nearest-rank percentile (the one `report_table` uses too)."""
  values = sorted(values)
  if not values:
    return 0.0
  index = int(round((len(values) - 1) * fraction / HUNDRED))
  return values[index]


class MeasurementLog:
  """CSV of the demo: one row per segment and backend.

    Between `begin_segment` and `end_segment` the screen calls `add_frame`
    once per frame. The first `WARMUP` frames of each segment are dropped
    (caches and shaders are still warming up), as the spec asks.
    """

  def __init__(self, path=None, fps=config.UI_FPS, frames_csv=False):
    self.path = path or self.default_path()
    self.frame_ms = PER_SECOND / fps
    self.frames_csv = (self.path[:-len(".csv")] + FRAMES_SUFFIX + ".csv"
                       if frames_csv and self.path.endswith(".csv")
                       else None)
    self.rows = []
    self.frames = []            # (t, work_ms, fx_ms) of the open segment
    self.open = None            # data of the segment being measured
    self._seen = 0
    self._ensure_folder()
    self._write_header()

  @staticmethod
  def default_path():
    """mediciones/demo_<date>_<host>.csv next to the repository (or in the
        user folder when the game runs packaged)."""
    stamp = datetime.datetime.now().strftime(STAMP)
    return os.path.join(config.MEASUREMENTS_DIR, CSV_FOLDER,
                        f"{CSV_PREFIX}_{stamp}_{_host()}.csv")

  def _ensure_folder(self):
    """Creates the folder of the CSV (it may not exist yet)."""
    folder = os.path.dirname(self.path)
    if folder:
      os.makedirs(folder, exist_ok=True)

  def _write_header(self):
    """Header of the main CSV (and of the per-frame one)."""
    with open(self.path, "w", newline="", encoding="utf-8") as fh:
      csv.writer(fh).writerow(COLUMNS)
    if self.frames_csv:
      with open(self.frames_csv, "w", newline="",
                encoding="utf-8") as fh:
        csv.writer(fh).writerow(FRAME_COLUMNS)

  def begin_segment(self, index, effect, backend, device, resolution,
                    window, remote, quality, block):
    """Opens the measurement of one segment of one backend."""
    self.open = {
        "index": index, "effect": effect, "backend": backend,
        "device": device, "resolution": resolution, "window": window,
        "remote": "sí" if remote else "no", "quality": quality,
        "block": block}
    self.frames = []
    self._seen = 0

  def add_frame(self, work_ms, fx_ms):
    """One frame of the open segment (the warm-up ones are ignored)."""
    if self.open is None:
      return
    self._seen += 1
    if self._seen <= WARMUP:
      return
    row = (len(self.frames) * self.frame_ms, work_ms, fx_ms)
    self.frames.append(row)
    self._write_frame(row)

  def end_segment(self, kernel_ms=None):
    """Closes the segment and appends its row to the CSV."""
    if self.open is None:
      return None
    row = self._row(kernel_ms or {})
    self.rows.append(row)
    self._append(row)
    self.open = None
    self.frames = []
    return row

  def _row(self, kernel_ms):
    """The row of the open segment, with every number rounded."""
    work = [item[1] for item in self.frames]
    fx = [item[2] for item in self.frames]
    data = dict(self.open)
    data.update(self._stats(work, fx))
    data["kernel_ms_json"] = json.dumps(
        {name: round(value, ROUND)
         for name, value in kernel_ms.items() if value}, sort_keys=True)
    return {name: data.get(name, "") for name in COLUMNS}

  def _stats(self, work, fx):
    """Means, p95 and fps of a segment (0 when it has no frames)."""
    return {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "host": _host(), "frames": len(self.frames),
        "fps_real_mean": _safe_div(PER_SECOND, _mean(work)),
        "fps_real_p5": _safe_div(PER_SECOND, percentile(work)),
        "work_ms_mean": round(_mean(work), ROUND),
        "work_ms_p95": round(percentile(work), ROUND),
        "fx_ms_mean": round(_mean(fx), ROUND),
        "fx_ms_p95": round(percentile(fx), ROUND),
        "htod_ms": 0.0, "dtoh_ms": 0.0}

  def _append(self, row):
    """One row, flushed: a cut demo keeps what it measured."""
    with open(self.path, "a", newline="", encoding="utf-8") as fh:
      writer = csv.DictWriter(fh, fieldnames=COLUMNS)
      writer.writerow(row)
      fh.flush()

  def _write_frame(self, frame):
    """One row of the per-frame CSV (only with --measure-frames)."""
    if not self.frames_csv:
      return
    with open(self.frames_csv, "a", newline="", encoding="utf-8") as fh:
      writer = csv.writer(fh)
      writer.writerow([round(value, ROUND) for value in frame])
      fh.flush()

  def close(self):
    """Closes the open segment (if any); returns the path."""
    if self.open is not None:
      self.end_segment()
    return self.path


def _safe_div(top, bottom):
  """Division that returns 0 instead of failing (no frames measured)."""
  return round(top / bottom, ROUND) if bottom else 0.0


def _host():
  """Name of the machine for the CSV (imported here: this module is light)."""
  from fdc.gpu import sysinfo      # pylint: disable=import-outside-toplevel
  return sysinfo.host_name()
