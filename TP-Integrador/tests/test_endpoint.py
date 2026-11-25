"""D1: where the game finds the online server (fdc/online/endpoint.py).

The order is --server, FDC_SERVER, servidor.txt and the default. The last
test writes servidor.txt and connects the real client to a real server, as
the installer will do next to the exe.
"""
import os
import tempfile
import time
import unittest
import unittest.mock

try:
  import websockets  # pylint: disable=unused-import
except ImportError:  # the local game does not need it: skipped without it
  raise unittest.SkipTest(
      "websockets is missing (pip install -r "
      "tools/requirements/requirements-online.txt)"
  ) from None

import helpers  # pylint: disable=unused-import
import online_helpers

from fdc import config
from fdc.online import client
from fdc.online import endpoint

DEFAULT = config.Online.SERVER_URL
LOCAL = "ws://127.0.0.1:8765/ws"
TUNNEL = "wss://futbol.example.com/ws"     # placeholder: no real domain
OTHER = "ws://192.0.2.10:18765/ws"         # documentation address (RFC 5737)
NUMBERED = "192.0.2.10:18765/ws"           # the same, written without scheme
BAD_SCHEME = "http://192.0.2.10/ws"
CONNECT_WAIT = 10.0                        # s to connect to the test server
POLL_STEP = 0.05                           # s between connection polls


def _write(folder, text):
  """Writes servidor.txt in the folder and returns its path."""
  path = os.path.join(folder, endpoint.FILE_NAME)
  with open(path, "w", encoding="utf-8") as handle:
    handle.write(text)
  return path


class ResolveTest(unittest.TestCase):
  """The four places, in order, and the addresses that are accepted."""

  def setUp(self):
    self.folder = tempfile.mkdtemp(prefix="fdc-endpoint-")

  def test_command_line_wins(self):
    _write(self.folder, LOCAL)
    url = endpoint.resolve_url(cli_url=TUNNEL,
                               environ={endpoint.ENV_NAME: OTHER},
                               folder=self.folder)
    self.assertEqual(url, TUNNEL)

  def test_variable_wins_over_the_file(self):
    _write(self.folder, LOCAL)
    url = endpoint.resolve_url(environ={endpoint.ENV_NAME: OTHER},
                               folder=self.folder)
    self.assertEqual(url, OTHER)

  def test_file_is_read_when_nothing_else_is_set(self):
    _write(self.folder, TUNNEL)
    self.assertEqual(endpoint.resolve_url(environ={}, folder=self.folder),
                     TUNNEL)

  def test_file_skips_comments_and_blank_lines(self):
    _write(self.folder, "# servidor del partido\n\n  " + TUNNEL + "  \n")
    self.assertEqual(endpoint.resolve_url(environ={}, folder=self.folder),
                     TUNNEL)

  def test_default_without_any_address(self):
    url = endpoint.resolve_url(environ={}, folder=self.folder)
    self.assertEqual(url, DEFAULT)

  def test_empty_variable_is_ignored(self):
    _write(self.folder, LOCAL)
    url = endpoint.resolve_url(environ={endpoint.ENV_NAME: "   "},
                               folder=self.folder)
    self.assertEqual(url, LOCAL)

  def test_text_without_scheme_is_plain_websocket(self):
    url = endpoint.resolve_url(cli_url=NUMBERED, environ={},
                               folder=self.folder)
    self.assertEqual(url, "ws://" + NUMBERED)

  def test_http_is_rejected_with_a_warning(self):
    _write(self.folder, LOCAL)
    with self.assertLogs("fdc.endpoint", level="WARNING"):
      url = endpoint.resolve_url(cli_url=BAD_SCHEME, environ={},
                                 folder=self.folder)
    self.assertEqual(url, LOCAL)

  def test_file_path_is_next_to_the_game(self):
    self.assertEqual(endpoint.file_path(), os.path.join(
        config.ROOT_DIR, endpoint.FILE_NAME))
    self.assertIsNone(endpoint.read_file(self.folder))


class ClientTest(unittest.TestCase):
  """The client of the game uses that address (real server, real socket)."""
  def setUp(self):
    self.folder = tempfile.mkdtemp(prefix="fdc-endpoint-")
    self.srv = self.enterContext(online_helpers.ServerThread())

  def test_client_connects_to_the_file_address(self):
    _write(self.folder, self.srv.url)
    url = endpoint.resolve_url(environ={}, folder=self.folder)
    net = client.NetClient(url)
    try:
      net.connect("Prueba")
      _wait_connected(net)
      self.assertEqual(net.status, client.OPEN)
      self.assertTrue(net.welcomed)
    finally:
      net.close()

  def test_default_url_reads_the_variable(self):
    with unittest.mock.patch.dict(os.environ,
                                  {endpoint.ENV_NAME: TUNNEL}):
      self.assertEqual(client.default_url(), TUNNEL)

  def test_a_failure_always_names_the_server(self):
    net = client.NetClient(url=OTHER)
    net._give_up("conexión cerrada")
    self.assertIn(OTHER, net.fatal)


def _wait_connected(net):
  """Polls the client until the server welcomes it (or it fails)."""
  deadline = time.monotonic() + CONNECT_WAIT
  while not net.connected:
    net.poll()
    if time.monotonic() > deadline or net.fatal:
      raise AssertionError(f"no connection: {net.status} {net.fatal}")
    time.sleep(POLL_STEP)


if __name__ == "__main__":
  unittest.main()
