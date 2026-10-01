"""Contrato entre la interfaz y "algo que simula el partido".

Las pantallas locales (Multijugador local y Mundialito) sólo usan estos
métodos y atributos. Los implementa SimLink (fdc/ipc.py): un proceso de
simulación comunicado por colas. El servidor online usa el mismo SimLink, uno
por sala en juego.

El partido online no pasa por este contrato: su pantalla (OnlineMatchScreen)
habla con NetClient (fdc/online/client.py), que además maneja salas, pausa
pedida, "listo" y reconexión. Los estados y eventos que dibuja son los mismos
de fdc/protocol.py. Ver docs/ONLINE.md.
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
