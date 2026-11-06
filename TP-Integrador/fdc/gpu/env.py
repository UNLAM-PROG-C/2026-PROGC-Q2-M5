"""Toolchain discovery for PyCUDA (nvcc + cl.exe in the PATH).

PyCUDA compiles the kernels with nvcc, and nvcc needs the MSVC compiler.
On this machine both are portable copies (see INSTALACION.md), so they are
not in the PATH by default: this module reads the MSVC `setup_x64.bat` and
adds the CUDA toolkit of the virtualenv, once per process.

The search order of the toolchain folder is:
  1. the FDC_GPU_TOOLCHAIN environment variable,
  2. a `toolchain` folder next to the repository.
"""
import os
import shutil
import subprocess
import sys

DONE_FLAG = "FDC_GPU_ENV"       # marker: the environment is already set
TOOLCHAIN_DIR = "toolchain"     # folder of the portable compilers
MAX_UP = 4                      # parent folders searched for the toolchain
SETUP_BAT = os.path.join("msvc", "setup_x64.bat")
CUDA_SITE = os.path.join("Lib", "site-packages", "nvidia", "cu13")
CUDA_BINS = ("bin", os.path.join("bin", "x64"), os.path.join("bin", "x86_64"))
COMMAND_TIMEOUT = 60            # s for the MSVC batch file


def repo_root():
    """Absolute path of the repository root (fdc/gpu/env.py -> up three)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def find_toolchain():
    """Folder that holds msvc/setup_x64.bat, or None.

    It looks in FDC_GPU_TOOLCHAIN and then in the parent folders of the
    repository (the checkout lives inside the project folder here).
    """
    folders = [os.environ.get("FDC_GPU_TOOLCHAIN")]
    folders += _ancestors(repo_root(), MAX_UP)
    for folder in folders:
        if folder and os.path.isfile(os.path.join(folder, SETUP_BAT)):
            return folder
    return None


def _ancestors(path, levels):
    """`path` and its parents, with a `toolchain` child each."""
    found = []
    for _ in range(levels):
        found.append(os.path.join(path, TOOLCHAIN_DIR))
        path = os.path.dirname(path)
    return found


def compilers_present():
    """True if nvcc and cl.exe are already reachable."""
    return bool(shutil.which("nvcc") and shutil.which("cl"))


def setup():
    """Puts nvcc and cl.exe in the PATH. True if they end up available."""
    if os.environ.get(DONE_FLAG) == "1":
        return True
    if compilers_present():
        os.environ[DONE_FLAG] = "1"
        return True
    toolchain = find_toolchain()
    if toolchain is None:
        return False
    _apply_msvc(os.path.join(toolchain, SETUP_BAT))
    _apply_cuda()
    os.environ[DONE_FLAG] = "1"
    return compilers_present()


def _apply_msvc(batch):
    """Exports what the batch file sets (it prints its environment)."""
    command = f'"{batch}" >nul && set'
    try:
        out = subprocess.run(command, shell=True, capture_output=True,
                             text=True, errors="replace",
                             timeout=COMMAND_TIMEOUT).stdout
    except (OSError, subprocess.SubprocessError):
        return
    for line in out.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = value


def _apply_cuda():
    """CUDA toolkit installed by pip inside the virtualenv."""
    cuda = os.path.join(sys.prefix, CUDA_SITE)
    if not os.path.isdir(cuda):
        return
    os.environ["CUDA_PATH"] = cuda
    paths = [os.path.join(cuda, part) for part in CUDA_BINS]
    os.environ["PATH"] = os.pathsep.join(paths + [os.environ.get("PATH", "")])
    lib = os.path.join(cuda, "lib", "x64")
    os.environ["LIB"] = os.pathsep.join([lib, os.environ.get("LIB", "")])
