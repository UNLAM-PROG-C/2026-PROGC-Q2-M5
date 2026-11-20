"""Player profile: the name chosen at the start (only once) and an own id.

The name is asked the first time the game opens and is used by every mode
(tournament, local and online). It is stored on the computer so it is not
asked again:
  * desktop version: a JSON file (by default ~/.futbol_de_cabeza.json, or the
    one in the FDC_PROFILE variable);
  * browser: the localStorage of the page.

Names can repeat. To tell two people with the same name apart, each profile
has its own random id (never shown): with it the online server gives each
one a different tag, for example "Ale #4821".
"""
import json
import os
import re
import secrets
import sys

NAME_MIN_LEN = 3            # fewest letters of a name
# Most letters of a name (it fits in the scoreboard and in the lists).
NAME_MAX_LEN = 16
# Characters allowed in a name.
NAME_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    "ÁÉÍÓÚÜÑáéíóúüñ _.-")
NAME_CHARS = frozenset(NAME_ALPHABET)
NAME_RE = re.compile(
    f"^[{re.escape(NAME_ALPHABET)}]{{{NAME_MIN_LEN},{NAME_MAX_LEN}}}$")
# Rule shown on screen when a name is not valid.
NAME_RULE = (f"entre {NAME_MIN_LEN} y {NAME_MAX_LEN} letras, números o "
             "espacios")
DEFAULT_PATH = os.environ.get("FDC_PROFILE") or os.path.join(
    os.path.expanduser("~"), ".futbol_de_cabeza.json")
STORAGE_KEY = "fdc_profile"
IN_BROWSER = sys.platform == "emscripten"
# Random bytes of the player id (16 hexadecimal characters).
PLAYER_ID_BYTES = 8
# Longest stored id accepted (otherwise a new one is generated).
MAX_PLAYER_ID = 64


def valid_name(name):
  """True if the name has the allowed length and characters."""
  return bool(NAME_RE.match((name or "").strip()))


class Profile:
  """Name chosen by the player and its hidden random id."""

  def __init__(self, name, player_id=None):
    self.name = name.strip()
    self.player_id = player_id or secrets.token_hex(PLAYER_ID_BYTES)

  def renamed(self, name):
    """Same player (same id) with another name."""
    return Profile(name, self.player_id)

  def to_json(self):
    return json.dumps({"name": self.name, "id": self.player_id},
                      ensure_ascii=False)


def load(path=None):
  """Stored profile, or None if no name was chosen yet (or it is bad)."""
  try:
    raw = _read(path or DEFAULT_PATH)
    data = json.loads(raw) if raw else None
  except (OSError, ValueError, TypeError):
    return None
  if not isinstance(data, dict) or not valid_name(data.get("name")):
    return None
  return Profile(data["name"], _valid_id(data.get("id")))


def _valid_id(player_id):
  """The stored id if it looks right, else None (a new one is made)."""
  if isinstance(player_id, str) and 0 < len(player_id) <= MAX_PLAYER_ID:
    return player_id
  return None


def save(profile, path=None):
  """Stores the profile. Returns False if there is no writable disk."""
  try:
    _write(path or DEFAULT_PATH, profile.to_json())
    return True
  except OSError:
    return False        # no writable disk: it is asked again next time


def _read(path):
  if IN_BROWSER:
    # pylint: disable-next=import-outside-toplevel
    import platform     # in pygbag, "platform" exposes the JS window
    raw = platform.window.localStorage.getItem(STORAGE_KEY)
    return str(raw) if raw else None
  if not os.path.isfile(path):
    return None
  with open(path, encoding="utf-8") as fh:
    return fh.read()


def _write(path, text):
  if IN_BROWSER:
    # pylint: disable-next=import-outside-toplevel
    import platform     # in pygbag, "platform" exposes the JS window
    platform.window.localStorage.setItem(STORAGE_KEY, text)
    return
  with open(path, "w", encoding="utf-8") as fh:
    fh.write(text)
