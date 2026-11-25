"""Information about the machine, for the overlay, the CSV and the logs.

Nothing here imports PyCUDA or pygame at module level: the simulation and
the web client import this module too, and they must stay light. The GPU
name is asked only when it is really needed (and it is cheap to cache).
"""
import ctypes
import os
import platform
import socket

REMOTE_SESSION = 0x1000     # SM_REMOTESESSION of the Windows API
WINDOWS = "Windows"
UNKNOWN_CPU = "CPU desconocida"
NOT_WINDOWS = "no (o sin API)"


def host_name():
  """Name of the machine (the CSV tells two notebooks apart with it)."""
  try:
    return socket.gethostname()
  except OSError:
    return "desconocido"


def cpu_name():
  """Commercial name of the processor ('CPU desconocida' if unknown)."""
  if platform.system() == WINDOWS:
    name = _windows_cpu_name()
    if name:
      return name
  return platform.processor() or UNKNOWN_CPU


def _windows_cpu_name():
  """ProcessorNameString of the registry, or '' when it cannot be read."""
  try:
    import winreg            # pylint: disable=import-outside-toplevel
    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CPU_REGISTRY)
    value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
    return str(value).strip()
  except OSError:
    return ""


def is_remote_session():
  """True when Windows says this is a remote desktop session.

    The flag only affects the presentation (it is shown in the overlay and
    goes to the CSV): the CUDA work does not depend on the screen at all.
    """
  if platform.system() != WINDOWS:
    return False
  try:
    return bool(ctypes.windll.user32.GetSystemMetrics(REMOTE_SESSION))
  except (AttributeError, OSError):
    return False


def render_driver():
  """Value of SDL_RENDER_DRIVER, or 'auto' (for the overlay and the CSV)."""
  return os.environ.get("SDL_RENDER_DRIVER", "auto")


# The registry key with the commercial name of the processor.
_CPU_REGISTRY = (r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
