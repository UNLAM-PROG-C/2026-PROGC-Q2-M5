"""Folders the game writes when it runs packaged (logs and demo CSV).

A .app inside /Applications or a .exe inside Program Files may be read only:
the log and the measurement CSV have to leave the bundle and go to the user
folder of each system, created on demand and with a silent fallback.
"""
import os
import tempfile
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import
from fdc import config
from fdc.gpu import metrics

HOME = "/home/ana"                     # fake home of the tests
LOCAL = "/win/AppData/Local"           # fake %LOCALAPPDATA%
NONE = {}                              # empty environment


class SourceTreeTest(unittest.TestCase):
    """Running from the sources nothing moves: the repository is writable."""

    def test_logs_stay_in_the_repository(self):
        folder = config.log_dir(platform="win32", home=HOME, frozen=False)
        self.assertEqual(folder, os.path.join(config.ROOT_DIR, "logs"))

    def test_measurements_stay_in_the_repository(self):
        folder = config.data_dir(platform="darwin", home=HOME, frozen=False)
        self.assertEqual(folder, config.ROOT_DIR)


class WindowsTest(unittest.TestCase):
    """Windows: %LOCALAPPDATA%\\FutbolDeCabeza."""

    def test_logs(self):
        folder = config.log_dir(platform="win32", environ={"LOCALAPPDATA":
                                                           LOCAL},
                                home=HOME, frozen=True)
        self.assertEqual(folder, os.path.join(LOCAL, "FutbolDeCabeza",
                                              "logs"))

    def test_data(self):
        folder = config.data_dir(platform="win32", environ={"LOCALAPPDATA":
                                                            LOCAL},
                                 home=HOME, frozen=True)
        self.assertEqual(folder, os.path.join(LOCAL, "FutbolDeCabeza"))

    def test_without_localappdata(self):
        folder = config.log_dir(platform="win32", environ=NONE, home=HOME,
                                frozen=True)
        self.assertEqual(folder, os.path.join(HOME, "AppData", "Local",
                                              "FutbolDeCabeza", "logs"))


class MacTest(unittest.TestCase):
    """macOS: ~/Library/Logs/FutbolDeCabeza (the .app is a read-only bundle)."""

    def test_logs(self):
        folder = config.log_dir(platform="darwin", environ=NONE, home=HOME,
                                frozen=True)
        self.assertEqual(folder, os.path.join(HOME, "Library", "Logs",
                                              "FutbolDeCabeza"))

    def test_data(self):
        folder = config.data_dir(platform="darwin", environ=NONE, home=HOME,
                                 frozen=True)
        self.assertEqual(folder, os.path.join(HOME, "Library",
                                              "Application Support",
                                              "FutbolDeCabeza"))


class LinuxTest(unittest.TestCase):
    """Linux: the XDG folders of the user."""

    def test_logs_use_xdg_state(self):
        folder = config.log_dir(platform="linux",
                                environ={"XDG_STATE_HOME": "/estado"},
                                home=HOME, frozen=True)
        self.assertEqual(folder, os.path.join("/estado", "FutbolDeCabeza",
                                              "logs"))

    def test_data_falls_back_to_the_home(self):
        folder = config.data_dir(platform="linux", environ=NONE, home=HOME,
                                 frozen=True)
        self.assertEqual(folder, os.path.join(HOME, ".local", "share",
                                              "FutbolDeCabeza"))


class EnsureTest(unittest.TestCase):
    """The folder is created; if it cannot, the fallback wins (silently)."""

    def test_creates_the_folder(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "a", "b")
            self.assertEqual(config._ensure(path, root), path)
            self.assertTrue(os.path.isdir(path))

    def test_falls_back_when_it_cannot(self):
        with tempfile.TemporaryDirectory() as root:
            blocker = os.path.join(root, "archivo")
            with open(blocker, "w", encoding="utf-8") as handle:
                handle.write("x")
            path = os.path.join(blocker, "logs")
            self.assertEqual(config._ensure(path, root), root)


class MeasurementsTest(unittest.TestCase):
    """The CSV of the demo lives in <data dir>/mediciones."""

    def test_default_path(self):
        path = metrics.MeasurementLog.default_path()
        folder = os.path.join(config.MEDICIONES_DIR, metrics.CSV_FOLDER)
        self.assertEqual(os.path.dirname(path), folder)
        self.assertTrue(os.path.basename(path).endswith(".csv"))


if __name__ == "__main__":
    unittest.main()
