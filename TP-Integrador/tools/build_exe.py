"""Builds the Windows exe of the game with PyInstaller (one command).

Usage (PowerShell; see tools/requirements/requirements-build.txt):
    .venv\\Scripts\\python.exe tools\\build_exe.py               # CPU
    .venv\\Scripts\\python.exe tools\\build_exe.py --mode full   # CPU + GPU
    .venv\\Scripts\\python.exe tools\\build_exe.py --console     # to read the
                                                               # errors

It leaves dist\\futbol-cpu\\ with futbol-cpu.exe (no Python needed), the
assets, jugar-cpu.bat and servidor.txt.example. That folder can be copied to
another Windows computer as it is.

A new build variant is one more entry in MODES: name suffix, extra data
files, hidden imports and excluded modules.
"""
import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
WORK = os.path.join(ROOT, "build", "pyinstaller")
ENTRY = os.path.join(ROOT, "main.py")
RUNTIME_HOOK = os.path.join(TOOLS, "pyi_rth_stdout.py")
SERVER_EXAMPLE = os.path.join(TOOLS, "servidor.txt.example")
# Icon of the .exe and of the window (the same logo of the .app and the web).
ICON = os.path.join(ROOT, "assets", "icono", "icono.ico")
SERVER_FILE = "servidor.txt"     # next to the exe (see fdc/online/endpoint.py)
PACKAGE = "futbol"               # dist/futbol-<mode>/futbol-<mode>.exe
EXE_SUFFIX = ".exe"
LAUNCHER_NAME = "jugar-cpu.bat"  # double click, next to the exe (per mode)
MEGABYTE = 1024 * 1024           # bytes, to show the size like the Explorer
# Files the game reads from disk at run time (PyInstaller only packs the .py).
EXTRA_DATA = (("fdc/online/panel.html", "fdc/online"),)
# Design material that must not ship inside the bundles.
ASSETS_SKIP = (os.path.join("icono", "propuestas"),
               os.path.join("icono", "mac"))
# The CUDA source of the kernels: only the modes with effects in the GPU.
CUDA_DATA = (("fdc/gpu/kernels.cu", "fdc/gpu"),
             ("fdc/gpu/kernels_config.cuh", "fdc/gpu"),
             ("fdc/gpu/kernels.fatbin", "fdc/gpu"),
             ("fdc/gpu/kernels.sha256", "fdc/gpu"))
# DLLs that pycuda._driver imports: they must sit next to the exe (the pip
# nvidia package keeps them in a subfolder the loader does not search).
CUDA_DLLS = (os.path.join("nvidia", "cu13", "bin", "x86_64",
                         "curand64_10.dll"),)
MODES = {
    "cpu": {
        "suffix": "cpu",
        "data": (),
        "hidden": (),
        "exclude": ("pycuda", "OpenGL", "tkinter"),
        "launcher": "jugar-cpu.bat",
    },
    "full": {
        "suffix": "full",
        "data": CUDA_DATA,
        "hidden": ("pycuda.driver", "pycuda.autoinit", "pycuda.compiler"),
        "binaries": CUDA_DLLS,
        "exclude": ("tkinter",),
        "launcher": "jugar-gpu.bat",
    },
}
LAUNCHER = """@echo off
rem Futbol de Cabeza: doble clic para jugar (no hace falta Python).
rem El servidor online, si hace falta, va en servidor.txt.
start "" "%~dp0{exe}" %*
"""


def parse_args(argv=None):
  """Options of the build script."""
  parser = argparse.ArgumentParser(
      description="Builds the Windows exe of Futbol de Cabeza.")
  parser.add_argument("--mode", choices=tuple(MODES), default="cpu",
                      help="cpu: effects in numpy; full: also the GPU")
  parser.add_argument("--name", default=None,
                      help="folder and exe name (default futbol-<mode>)")
  parser.add_argument("--console", action="store_true",
                      help="keep the console window (to read the errors)")
  parser.add_argument("--dist", default=DIST,
                      help="output folder of PyInstaller (default dist)")
  return parser.parse_args(argv)


def output_name(options):
  """Name of the folder and of the exe: futbol-cpu, futbol-full..."""
  return options.name or f"{PACKAGE}-{MODES[options.mode]['suffix']}"


def pyinstaller_args(options):
  """The whole PyInstaller command line for this mode."""
  mode = MODES[options.mode]
  args = [ENTRY, "--onedir", "--noconfirm", "--clean",
          "--name", output_name(options),
          "--distpath", options.dist, "--workpath", WORK,
          "--specpath", WORK]
  if os.path.exists(ICON):
    args += ["--icon", ICON]
  args += _window_args(options)
  _add_data(args, tuple(asset_pairs()) + EXTRA_DATA + mode["data"])
  _add_binaries(args, mode.get("binaries", ()))
  _add_modules(args, "--hidden-import", mode["hidden"])
  _add_modules(args, "--exclude-module", mode["exclude"])
  return args


def asset_pairs():
  """(source, target) for every file of assets/ except ASSETS_SKIP."""
  pairs = []
  base = os.path.join(ROOT, "assets")
  for folder, _, names in os.walk(base):
    rel = os.path.relpath(folder, base)
    if any(rel == skip or rel.startswith(skip + os.sep)
           for skip in ASSETS_SKIP):
      continue
    for name in names:
      source = os.path.relpath(os.path.join(folder, name), ROOT)
      target = os.path.normpath(os.path.join("assets", rel))
      pairs.append((source, target))
  return pairs


def _window_args(options):
  """Only the game window, or the console too (--console)."""
  if options.console:
    return ["--console"]
  return ["--windowed", "--runtime-hook", RUNTIME_HOOK]


def _add_data(args, pairs):
  """--add-data source<sep>destination for each pair (sources from ROOT)."""
  for source, target in pairs:
    path = os.path.join(ROOT, source)
    args.extend(["--add-data", os.pathsep.join((path, target))])


def _add_binaries(args, names):
  """--add-binary for each DLL of the virtualenv (to the exe folder)."""
  for name in names:
    path = os.path.join(sys.prefix, "Lib", "site-packages", name)
    args.extend(["--add-binary", os.pathsep.join((path, "."))])


def _add_modules(args, flag, names):
  """--hidden-import or --exclude-module for each module name."""
  for name in names:
    args.extend([flag, name])


def main(argv=None):
  """Runs PyInstaller and leaves the launcher next to the exe."""
  options = parse_args(argv)
  name = output_name(options)
  args = pyinstaller_args(options)
  if options.mode == "full":
    _rebuild_kernels()
  _run_pyinstaller(args)
  folder = os.path.join(options.dist, name)
  _extras(folder, name, MODES[options.mode]["launcher"])
  _report(folder, name, MODES[options.mode]["launcher"])
  return 0


def _run_pyinstaller(args):
  """Prints the command line and runs PyInstaller with it."""
  print("pyinstaller " + " ".join(args))
  # Imported here: the script still says what it does without the package.
  # pylint: disable-next=import-outside-toplevel
  import PyInstaller.__main__
  PyInstaller.__main__.run(args)


def _rebuild_kernels():
  """Recompiles kernels.fatbin from kernels.cu and checks every name.

    A stale or hand-made fatbin must never reach a GPU zip.
    """
  sys.path.insert(0, TOOLS)
  # pylint: disable-next=import-outside-toplevel,import-error
  import build_kernels
  build_kernels.build()


def _extras(folder, name, launcher):
  """Launcher and servidor.txt next to the exe."""
  if not os.path.isdir(folder):
    raise SystemExit(f"PyInstaller did not create {folder}")
  _write_launcher(os.path.join(folder, launcher), name + EXE_SUFFIX)
  _write_server_file(folder)
  _drop_duplicate_cuda(folder)


def _drop_duplicate_cuda(folder):
  """PyInstaller also copies the pip nvidia tree (100 MB twice): remove."""
  shutil.rmtree(os.path.join(folder, "_internal", "nvidia"),
                ignore_errors=True)


def _write_server_file(folder):
  """servidor.txt with the default server (never over the player's)."""
  path = os.path.join(folder, SERVER_FILE)
  if not os.path.exists(path):
    shutil.copy(SERVER_EXAMPLE, path)


def _write_launcher(path, exe):
  """jugar-*.bat that starts that exe (it works from any folder)."""
  with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
    handle.write(LAUNCHER.format(exe=exe))


def folder_size(folder):
  """Bytes of every file of the folder (recursive)."""
  total = 0
  for base, _, names in os.walk(folder):
    for name in names:
      total += os.path.getsize(os.path.join(base, name))
  return total


def _report(folder, name, launcher):
  """Prints where the game is, how big it is and how to try it."""
  size = folder_size(folder) / MEGABYTE
  print(f"\nlisto: {folder}  ({size:.1f} MB)")
  print(f'probar: "{os.path.join(folder, name + EXE_SUFFIX)}" --backend cpu')
  print(f'        "{os.path.join(folder, launcher)}"')


if __name__ == "__main__":
  raise SystemExit(main())
