
from multiprocessing import Lock, Queue
from typing import List

from modelo import ZONAS, EventoMonitoreo
from selector_eventos import SelectorAleatorioPonderado
from sistema_vigilancia import SistemaVigilancia


class FabricaSistemasVigilancia:

    @staticmethod
    def crear_todos(
        duracion_seg: float,
        frecuencia_seg: float,
        lock_impresion: Lock,
        cola_resultados: Queue,
    ) -> List[SistemaVigilancia]:

        return [
            FabricaSistemasVigilancia._construir_uno(
                nombre_zona, eventos, duracion_seg, frecuencia_seg,
                lock_impresion, cola_resultados
            )
            for nombre_zona, eventos in ZONAS.items()
        ]

    @staticmethod
    def _construir_uno(
        zona: str,
        eventos: List[EventoMonitoreo],
        duracion_seg: float,
        frecuencia_seg: float,
        lock_impresion: Lock,
        cola_resultados: Queue,
    ) -> SistemaVigilancia:
        return SistemaVigilancia(
            zona=zona,
            eventos=eventos,
            duracion_seg=duracion_seg,
            frecuencia_seg=frecuencia_seg,
            selector_eventos=SelectorAleatorioPonderado(),
            lock_impresion=lock_impresion,
            cola_resultados=cola_resultados,
        )
