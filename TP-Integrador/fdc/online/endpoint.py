"""Address of the online server: --server, FDC_SERVER or servidor.txt.

The player or the installer can write it in three places. This module keeps
the order in one place, so the game and the tests agree:

  1. the --server option of the command line;
  2. the FDC_SERVER environment variable;
  3. the first useful line of servidor.txt, next to the exe (or next to
     main.py when the game runs from the sources);
  4. config.Online.SERVER_URL (ws://setcomnas.ddns.net:18765/ws by default).

Both ws:// (the local server) and wss:// (the same server behind a tunnel
with TLS) are accepted; a text without scheme is taken as ws://.
"""
import logging
import os
import sys
import urllib.parse

from fdc import config

log = logging.getLogger("fdc.endpoint")
ONLINE = config.Online
FILE_NAME = "servidor.txt"     # read next to the exe (see file_path)
ENV_NAME = "FDC_SERVER"        # the variable config.Online also reads
SCHEMES = ("ws", "wss")        # plain WebSocket and WebSocket over TLS
SCHEME_SEP = "://"             # between the scheme and the host
COMMENT = "#"                  # a servidor.txt line that starts like this
LOCAL_SCHEME = "ws"            # assumed when the text has no scheme


def base_dir():
  """Folder of the exe, or of the project when running from sources."""
  if getattr(sys, "frozen", False):
    return os.path.dirname(os.path.abspath(sys.executable))
  return config.ROOT_DIR


def file_path(folder=None):
  """Path of servidor.txt in `folder` (the base folder by default)."""
  return os.path.join(folder or base_dir(), FILE_NAME)


def read_file(folder=None):
  """First useful line of servidor.txt, or None if there is no file."""
  try:
    with open(file_path(folder), encoding="utf-8") as handle:
      return _first_line(handle.read())
  except OSError:
    return None


def _first_line(text):
  """First line that is not empty and does not start with '#'."""
  for line in text.splitlines():
    line = line.strip()
    if line and not line.startswith(COMMENT):
      return line
  return None


def with_scheme(text):
  """The address as written, or with ws:// in front of it."""
  if SCHEME_SEP in text:
    return text
  return LOCAL_SCHEME + SCHEME_SEP + text


def validate(text):
  """The usable URL, or ValueError if the scheme or the host is wrong."""
  url = with_scheme(text)
  parts = urllib.parse.urlsplit(url)
  if parts.scheme in SCHEMES and parts.netloc:
    return url
  raise ValueError(
      f"dirección del servidor inválida: {text!r} "
      "(se espera ws://host:puerto/ws o wss://dominio/ws)")


def _usable(text):
  """The checked address, or None (with a warning in the log)."""
  if not text or not text.strip():
    return None
  try:
    return validate(text.strip())
  except ValueError as error:
    log.warning("%s", error)
    return None


def resolve_url(cli_url=None, environ=None, folder=None):
  """Server address, in the order described in the module docstring."""
  environ = os.environ if environ is None else environ
  for text in (cli_url, environ.get(ENV_NAME), read_file(folder)):
    url = _usable(text)
    if url:
      return url
  return ONLINE.SERVER_URL
