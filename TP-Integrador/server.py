"""Futbol De Cabeza online server (1 against 1 rooms over the internet).

Usage:
    .venv/bin/python server.py                 # port 8765, all interfaces
    .venv/bin/python server.py --port 9000
    .venv/bin/python server.py --duration 20   # short matches (tests)

It serves the game page (build/web, see tools/build_web.py) and the
WebSocket /ws on the same port. See docs/ONLINE.md.
"""
import multiprocessing
import sys


def main(argv=None):
  """Runs the server (fdc/online/server.py) until it is stopped."""
  # pylint: disable-next=import-outside-toplevel
  from fdc.online import server  # Here: "spawn" imports this file again.
  return server.main(argv)


if __name__ == "__main__":
  # Windows: every room launches its simulation process with "spawn".
  multiprocessing.freeze_support()
  sys.exit(main())
