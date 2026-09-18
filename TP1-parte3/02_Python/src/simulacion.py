"""Arma la cuerda y la tropa, lanza un hilo por babuino y espera con join()."""
import random
import threading
from typing import List, Optional, Type

from constantes import ESCALA_TIEMPO_NORMAL
from cuerda import Cuerda, Reloj
from fabrica import FabricaBabuinos
from observadores import Auditor, InformeAuditoria, ObservadorCuerda


def _lanzar_hilos(babuinos: list) -> List[threading.Thread]:
    hilos = [threading.Thread(target=b.cruzar, name=f"babuino-{b.id_babuino}") for b in babuinos]
    for hilo in hilos:
        hilo.start()
    return hilos


def simular(
    izquierda: int,
    derecha: int,
    observadores: Optional[List[ObservadorCuerda]] = None,
    escala_tiempo: float = ESCALA_TIEMPO_NORMAL,
    clase_cuerda: Type[Cuerda] = Cuerda,
) -> InformeAuditoria:
    """Corre un cruce completo y devuelve lo que comprobó el auditor."""
    auditor = Auditor()
    cuerda = clase_cuerda([*(observadores or []), auditor], Reloj())
    babuinos = FabricaBabuinos.crear(izquierda, derecha, cuerda, random.Random(), escala_tiempo)
    for hilo in _lanzar_hilos(babuinos):
        hilo.join()
    return auditor.informe
