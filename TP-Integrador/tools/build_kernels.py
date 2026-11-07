"""Compiles fdc/gpu/kernels.cu into fdc/gpu/kernels.fatbin (one fatbin).

Why: PyCUDA's SourceModule needs nvcc and the MSVC compiler on the PC that
runs the game. A player has neither, so the GPU zip ships the kernels
already compiled and loads them with `module_from_file` (the driver only).

The fatbin holds real machine code (SASS) for the NVIDIA generations that
nvcc 13 still supports plus PTX for the newest one, so a GPU newer than all
of them still works: the driver compiles that PTX when the game starts.

Run it on the dev PC (it needs nvcc and cl.exe, see INSTALACION.md) every
time kernels.cu changes:

    py tools/build_kernels.py

It also writes kernels.sha256; the game only trusts the fatbin when that
hash matches the current kernels.cu, so a stale fatbin is never loaded.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from fdc.gpu import backend  # noqa: E402  pylint: disable=wrong-import-position
from fdc.gpu import env      # noqa: E402  pylint: disable=wrong-import-position

# Real code for these architectures (Turing .. Blackwell).
SASS_ARCHS = ("75", "80", "86", "89", "90", "100", "120")
PTX_ARCH = "120"            # PTX for anything newer than the list above
TIMEOUT = 600               # s for nvcc


def nvcc_command(source, output):
    """The nvcc command line: one -gencode per architecture."""
    command = ["nvcc", "--fatbin", *backend.COMPILER_OPTIONS]
    for arch in SASS_ARCHS:
        command += ["-gencode", f"arch=compute_{arch},code=sm_{arch}"]
    command += ["-gencode", f"arch=compute_{PTX_ARCH},code=compute_{PTX_ARCH}"]
    return command + ["-o", output, source]


def compile_c_linkage(output):
    """nvcc on the source wrapped in extern "C" (plain kernel names)."""
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, backend.KERNEL_FILE)
        with open(source, "w", encoding="utf-8") as fh:
            fh.write(backend.c_linkage_source())
        subprocess.run(nvcc_command(source, output), check=True,
                       timeout=TIMEOUT)


def verify(path):
    """Loads the fatbin and asks the driver for every kernel by name."""
    # pylint: disable=import-outside-toplevel,unused-import
    import pycuda.autoinit  # noqa: F401
    import pycuda.driver as drv
    module = drv.module_from_file(path)
    missing = []
    for name in backend.kernel_names():
        try:
            module.get_function(name)
        except drv.LogicError:
            missing.append(name)
    if missing:
        raise SystemExit(f"kernels missing in {path}: {missing}")


def build():
    """Compiles the kernels and saves the hash of the source; returns paths."""
    if not env.setup():
        raise SystemExit("nvcc / cl.exe not found (see INSTALACION.md)")
    folder = os.path.dirname(backend.kernel_path())
    output = os.path.join(folder, backend.FATBIN_FILE)
    compile_c_linkage(output)
    verify(output)
    with open(os.path.join(folder, backend.HASH_FILE), "w",
              encoding="ascii") as fh:
        fh.write(backend.source_hash() + "\n")
    return output


def main():
    """Entry point."""
    output = build()
    print(f"{output}: {os.path.getsize(output)} bytes")


if __name__ == "__main__":
    main()
