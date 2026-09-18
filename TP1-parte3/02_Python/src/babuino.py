"""Un babuino: llega, espera su turno, cruza la cuerda y baja."""
import time

from cuerda import Cuerda
from direccion import Direccion


class Babuino:
    """Su cuerpo (cruzar) corre en un hilo propio. Solo se sincroniza a través de la cuerda."""

    def __init__(self, id_babuino: int, direccion: Direccion, cuerda: Cuerda, demora_llegada_s: float, duracion_cruce_s: float):
        self.id_babuino = id_babuino
        self.direccion = direccion
        self._cuerda = cuerda
        self._demora_llegada_s = demora_llegada_s
        self._duracion_cruce_s = duracion_cruce_s

    def cruzar(self) -> None:
        time.sleep(self._demora_llegada_s)
        turno = self._cuerda.entrar(self.id_babuino, self.direccion)
        time.sleep(self._duracion_cruce_s)
        self._cuerda.salir(self.id_babuino, self.direccion, turno)
