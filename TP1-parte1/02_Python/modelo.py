"""Modelo de datos del sistema de monitoreo.

Define los eventos que puede reportar cada zona (con su probabilidad y
si es o no un evento crítico) y la tabla de zonas del parque.

Mantener esta información separada de la lógica de vigilancia permite
agregar, quitar o modificar zonas y eventos sin tocar el resto del
código (principio de responsabilidad única).
"""

from typing import Dict, List, NamedTuple


class EventoMonitoreo(NamedTuple):
    """Un posible evento que puede reportar una zona.

    Attributes:
        nombre: Descripción del evento, tal como se imprime por consola.
        probabilidad: Probabilidad del evento, entre 0.0 y 1.0.
        es_critico: True si el evento se considera crítico.
    """
    nombre: str
    probabilidad: float
    es_critico: bool


# Eventos considerados críticos según el enunciado:
#   - Dinosaurio fuera de su recinto.
#   - Falla en el cerco eléctrico.
#   - Pérdida de comunicación.
#   - Alerta de seguridad.
# El resto de los eventos (Todo Normal, Pérdida de visibilidad,
# Comportamiento inusual, Estampida, Falla del sistema, Acceso no
# autorizado) no están en esa lista, por lo que no se consideran
# críticos.
ZONAS: Dict[str, List[EventoMonitoreo]] = {
    "Sector del Tiranosaurio": [
        EventoMonitoreo("Todo Normal", 0.80, False),
        EventoMonitoreo("Tiranosaurio fuera del recinto", 0.10, True),
        EventoMonitoreo("Falla en el cerco eléctrico", 0.10, True),
    ],
    "Área de Velociraptores": [
        EventoMonitoreo("Todo Normal", 0.70, False),
        EventoMonitoreo("Pérdida de visibilidad", 0.20, False),
        EventoMonitoreo("Falla en el cerco eléctrico", 0.10, True),
    ],
    "Recinto de los Triceratops": [
        EventoMonitoreo("Todo Normal", 0.60, False),
        EventoMonitoreo("Comportamiento inusual", 0.30, False),
        EventoMonitoreo("Estampida", 0.10, False),
    ],
    "Centro de Visitantes": [
        EventoMonitoreo("Todo Normal", 0.80, False),
        EventoMonitoreo("Pérdida de comunicación", 0.15, True),
        EventoMonitoreo("Alerta de seguridad", 0.05, True),
    ],
    "Laboratorio Genético": [
        EventoMonitoreo("Todo Normal", 0.80, False),
        EventoMonitoreo("Falla del sistema", 0.10, False),
        EventoMonitoreo("Pérdida de comunicación", 0.05, True),
        EventoMonitoreo("Acceso no autorizado", 0.05, True),
    ],
}
