from typing import Dict, List, NamedTuple


class EventoMonitoreo(NamedTuple):
    nombre: str
    probabilidad: float
    es_critico: bool


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
