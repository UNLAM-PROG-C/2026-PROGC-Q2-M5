

import random
from abc import ABC, abstractmethod
from typing import List

from modelo import EventoMonitoreo


class SelectorDeEventos(ABC):
   
    @abstractmethod
    def elegir(self, eventos: List[EventoMonitoreo]) -> EventoMonitoreo: ...
       


class SelectorAleatorioPonderado(SelectorDeEventos):


    def elegir(self, eventos: List[EventoMonitoreo]) -> EventoMonitoreo:

        pesos = self._obtener_pesos(eventos)
        return random.choices(eventos, weights=pesos, k=1)[0]

    def _obtener_pesos(self, eventos: List[EventoMonitoreo]) -> List[float]:
        return [evento.probabilidad for evento in eventos]
