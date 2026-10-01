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

NAME_RE = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ _.-]{3,16}$")
NAME_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                       "ÁÉÍÓÚÜÑáéíóúüñ _.-")
DEFAULT_PATH = os.environ.get("FDC_PERFIL") or os.path.join(os.path.expanduser("~"), ".futbol_de_cabeza.json")
STORAGE_KEY = "fdc_perfil"
IN_BROWSER = sys.platform == "emscripten"


def valid_name(name):
    return bool(NAME_RE.match((name or "").strip()))


class Profile:
    def __init__(self, name, player_id=None):
        self.name = name.strip()
        self.player_id = player_id or secrets.token_hex(8)

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
    return Profile(data["name"], pid if isinstance(pid, str) and 0 < len(pid) <= 64 else None)


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
