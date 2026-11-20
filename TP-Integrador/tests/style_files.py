"""Shared, deterministic source inventory for the course style checks."""
import os

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = ("fdc", "tools", "tests")
ROOT_SCRIPTS = ("main.py", "server.py")


def project_files(include_tests=True):
  """Yield only the agreed scope; landing, assets and web are excluded."""
  for name in ROOT_SCRIPTS:
    yield os.path.join(PROJECT, name)
  for folder in FOLDERS:
    if folder != "tests" or include_tests:
      yield from _folder_files(folder)


def _folder_files(folder):
  for base, directories, files in os.walk(os.path.join(PROJECT, folder)):
    directories.sort()
    for name in sorted(files):
      if name.endswith(".py"):
        yield os.path.join(base, name)


def sources(include_tests=True):
  for path in project_files(include_tests):
    with open(path, encoding="utf-8") as stream:
      yield os.path.relpath(path, PROJECT), stream.read()
