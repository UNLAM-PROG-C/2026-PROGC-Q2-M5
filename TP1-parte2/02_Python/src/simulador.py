"""Orquesta N hilos, cada uno corriendo su propia porción de torneos completos."""
import random
import threading
import time
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Dict, List

from combate import IEstrategiaAtaque
from constantes import MILISEGUNDOS_POR_SEGUNDO, SEMILLA_MAXIMA
from guerreros import Guerrero
from torneo import ResultadoHilo, simular_torneo


@dataclass
class ResultadoGlobal:
    cantidad_torneos: int
    cantidad_hilos: int
    duracion_ms: float
    turnos_totales: int = 0
    victorias_por_guerrero: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    campeonatos_por_guerrero: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


def _repartir_torneos(cantidad_torneos: int, cantidad_hilos: int) -> List[int]:
    """Reparte la cantidad total de torneos entre los hilos lo más parejo posible."""
    base, resto = divmod(cantidad_torneos, cantidad_hilos)
    return [base + 1 if i < resto else base for i in range(cantidad_hilos)]


def _simular_lote(roster: List[Guerrero], estrategia: IEstrategiaAtaque, cantidad_torneos: int, semilla: int, resultado: ResultadoHilo) -> None:
    generador = random.Random(semilla)
    for _ in range(cantidad_torneos):
        simular_torneo(roster, estrategia, generador, resultado)


def _sumar_diccionario(destino: Dict[str, int], origen: Dict[str, int]) -> None:
    for nombre, cantidad in origen.items():
        destino[nombre] += cantidad


class SimuladorConcurrente:
    """No hay comunicación ni sincronización entre hilos: sólo join() al final."""

    def __init__(self, roster: List[Guerrero], estrategia: IEstrategiaAtaque):
        self._roster = roster
        self._estrategia = estrategia

    def _lanzar_hilos(self, reparto: List[int], resultados: List[ResultadoHilo]) -> List[threading.Thread]:
        semillas = random.Random().sample(range(SEMILLA_MAXIMA), len(reparto))
        hilos = []
        for i, cantidad_torneos in enumerate(reparto):
            args = (self._roster, self._estrategia, cantidad_torneos, semillas[i], resultados[i])
            hilos.append(threading.Thread(target=_simular_lote, args=args))
            hilos[-1].start()
        return hilos

    def _combinar_resultados(self, cantidad_torneos: int, duracion_ms: float, resultados: List[ResultadoHilo]) -> ResultadoGlobal:
        global_ = ResultadoGlobal(cantidad_torneos, len(resultados), duracion_ms)
        for resultado in resultados:
            global_.turnos_totales += resultado.turnos_totales
            _sumar_diccionario(global_.victorias_por_guerrero, resultado.victorias_por_guerrero)
            _sumar_diccionario(global_.campeonatos_por_guerrero, resultado.campeonatos_por_guerrero)
        return global_

    def ejecutar(self, cantidad_torneos: int, cantidad_hilos: int) -> ResultadoGlobal:
        reparto = _repartir_torneos(cantidad_torneos, cantidad_hilos)
        resultados = [ResultadoHilo() for _ in range(cantidad_hilos)]

        inicio = time.perf_counter()
        hilos = self._lanzar_hilos(reparto, resultados)
        for hilo in hilos:
            hilo.join()
        duracion_ms = (time.perf_counter() - inicio) * MILISEGUNDOS_POR_SEGUNDO

        return self._combinar_resultados(cantidad_torneos, duracion_ms, resultados)
