"""Eventos que la cuerda informa a sus observadores."""
from dataclasses import dataclass
from enum import Enum

from direccion import Direccion


class TipoEvento(Enum):
    LLEGA = "llega"
    SUBE = "sube"
    BAJA = "baja"


@dataclass(frozen=True)
class EventoCuerda:
    """Algo que le pasó a un babuino, con el instante en que ocurrió."""

    milisegundos: float
    id_babuino: int
    direccion: Direccion
    tipo: TipoEvento
    turno: int
    en_cuerda: int
