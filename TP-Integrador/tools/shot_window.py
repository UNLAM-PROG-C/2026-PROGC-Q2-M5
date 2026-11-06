"""Screenshot (and close) the window of the game, from Windows.

Usage (PowerShell, from the repository, with the venv):
    .venv\\Scripts\\python.exe tools\\shot_window.py captura.png
    .venv\\Scripts\\python.exe tools\\shot_window.py --close

It looks for the window titled "Futbol De Cabeza" (main.py or the exe),
copies its pixels and saves a PNG. `--close` asks the window to close, the
same as the X button. It is the tool used for the captures of the exe: the
demo runs in its own window and the picture is taken from outside.
"""
import argparse
import os
import sys

import pygame
import win32con
import win32gui
import win32ui

GAME_TITLE = "Futbol De Cabeza"   # pygame.display.set_caption (fdc/config.py)
SRCCOPY = win32con.SRCCOPY        # copy the pixels of the window
BYTES_PER_PIXEL = 4               # 32 bits per pixel (BGRA)
WAIT_MS = 200                     # ms after asking the window to close
FOCUS_MS = 400                    # ms after bringing the window to the front


def parse_args(argv=None):
    """A picture to take or --close."""
    parser = argparse.ArgumentParser(description="Window of the game.")
    parser.add_argument("picture", nargs="?", help="PNG to write")
    parser.add_argument("--close", action="store_true",
                        help="ask the window to close (like the X)")
    return parser.parse_args(argv)


def find_window():
    """Handle of the game window, or SystemExit with a clear message."""
    hwnd = win32gui.FindWindow(None, GAME_TITLE)
    if not hwnd:
        raise SystemExit(f'no encontré la ventana "{GAME_TITLE}"')
    return hwnd


def close(hwnd):
    """The same as clicking the X: the game saves and quits."""
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    win32gui.PumpWaitingMessages()
    pygame.time.wait(WAIT_MS)


def _copy(source, width, height):
    """Copy of the source DC as a bitmap (BitBlt)."""
    save = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(source, width, height)
    save.SelectObject(bitmap)
    save.BitBlt((0, 0), (width, height), source, (0, 0), SRCCOPY)
    return bitmap


def _window_bitmap(hwnd):
    """Bitmap with the pixels of the window (GetBitmapBits works on it)."""
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise SystemExit("la ventana del juego no tiene tamaño")
    window_dc = win32gui.GetWindowDC(hwnd)
    source = win32ui.CreateDCFromHandle(window_dc)
    bitmap = _copy(source, width, height)
    win32gui.ReleaseDC(hwnd, window_dc)
    return bitmap


def _focus(hwnd):
    """Brings the window to the front (the game pauses without focus)."""
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:      # pylint: disable=broad-exception-caught
        pass               # Windows may refuse: the picture is taken anyway
    pygame.time.wait(FOCUS_MS)


def capture(hwnd, path):
    """Saves the window content as PNG and returns the path."""
    _focus(hwnd)
    bitmap = _window_bitmap(hwnd)
    info = bitmap.GetInfo()
    pixels = bitmap.GetBitmapBits(True)
    size = (info["bmWidth"], info["bmHeight"])
    surface = pygame.image.frombuffer(pixels, size, "BGRA")
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    pygame.image.save(surface, path)
    return path


def main(argv=None):
    """Takes the picture or closes the window."""
    options = parse_args(argv)
    hwnd = find_window()
    if options.close:
        close(hwnd)
        print("ventana cerrada")
        return 0
    if not options.picture:
        raise SystemExit("falta el PNG a escribir (o --close)")
    print("captura: " + capture(hwnd, options.picture))
    return 0


if __name__ == "__main__":
    sys.exit(main())
