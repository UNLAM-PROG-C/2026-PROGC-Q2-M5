"""Data of the seven characters (looks only).

The drawings come from assets/characters/ (pixel art imported with
tools/import_sprites.py from assets/originals/). The simulation uses the
same abilities for everybody: nothing in this file reaches the physics.
"""
from fdc import config

# id, name, national team, shirt number and colours (shirt, detail) in RGB.
CHARACTERS = [
    {"id": "messi", "name": "Messi", "team": "Argentina", "number": 10,
     "colors": ((117, 190, 233), (250, 250, 252))},
    {"id": "maradona", "name": "Maradona", "team": "Argentina", "number": 10,
     "colors": ((117, 190, 233), (250, 250, 252))},
    {"id": "pele", "name": "Pelé", "team": "Brasil", "number": 10,
     "colors": ((252, 211, 30), (0, 150, 72))},
    {"id": "cr7", "name": "Cristiano Ronaldo", "short": "CR7",
     "team": "Portugal", "number": 7,
     "colors": ((200, 22, 42), (0, 112, 62))},
    {"id": "henry", "name": "Thierry Henry", "short": "Henry",
     "team": "Francia", "number": 12,
     "colors": ((30, 52, 132), (212, 30, 52))},
    {"id": "neymar", "name": "Neymar", "team": "Brasil", "number": 10,
     "colors": ((252, 211, 30), (0, 150, 72))},
    {"id": "mbappe", "name": "Mbappé", "team": "Francia", "number": 10,
     "colors": ((30, 52, 132), (212, 30, 52))},
]
CHARACTERS_BY_ID = {c["id"]: c for c in CHARACTERS}
CHARACTER_IDS = [c["id"] for c in CHARACTERS]
if tuple(CHARACTER_IDS) != config.CHARACTER_IDS:
  raise ValueError("the character list must match fdc/config.py")


def short_name(character):
  """Name shown on screen (a short one if the character has it)."""
  return character.get("short", character["name"])
