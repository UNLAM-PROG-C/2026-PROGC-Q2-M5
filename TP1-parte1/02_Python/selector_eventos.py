"""Estrategias para elegir el próximo evento a reportar en una zona.

Implementa el patrón de diseño Strategy: la forma de elegir un evento
(por ejemplo, al azar y ponderada por probabilidad) queda encapsulada en
una clase intercambiable, separada de la lógica de monitoreo de
SistemaVigilancia. Esto permite, por ejemplo, reemplazarla en un test
por un selector determinístico sin tocar SistemaVigilancia.
"""

import random
from abc import ABC, abstractmethod
from typing import List

from modelo import EventoMonitoreo


class SelectorDeEventos(ABC):
    """Interfaz para elegir un evento de una lista de eventos posibles."""

    @abstractmethod
    def elegir(self, eventos: List[EventoMonitoreo]) -> EventoMonitoreo:
        """Elige un evento de la lista recibida.

        Args:
            eventos: Los eventos posibles de una zona.

        Returns:
            El evento elegido.
        """


class SelectorAleatorioPonderado(SelectorDeEventos):
    """Elige un evento al azar, respetando la probabilidad de cada uno."""

    def elegir(self, eventos: List[EventoMonitoreo]) -> EventoMonitoreo:
        """Ver SelectorDeEventos.elegir."""
        pesos = self._obtener_pesos(eventos)
        return random.choices(eventos, weights=pesos, k=1)[0]

    def _obtener_pesos(self, eventos: List[EventoMonitoreo]) -> List[float]:
        return [evento.probabilidad for evento in eventos]
