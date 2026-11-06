"""Isolation of the simulation and the server (spec.md 15, requirement 11).

The online rooms and the simulation processes never draw nor use the GPU:
they must not import numpy, pygame, pycuda nor `fdc.gpu`. Two checks: the
imports written in the sources, and a fresh interpreter that imports them
and lists what ended up loaded.
"""
import ast
import json
import os
import subprocess
import sys
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(PROJECT, "tests", "check_sim_imports.py")
FOLDERS = (os.path.join(PROJECT, "fdc", "sim"),
           os.path.join(PROJECT, "fdc", "online"))
EXTRA = (os.path.join(PROJECT, "fdc", "ipc.py"),
         os.path.join(PROJECT, "fdc", "protocol.py"))
FORBIDDEN = ("numpy", "pygame", "pycuda", "fdc.gpu")
CHECK_TIMEOUT = 120     # s for the fresh interpreter


def _modules_imported(tree):
    """Top level names of every import of one module."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _forbidden(names):
    """The names of `names` that the simulation must not import."""
    return sorted(name for name in names
                  if name in FORBIDDEN or name.startswith("fdc.gpu"))


def _sources():
    """(relative path, tree) of every module of the two folders."""
    paths = list(EXTRA)
    for folder in FOLDERS:
        for base, _, files in os.walk(folder):
            paths += [os.path.join(base, name) for name in sorted(files)
                      if name.endswith(".py")]
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            yield os.path.relpath(path, PROJECT), ast.parse(fh.read())


class ImportIsolationTest(unittest.TestCase):
    """The simulation and the server stay free of drawing and GPU modules."""

    def test_source_imports_are_clean(self):
        problems = []
        for rel, tree in _sources():
            found = _forbidden(_modules_imported(tree))
            if found:
                problems.append(f"{rel}: {', '.join(found)}")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_a_fresh_interpreter_loads_none(self):
        env = dict(os.environ, SDL_VIDEODRIVER="dummy")
        out = subprocess.run([sys.executable, CHECK], cwd=PROJECT, env=env,
                             capture_output=True, text=True, check=True,
                             timeout=CHECK_TIMEOUT)
        data = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertTrue(data["imported"], "the check imported nothing")
        self.assertEqual(data["loaded"], [])


if __name__ == "__main__":
    unittest.main()
