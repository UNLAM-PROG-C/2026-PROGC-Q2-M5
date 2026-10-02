"""Datos de los siete personajes (sólo apariencia).

Los dibujos salen de assets/personajes/ (pixel art importado con
tools/importar_sprites.py a partir de assets/originales/). La simulación usa
las mismas capacidades para todos: nada de este archivo llega a la física.
"""
from .. import config

# id, nombre, selección, número de camiseta y colores (camiseta, detalle) en RGB
CHARACTERS = [
    {"id": "messi", "name": "Messi", "team": "Argentina", "number": 10,
     "colors": ((117, 190, 233), (250, 250, 252))},
    {"id": "maradona", "name": "Maradona", "team": "Argentina", "number": 10,
     "colors": ((117, 190, 233), (250, 250, 252))},
    {"id": "pele", "name": "Pelé", "team": "Brasil", "number": 10,
     "colors": ((252, 211, 30), (0, 150, 72))},
    {"id": "cr7", "name": "Cristiano Ronaldo", "short": "CR7", "team": "Portugal", "number": 7,
     "colors": ((200, 22, 42), (0, 112, 62))},
    {"id": "henry", "name": "Thierry Henry", "short": "Henry", "team": "Francia", "number": 12,
     "colors": ((30, 52, 132), (212, 30, 52))},
    {"id": "neymar", "name": "Neymar", "team": "Brasil", "number": 10,
     "colors": ((252, 211, 30), (0, 150, 72))},
    {"id": "mbappe", "name": "Mbappé", "team": "Francia", "number": 10,
     "colors": ((30, 52, 132), (212, 30, 52))},
]
CHARACTERS_BY_ID = {c["id"]: c for c in CHARACTERS}
CHARACTER_IDS = [c["id"] for c in CHARACTERS]
assert tuple(CHARACTER_IDS) == config.CHARACTER_IDS, "la lista de personajes debe coincidir con config"


def short_name(ch):
    return ch.get("short", ch["name"])
