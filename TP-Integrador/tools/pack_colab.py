"""Package for Google Colab: sources, notebook and demo frames (< 10 MB).

Usage (PowerShell, from the repository):
    py tools\\pack_colab.py                 # colab_pack.zip
    py tools\\pack_colab.py --max-mb 8

The ZIP has the Python sources, the kernels, the tools, the notebook and the
frames (if `record_frames.py` was run). It does NOT include the virtual
environment, the measurements or the assets: the notebook only runs the
kernel benchmark, it does not draw the game.
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "colab_pack.zip")
NOTEBOOK = os.path.join(ROOT, "notebooks", "gpu_efectos_colab.ipynb")
FOLDERS = ("fdc", "tools", "notebooks")
FILES = ("main.py", "requirements-gpu.txt", "requirements.txt",
         "CATEDRA-GPU.md")
SKIP = ("__pycache__", ".pyc", "mediciones", ".venv", "frames")
FRAMES = os.path.join(ROOT, "frames")
MAX_MB = 9.5                      # MB that Colab accepts
MB = 1024 * 1024                 # bytes in a megabyte


def main(argv):
    """Writes the ZIP and checks its size."""
    limit = _max_mb(argv)
    if not os.path.exists(NOTEBOOK):
        print(f"falta {NOTEBOOK}")
        return 1
    sources = list(_sources())
    size = _write(sources)
    print(f"{OUT}: {size / MB:.1f} MB ({len(sources)} archivos)")
    if size > limit * MB:
        print(f"AVISO: supera los {limit} MB de Colab; sacá frames o tools")
        return 2
    return 0


def _write(sources):
    """Creates the ZIP with the given sources and returns its size."""
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as pack:
        for path in sources:
            pack.write(path, os.path.relpath(path, ROOT))
    return os.path.getsize(OUT)


def _sources():
    """Every file that goes into the pack."""
    for name in FILES:
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            yield path
    for path in _source_files():
        yield path
    for path in _frames():
        yield path


def _source_files():
    """Python, notebooks and kernels of the folders of the pack."""
    for folder in FOLDERS:
        for base, dirs, files in os.walk(os.path.join(ROOT, folder)):
            dirs[:] = [name for name in dirs if name not in SKIP]
            for name in sorted(files):
                if name.endswith((".py", ".ipynb", ".cu", ".txt", ".md")):
                    yield os.path.join(base, name)


def _frames():
    """PNGs of the demo (only if record_frames.py was run)."""
    if not os.path.isdir(FRAMES):
        return
    for name in sorted(os.listdir(FRAMES)):
        if name.endswith(".png"):
            yield os.path.join(FRAMES, name)


def _max_mb(argv):
    """`--max-mb N` (default 9.5, the limit of Colab's upload)."""
    if "--max-mb" in argv:
        index = argv.index("--max-mb")
        if index + 1 < len(argv):
            return float(argv[index + 1])
    return MAX_MB


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
