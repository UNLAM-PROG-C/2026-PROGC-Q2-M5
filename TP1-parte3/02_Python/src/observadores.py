"""Observers de la cuerda: el log en consola y el auditor independiente."""
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional

from constantes import CAPACIDAD_CUERDA
from direccion import Direccion
from eventos import EventoCuerda, TipoEvento


class ObservadorCuerda(ABC):
    """Observer: recibe cada evento sin que la cuerda sepa qué hace con él."""

    @abstractmethod
    def al_registrar_evento(self, evento: EventoCuerda) -> None:
        raise NotImplementedError


class RegistroConsola(ObservadorCuerda):
    """Imprime una línea por evento (la cuerda los emite de a uno por vez)."""

    def al_registrar_evento(self, evento: EventoCuerda) -> None:
        babuino = f"Babuino {evento.id_babuino:02d} ({evento.direccion.flecha})"
        print(f"[{evento.milisegundos:7.0f} ms] {babuino} | {self._descripcion(evento)}", flush=True)

    @staticmethod
    def _descripcion(evento: EventoCuerda) -> str:
        if evento.tipo is TipoEvento.LLEGA:
            return f"llega y toma el turno {evento.turno}"
        if evento.tipo is TipoEvento.SUBE:
            return f"sube a la cuerda (en cuerda: {evento.en_cuerda}, {evento.direccion.descripcion})"
        return f"baja de la cuerda (en cuerda: {evento.en_cuerda})"


@dataclass
class InformeAuditoria:
    """Lo que el auditor comprobó por su cuenta durante la simulación."""

    cruzaron: Dict[Direccion, int] = field(default_factory=lambda: {d: 0 for d in Direccion})
    maximo_simultaneo: int = 0
    peleas: int = 0
    cuerdas_rotas: int = 0
    fuera_de_turno: int = 0

    @property
    def total_cruzaron(self) -> int:
        return sum(self.cruzaron.values())

    def es_correcto(self) -> bool:
        return self.peleas == 0 and self.cuerdas_rotas == 0 and self.fuera_de_turno == 0


class Auditor(ObservadorCuerda):
    """Recalcula el estado de la cuerda solo a partir de los eventos, sin confiar en ella."""

    def __init__(self):
        self.informe = InformeAuditoria()
        self._candado = threading.Lock()
        self._en_cuerda = 0
        self._direccion: Optional[Direccion] = None
        self._proximo_turno = 0

    def al_registrar_evento(self, evento: EventoCuerda) -> None:
        with self._candado:
            if evento.tipo is TipoEvento.SUBE:
                self._registrar_subida(evento)
            elif evento.tipo is TipoEvento.BAJA:
                self._registrar_bajada(evento)

    def _registrar_subida(self, evento: EventoCuerda) -> None:
        if self._en_cuerda > 0 and self._direccion is not evento.direccion:
            self.informe.peleas += 1
        if evento.turno != self._proximo_turno:
            self.informe.fuera_de_turno += 1
        self._proximo_turno = evento.turno + 1
        self._direccion = evento.direccion
        self._en_cuerda += 1
        self.informe.maximo_simultaneo = max(self.informe.maximo_simultaneo, self._en_cuerda)
        if self._en_cuerda > CAPACIDAD_CUERDA:
            self.informe.cuerdas_rotas += 1

    def _registrar_bajada(self, evento: EventoCuerda) -> None:
        self._en_cuerda -= 1
        self.informe.cruzaron[evento.direccion] += 1
        if self._en_cuerda == 0:
            self._direccion = None
