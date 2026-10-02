"""Perfil del jugador: el nombre que elige al empezar (una sola vez) y un id propio.

El nombre se pide al abrir el juego por primera vez y vale para todos los
modos (Mundialito, local y online). Se guarda en el equipo para no volver a
pedirlo:
  * versión de escritorio: un archivo JSON (por defecto ~/.futbol_de_cabeza.json,
    o el de la variable FDC_PERFIL);
  * navegador: el localStorage de la página.

Los nombres se pueden repetir. Para distinguir a dos personas con el mismo
nombre, cada perfil tiene un id aleatorio propio (nunca se muestra): con él el
servidor online le da a cada una una etiqueta distinta, por ejemplo "Ale #4821".
"""
import json
import os
import re
import secrets
import sys

NAME_MIN_LEN = 3            # letras mínimas de un nombre
NAME_MAX_LEN = 16           # letras máximas de un nombre (entra en el marcador y en las listas)
# caracteres que se pueden usar en un nombre
NAME_ALPHABET = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                 "ÁÉÍÓÚÜÑáéíóúüñ _.-")
NAME_CHARS = frozenset(NAME_ALPHABET)
NAME_RE = re.compile(f"^[{re.escape(NAME_ALPHABET)}]{{{NAME_MIN_LEN},{NAME_MAX_LEN}}}$")
NAME_RULE = f"entre {NAME_MIN_LEN} y {NAME_MAX_LEN} letras, números o espacios"
DEFAULT_PATH = os.environ.get("FDC_PERFIL") or os.path.join(os.path.expanduser("~"), ".futbol_de_cabeza.json")
STORAGE_KEY = "fdc_perfil"
IN_BROWSER = sys.platform == "emscripten"
PLAYER_ID_BYTES = 8         # bytes aleatorios del id del jugador (16 caracteres hexadecimales)
MAX_PLAYER_ID = 64          # largo máximo aceptado de un id guardado (si no, se genera otro)


def valid_name(name):
    return bool(NAME_RE.match((name or "").strip()))


class Profile:
    def __init__(self, name, player_id=None):
        self.name = name.strip()
        self.player_id = player_id or secrets.token_hex(PLAYER_ID_BYTES)

    def renamed(self, name):
        """Mismo jugador (mismo id) con otro nombre."""
        return Profile(name, self.player_id)

    def to_json(self):
        return json.dumps({"name": self.name, "id": self.player_id}, ensure_ascii=False)


def load(path=None):
    """Perfil guardado, o None si todavía no eligió nombre (o el guardado no sirve)."""
    try:
        raw = _read(path or DEFAULT_PATH)
        data = json.loads(raw) if raw else None
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not valid_name(data.get("name")):
        return None
    pid = data.get("id")
    return Profile(data["name"], pid if isinstance(pid, str) and 0 < len(pid) <= MAX_PLAYER_ID else None)


def save(profile, path=None):
    try:
        _write(path or DEFAULT_PATH, profile.to_json())
        return True
    except OSError:
        return False                        # sin disco escribible: se vuelve a pedir la próxima vez


def _read(path):
    if IN_BROWSER:
        import platform                     # en pygbag, "platform" expone el objeto window de JS
        raw = platform.window.localStorage.getItem(STORAGE_KEY)
        return str(raw) if raw else None
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    if IN_BROWSER:
        import platform
        platform.window.localStorage.setItem(STORAGE_KEY, text)
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
