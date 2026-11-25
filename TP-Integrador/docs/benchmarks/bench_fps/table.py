"""Markdown table from the bench_fps.py JSON files (same folder)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROWS = ("sin efecto", "Hielo", "Fuego", "Repetición", "Confusión", "Apagón",
        "Noche")
COLUMNS = ("pc-gpu-full", "pc-cpu-full", "notebook-cpu-full")


def load(name):
  path = HERE / f"{name}.json"
  return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"rows": {}}


def cell(row):
  if not row:
    return "sin dato"
  return f"{row['fps_avg']} ({row['fps_p1']} / {row['fps_min']})"


def main():
  data = {name: load(name) for name in COLUMNS}
  print("| Efecto | PC GPU FULL | PC CPU FULL | GPU/CPU | Notebook CPU FULL |"
        " active | seen (GPU / CPU) |")
  print("|---|---|---|---|---|---|---|")
  for label in ROWS:
    g, c, n = (data[name]["rows"].get(label) for name in COLUMNS)
    ratio = f"{g['fps_avg'] / c['fps_avg']:.1f}x" if g and c else "sin dato"
    active = "/".join(str(r.get("active_share", "-")) for r in (g, c, n) if r)
    seen = " / ".join(",".join(r.get("seen", [])) for r in (g, c) if r)
    print(f"| {label} | {cell(g)} | {cell(c)} | {ratio} | {cell(n)} |"
          f" {active} | {seen} |")
  for name in ("pc-cpu-sin-efectos", "notebook-cpu-sin-efectos"):
    print(f"| {name} | {cell(load(name)['rows'].get('sin efecto'))} | | | | | |")
  print("window:", {n: load(n).get("window") for n in COLUMNS})


if __name__ == "__main__":
  main()
