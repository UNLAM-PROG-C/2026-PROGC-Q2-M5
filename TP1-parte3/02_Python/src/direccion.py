"""Sentidos posibles de cruce sobre la cuerda."""
from enum import Enum


class Direccion(Enum):
    """Sentido en que un babuino cruza el cañón."""

    IZQUIERDA_A_DERECHA = ("->", "hacia la derecha")
    DERECHA_A_IZQUIERDA = ("<-", "hacia la izquierda")

    def __init__(self, flecha: str, descripcion: str):
        self.flecha = flecha
        self.descripcion = descripcion
