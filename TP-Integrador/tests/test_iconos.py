"""Art of the icon: one raster per size, never a 1024 shrunken into place.

The set is versioned (assets/icono), so these tests read the
files with the standard library: a PNG header and the directory of an ICO
are enough to catch a logo drawn at its native size inside a small canvas
(the 16 and 32 px rasters would come out identical) and a missing derivative.
"""
import os
import struct
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONO = os.path.join(ROOT, "assets", "icono")
ICONSET = os.path.join(ICONO, "mac", "FutbolDeCabeza.iconset")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICONSET_FILES = {
    "icon_16x16.png": 16, "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32, "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128, "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256, "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512, "icon_512x512@2x.png": 1024,
}


def png_size(data):
  """Width and height of a PNG, from its IHDR chunk."""
  if data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
    raise ValueError("not a PNG")
  return struct.unpack(">II", data[16:24])


def png_size_of(path):
  """Width and height of a PNG file."""
  with open(path, "rb") as handle:
    return png_size(handle.read(33))


def ico_entries(data):
  """(width, height, payload) of every image of an ICO."""
  count = struct.unpack("<H", data[4:6])[0]
  entries = []
  for index in range(count):
    start = 6 + index * 16
    width, height, _, _, _, _, length, offset = struct.unpack(
        "<BBBBHHII", data[start:start + 16])
    entries.append((width or 256, height or 256,
                    data[offset:offset + length]))
  return entries


class IcoTest(unittest.TestCase):
  """Windows icon: seven rasters, each drawn at its own size."""

  @classmethod
  def setUpClass(cls):
    with open(os.path.join(ICONO, "icono.ico"), "rb") as handle:
      cls.entries = ico_entries(handle.read())

  def test_has_every_size(self):
    sizes = sorted(width for width, _, _ in self.entries)
    self.assertEqual(sizes, sorted(ICO_SIZES))

  def test_every_entry_is_a_png_of_its_size(self):
    for width, height, payload in self.entries:
      self.assertEqual(png_size(payload), (width, height))

  def test_small_sizes_are_not_the_same_raster(self):
    payloads = {width: payload for width, _, payload in self.entries}
    self.assertNotEqual(payloads[16], payloads[32])
    self.assertNotEqual(payloads[32], payloads[48])
    self.assertNotEqual(payloads[64], payloads[256])


class PngTest(unittest.TestCase):
  """The PNGs Python uses, and the macOS iconset."""

  def test_master_and_window_logo(self):
    self.assertEqual(png_size_of(os.path.join(ICONO, "logo-1024.png")),
                     (1024, 1024))
    self.assertEqual(png_size_of(os.path.join(ICONO, "logo.png")),
                     (32, 32))

  def test_iconset_has_the_ten_files_of_macos(self):
    for name, size in ICONSET_FILES.items():
      path = os.path.join(ICONSET, name)
      self.assertTrue(os.path.isfile(path), name)
      self.assertEqual(png_size_of(path), (size, size), name)



if __name__ == "__main__":
  unittest.main()
