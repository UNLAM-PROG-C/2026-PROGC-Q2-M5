"""Fábrica de babuinos (patrón Factory Method)."""
import random
from typing import List

from babuino import Babuino
from constantes import CRUCE_MAXIMO_S, CRUCE_MINIMO_S, LLEGADA_MAXIMA_S
from cuerda import Cuerda
from direccion import Direccion


class FabricaBabuinos:
    """Crea toda la tropa en un solo hilo, antes de que arranque el cruce."""

    @staticmethod
    def crear(izquierda: int, derecha: int, cuerda: Cuerda, azar: random.Random, escala_tiempo: float) -> List[Babuino]:
        """Crea `izquierda` babuinos que van hacia la derecha y `derecha` que van hacia la izquierda."""
        direcciones = [Direccion.IZQUIERDA_A_DERECHA] * izquierda + [Direccion.DERECHA_A_IZQUIERDA] * derecha
        azar.shuffle(direcciones)
        return [FabricaBabuinos._crear_uno(numero, direccion, cuerda, azar, escala_tiempo) for numero, direccion in enumerate(direcciones, start=1)]

    @staticmethod
    def _crear_uno(numero: int, direccion: Direccion, cuerda: Cuerda, azar: random.Random, escala_tiempo: float) -> Babuino:
        demora_llegada_s = azar.uniform(0, LLEGADA_MAXIMA_S) * escala_tiempo
        duracion_cruce_s = azar.uniform(CRUCE_MINIMO_S, CRUCE_MAXIMO_S) * escala_tiempo
        return Babuino(numero, direccion, cuerda, demora_llegada_s, duracion_cruce_s)
