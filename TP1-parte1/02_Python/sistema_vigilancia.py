import random
import time
from multiprocessing import Process
from multiprocessing.queues import Queue as QueueType
from multiprocessing.synchronize import Lock as LockType
from typing import Any, Dict, List

from modelo import EventoMonitoreo
from selector_eventos import SelectorDeEventos


class SistemaVigilancia(Process):

    def __init__(
        self,
        zona: str,
        eventos: List[EventoMonitoreo],
        duracion_seg: float,
        frecuencia_seg: float,
        selector_eventos: SelectorDeEventos,
        lock_impresion: LockType,
        cola_resultados: QueueType,
    ) -> None:
        super().__init__(name=f"Vigilancia-{zona}")
        self._zona = zona
        self._eventos = eventos
        self._duracion_seg = duracion_seg
        self._frecuencia_seg = frecuencia_seg
        self._selector_eventos = selector_eventos
        self._lock_impresion = lock_impresion
        self._cola_resultados = cola_resultados
        self._total_eventos = 0
        self._total_criticos = 0

    def run(self) -> None:
        self._resembrar_aleatoriedad()
        tiempo_inicio = time.monotonic()
        while self._sigue_monitoreando(tiempo_inicio):
            time.sleep(self._frecuencia_seg)
            if not self._sigue_monitoreando(tiempo_inicio):
                break
            self._procesar_un_evento()
        self._informar_resumen_final()
        self._enviar_resultado_al_proceso_principal()

    def _resembrar_aleatoriedad(self) -> None:
        random.seed()

    def _sigue_monitoreando(self, tiempo_inicio: float) -> bool:
        return (time.monotonic() - tiempo_inicio) < self._duracion_seg

    def _procesar_un_evento(self) -> None:
        evento = self._selector_eventos.elegir(self._eventos)
        self._registrar_evento(evento)
        self._informar_evento(evento)

    def _registrar_evento(self, evento: EventoMonitoreo) -> None:
        self._total_eventos += 1
        if evento.es_critico:
            self._total_criticos += 1

    def _informar_evento(self, evento: EventoMonitoreo) -> None:
        with self._lock_impresion:
            print(f"[{self._zona}] - {evento.nombre}")

    def _informar_resumen_final(self) -> None:
        with self._lock_impresion:
            print(
                f"\n--- Resumen de monitoreo: {self._zona} "
                f"(PID: {self.pid}) ---\n"
                f"Total de eventos detectados: {self._total_eventos}\n"
                f"Total de eventos críticos:   {self._total_criticos}\n"
            )

    def _enviar_resultado_al_proceso_principal(self) -> None:
        resultado: Dict[str, Any] = {
            "zona": self._zona,
            "total_eventos": self._total_eventos,
            "total_criticos": self._total_criticos,
        }
        self._cola_resultados.put(resultado)
