"""PyInstaller runtime hook: stdout and stderr when the exe has no console.

With --windowed Windows does not give the process a console, so Python
starts with sys.stdout and sys.stderr = None and the first print() would
fail. The game logs to logs/fdc.log anyway; here the writes are simply
thrown away.
"""
import os
import sys

_DEVNULL = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

if sys.stdout is None:
    sys.stdout = _DEVNULL
if sys.stderr is None:
    sys.stderr = _DEVNULL
