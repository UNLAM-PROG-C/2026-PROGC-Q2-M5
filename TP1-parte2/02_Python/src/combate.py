"""Resolución de un combate 1 a 1 entre dos guerreros."""
import random
from abc import ABC, abstractmethod
from typing import Tuple

from constantes import DANIO_MINIMO, MULTIPLICADOR_CRITICO, PROBABILIDAD_DESEMPATE_VELOCIDAD
from guerreros import Guerrero


class IEstrategiaAtaque(ABC):
    """Strategy: cómo se resuelve un ataque, desacoplado del combate."""

    @abstractmethod
    def resolver_ataque(self, atacante: Guerrero, defensor: Guerrero, generador: random.Random) -> int:
        raise NotImplementedError


class EstrategiaAtaqueClasica(IEstrategiaAtaque):
    """Bloqueo -> crítico -> daño, tal como lo describe el enunciado."""

    def resolver_ataque(self, atacante: Guerrero, defensor: Guerrero, generador: random.Random) -> int:
        if generador.random() < defensor.bloqueo:
            return 0
        danio = max(DANIO_MINIMO, atacante.ataque - defensor.defensa)
        if generador.random() < atacante.critico:
            danio *= MULTIPLICADOR_CRITICO
        return danio


def _quien_empieza(a: Guerrero, b: Guerrero, generador: random.Random) -> bool:
    """True si ataca primero "a": gana el más veloz, empate se decide al azar."""
    if a.velocidad != b.velocidad:
        return a.velocidad > b.velocidad
    return generador.random() < PROBABILIDAD_DESEMPATE_VELOCIDAD


def simular_combate(a: Guerrero, b: Guerrero, estrategia: IEstrategiaAtaque, generador: random.Random) -> Tuple[Guerrero, int]:
    """Combate por turnos hasta que uno de los dos llega a 0 de vida."""
    vida = {a.nombre: a.vida, b.nombre: b.vida}
    ataca_a = _quien_empieza(a, b, generador)
    turnos = 0
    while vida[a.nombre] > 0 and vida[b.nombre] > 0:
        atacante, defensor = (a, b) if ataca_a else (b, a)
        vida[defensor.nombre] -= estrategia.resolver_ataque(atacante, defensor, generador)
        ataca_a = not ataca_a
        turnos += 1
    ganador = a if vida[b.nombre] <= 0 else b
    return ganador, turnos
