"""Imports the simulation and the server alone and lists heavy modules.

Run by tests/test_gpu_isolation.py in a fresh interpreter: the server and
`fdc/sim` must not drag numpy, pygame, pycuda or the effects package into
their processes (spec.md section 15, requirement 11).
"""
import importlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)

FORBIDDEN = ("numpy", "pygame", "pycuda", "fdc.gpu")
MODULES = ("fdc.protocol", "fdc.ipc", "fdc.sim.core", "fdc.sim.match",
           "fdc.sim.powers", "fdc.sim.process",
           "fdc.online.lobby", "fdc.online.server", "fdc.online.room_runner",
           "fdc.online.wire")


def main():
  """Imports the modules and prints the forbidden ones that came along."""
  for name in MODULES:
    importlib.import_module(name)
  loaded = sorted(name for name in sys.modules
                  if name.split(".")[0] in FORBIDDEN
                  or name.startswith("fdc.gpu"))
  print(json.dumps({"loaded": loaded, "imported": list(MODULES)}))
  return 0


if __name__ == "__main__":
  sys.exit(main())
