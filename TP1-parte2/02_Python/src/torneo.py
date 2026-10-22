"""Simulación de un torneo eliminatorio completo (cuartos -> semi -> final)."""
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from combate import IEstrategiaAtaque, simular_combate
from constantes import CANTIDAD_LUCHADORES_TORNEO
from guerreros import Guerrero


@dataclass
class ResultadoHilo:
    """Estructura de resultados propia de un hilo: nunca la toca otro hilo."""

    turnos_totales: int = 0
    victorias_por_guerrero: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    campeonatos_por_guerrero: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


def _jugar_ronda(participantes: List[Guerrero], estrategia: IEstrategiaAtaque, generador: random.Random, resultado: ResultadoHilo) -> List[Guerrero]:
    ganadores = []
    for i in range(0, len(participantes), 2):
        ganador, turnos = simular_combate(participantes[i], participantes[i + 1], estrategia, generador)
        resultado.turnos_totales += turnos
        resultado.victorias_por_guerrero[ganador.nombre] += 1
        ganadores.append(ganador)
    return ganadores


def simular_torneo(roster: List[Guerrero], estrategia: IEstrategiaAtaque, generador: random.Random, resultado: ResultadoHilo) -> None:
    """Elige 8 de los 12 guerreros al azar y los enfrenta hasta tener campeón."""
    participantes = generador.sample(roster, CANTIDAD_LUCHADORES_TORNEO)
    while len(participantes) > 1:
        participantes = _jugar_ronda(participantes, estrategia, generador, resultado)
    resultado.campeonatos_por_guerrero[participantes[0].nombre] += 1
