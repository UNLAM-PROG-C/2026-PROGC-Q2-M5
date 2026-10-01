"""Contrato entre la interfaz y "algo que simula el partido".

La interfaz (fdc/ui) sólo usa estos métodos y atributos. Hoy los implementa
SimLink (fdc/ipc.py): un proceso local comunicado por colas. Para el modo
online alcanza con otra implementación (p. ej. NetLink sobre WebSocket) que
hable con la sala del servidor usando los MISMOS mensajes de fdc/protocol.py:
las pantallas, el dibujo y el sonido no cambian.

Ver docs/ONLINE.md.
"""
from abc import ABC, abstractmethod


class MatchLink(ABC):
    """Interfaz mínima que necesita la UI.

    Atributos que la UI lee:
      ready (bool), ready_info (dict del mensaje READY), error (str|None),
      error_detail (str), shutdown_report (dict|None)
    """

    ready = False
    ready_info = {}
    error = None
    error_detail = ""
    shutdown_report = None

    @abstractmethod
    def start(self):
        """Conecta / lanza la simulación (no bloquea: READY llega por poll)."""

    @abstractmethod
    def send_command(self, ctype, **payload):
        """Orden confiable (start_match, pause, ...). Devuelve su cid o None."""

    @abstractmethod
    def send_input(self, players):
        """Foto de controles reemplazable (contadores acumulados de pulsaciones)."""

    @abstractmethod
    def poll(self):
        """Sin bloquear: (mensajes nuevos, último estado o None)."""

    @abstractmethod
    def check_health(self):
        """Devuelve un texto de error si la conexión/simulación falló."""

    @abstractmethod
    def stop(self):
        """Cierre coordinado. Devuelve un informe."""

    def restart(self):
        self.stop()
        self.start()

    @property
    def alive(self):
        return self.error is None

    def debug_lines(self):
        return {}
