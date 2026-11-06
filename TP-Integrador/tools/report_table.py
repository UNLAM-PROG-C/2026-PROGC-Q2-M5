"""Table of the measurements: GPU against numpy, one row per effect.

It reads the CSV of --demo (or of bench_gpu.py) and groups by effect and
backend: mean FPS, mean work time, mean chain time and the speedup of the
GPU against numpy. It writes a Markdown table next to the sources and
prints it. Commands: `py tools\\report_table.py` (see the README).
"""
import csv
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "mediciones")
PATTERN = "*.csv"
SKIP_SUFFIX = "_frames"
COLUMNS = ("efecto", "backend", "frames", "fps", "work_ms", "fx_ms")
TABLE_PREFIX = "tabla"


def read(path):
    """Rows of one CSV (empty when the file is not a measurement)."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [row for row in rows if row.get("effect")]


def sources(argv):
    """Files to read: the ones of the command line or every demo CSV."""
    files = [arg for arg in argv if arg.endswith(".csv")]
    if files:
        return files
    return sorted(name for name in glob.glob(os.path.join(FOLDER, PATTERN))
                  if not name.endswith(SKIP_SUFFIX + ".csv"))


def group(rows):
    """{(effect, backend): [rows]} (the same effect may repeat)."""
    groups = {}
    for row in rows:
        key = (row["effect"], row.get("backend") or "?")
        groups.setdefault(key, []).append(row)
    return groups


def mean(rows, column):
    """Mean of one numeric column (0 when there is nothing)."""
    values = [_number(row.get(column)) for row in rows]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else 0.0


def _number(value):
    """Float or None (the CSV may have empty cells)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def table(rows):
    """[(effect, backend, frames, fps, work, fx, speedup)] ordered by effect."""
    groups = group(rows)
    effects = sorted({key[0] for key in groups})
    out = []
    for effect in effects:
        gpu = groups.get((effect, "gpu"))
        cpu = groups.get((effect, "cpu"))
        base = gpu or cpu or []
        out.append((effect, "gpu" if gpu else "cpu", int(mean(base, "frames")),
                    mean(base, "fps_real_mean"), mean(base, "work_ms_mean"),
                    mean(base, "fx_ms_mean"),
                    _speedup(gpu, cpu)))
    return out


def _speedup(gpu, cpu):
    """numpy ms / GPU ms of the chain (only when both ran)."""
    if not gpu or not cpu:
        return 0.0
    fast = mean(gpu, "fx_ms_mean")
    return mean(cpu, "fx_ms_mean") / fast if fast else 0.0


def markdown(rows):
    """Markdown table ready to paste into NOTAS or the README."""
    lines = ["| efecto | backend | frames | FPS | work ms | fx ms | x |",
             "|---|---|---|---|---|---|---|"]
    for effect, back, frames, fps, work, fx, speed in table(rows):
        lines.append(f"| {effect} | {back} | {frames} | {fps:.1f} | "
                     f"{work:.2f} | {fx:.2f} | "
                     f"{speed:.1f} |" if speed else
                     f"| {effect} | {back} | {frames} | {fps:.1f} | "
                     f"{work:.2f} | {fx:.2f} | - |")
    return "\n".join(lines)


def output_path(argv):
    """`--out` value or mediciones/tabla_<first source>.md."""
    if "--out" in argv:
        index = argv.index("--out")
        if index + 1 < len(argv):
            return argv[index + 1]
    return os.path.join(FOLDER, TABLE_PREFIX + ".md")


def main(argv):
    """Reads the CSVs, prints the table and writes it."""
    os.makedirs(FOLDER, exist_ok=True)
    files = sources(argv)
    rows = _load(files)
    if not rows:
        return 1
    text = markdown(rows)
    print(text)
    path = output_path(argv)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"\nTabla escrita en {path} ({len(files)} archivo(s))")
    return 0


def _load(files):
    """Rows of every source; explains why when there is nothing."""
    if not files:
        print("No hay mediciones: corré primero tools\\run_demo.py")
        return []
    rows = []
    for path in files:
        rows.extend(read(path))
    if not rows:
        print("Los CSV no tienen filas de medición.")
    return rows


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
