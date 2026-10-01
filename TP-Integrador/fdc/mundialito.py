"""Mundialito: torneo de 1 jugador contra los otros 6 personajes.

Reglas:
  * se juega una etapa por rival (orden al azar) y la dificultad sube en cada una;
  * sólo se avanza ganando; los empates se definen por gol de oro;
  * si se pierde, el torneo termina y se informa el puesto final
    (perder en la Fecha 1 = 7.º puesto ... perder la Final = 2.º puesto);
  * si se ganan las 6 etapas, se gana la Copa del Mundo (1.º puesto).
"""
import random

from .config import CHARACTER_IDS

STAGES = ("Fecha 1", "Fecha 2", "Fecha 3", "Cuartos de final", "Semifinal", "Final")
GROUP_STAGES = 3          # las tres primeras son la fase de grupos

IN_PROGRESS = "en_curso"
ELIMINATED = "eliminado"
CHAMPION = "campeon"

HUMAN_SLOT = 1            # la persona juega a la derecha
BOT_SLOT = 0


class Tournament:
    def __init__(self, player, rng=None):
        if player not in CHARACTER_IDS:
            raise ValueError(f"personaje desconocido: {player}")
        rng = rng or random.Random()
        self.player = player
        self.rivals = [c for c in CHARACTER_IDS if c != player]
        rng.shuffle(self.rivals)
        self.stage = 0
        self.results = []              # (etapa, rival, mis goles, goles del rival)
        self.status = IN_PROGRESS

    @property
    def finished(self):
        return self.status != IN_PROGRESS

    @property
    def stage_name(self):
        return STAGES[min(self.stage, len(STAGES) - 1)]

    @property
    def rival(self):
        return self.rivals[min(self.stage, len(self.rivals) - 1)]

    @property
    def level(self):
        """Dificultad del rival: crece con cada etapa (0..5)."""
        return self.stage

    @property
    def position(self):
        """Puesto final (None mientras el torneo sigue)."""
        if self.status == CHAMPION:
            return 1
        if self.status == ELIMINATED:
            return len(STAGES) + 1 - self.stage
        return None

    def record(self, my_goals, rival_goals):
        """Registra el resultado del partido actual. Devuelve True si se ganó."""
        if self.finished:
            raise RuntimeError("el Mundialito ya terminó")
        won = my_goals > rival_goals
        self.results.append((self.stage_name, self.rival, my_goals, rival_goals))
        if won:
            self.stage += 1
            if self.stage == len(STAGES):
                self.status = CHAMPION
        else:
            self.status = ELIMINATED
        return won


def ordinal(n):
    return f"{n}.º"
