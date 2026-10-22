"""La cuerda: un monitor que garantiza que ningún babuino se cruce ni la rompa."""
import threading
import time
from typing import List, Optional

from constantes import CAPACIDAD_CUERDA, MILISEGUNDOS_POR_SEGUNDO
from direccion import Direccion
from eventos import EventoCuerda, TipoEvento
from observadores import ObservadorCuerda


class Reloj:
    """Milisegundos transcurridos desde que arrancó la simulación."""

    def __init__(self):
        self._inicio = time.perf_counter()

    def milisegundos(self) -> float:
        return (time.perf_counter() - self._inicio) * MILISEGUNDOS_POR_SEGUNDO


class Cuerda:
    """Monitor (threading.Condition) con admisión FIFO por número de turno.

    Cada babuino toma un turno al llegar y solo sube cuando (1) es su turno y (2) la cuerda
    está vacía, o va en su misma dirección y tiene lugar. Como el turno se respeta siempre, un
    babuino de dirección contraria al frente de la fila frena a los de atrás hasta que la cuerda
    se vacía: nadie espera indefinidamente (no hay inanición).
    """

    def __init__(self, observadores: List[ObservadorCuerda], reloj: Reloj):
        self._condicion = threading.Condition()
        self._observadores = observadores
        self._reloj = reloj
        self._proximo_turno_a_entregar = 0
        self._turno_que_puede_subir = 0
        self._en_cuerda = 0
        self._direccion: Optional[Direccion] = None

    def entrar(self, id_babuino: int, direccion: Direccion) -> int:
        """Bloquea hasta poder subir. Devuelve el turno que le tocó."""
        with self._condicion:
            turno = self._tomar_turno(id_babuino, direccion)
            self._condicion.wait_for(lambda: self._puede_subir(turno, direccion))
            self._subir(id_babuino, direccion, turno)
            return turno

    def salir(self, id_babuino: int, direccion: Direccion, turno: int) -> None:
        with self._condicion:
            self._en_cuerda -= 1
            if self._en_cuerda == 0:
                self._direccion = None
            self._notificar(id_babuino, direccion, TipoEvento.BAJA, turno)
            self._condicion.notify_all()

    def _tomar_turno(self, id_babuino: int, direccion: Direccion) -> int:
        turno = self._proximo_turno_a_entregar
        self._proximo_turno_a_entregar += 1
        self._notificar(id_babuino, direccion, TipoEvento.LLEGA, turno)
        return turno

    def _puede_subir(self, turno: int, direccion: Direccion) -> bool:
        if turno != self._turno_que_puede_subir:
            return False
        misma_direccion = self._direccion is direccion
        return self._en_cuerda == 0 or (misma_direccion and self._en_cuerda < CAPACIDAD_CUERDA)

    def _subir(self, id_babuino: int, direccion: Direccion, turno: int) -> None:
        self._direccion = direccion
        self._en_cuerda += 1
        self._turno_que_puede_subir += 1
        self._notificar(id_babuino, direccion, TipoEvento.SUBE, turno)
        self._condicion.notify_all()

    def _notificar(self, id_babuino: int, direccion: Direccion, tipo: TipoEvento, turno: int) -> None:
        evento = EventoCuerda(self._reloj.milisegundos(), id_babuino, direccion, tipo, turno, self._en_cuerda)
        for observador in self._observadores:
            observador.al_registrar_evento(evento)
