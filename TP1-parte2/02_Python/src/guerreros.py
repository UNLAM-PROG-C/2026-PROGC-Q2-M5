"""Roster de guerreros y su fábrica de creación (patrón Factory Method)."""
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Guerrero:
    """Ficha de un guerrero. Inmutable: se comparte de solo lectura entre hilos."""

    nombre: str
    vida: int
    ataque: int
    defensa: int
    velocidad: int
    critico: float
    bloqueo: float


class FabricaGuerreros:
    """Factory Method: crea el roster fijo de guerreros del torneo."""

    @staticmethod
    def crear_roster() -> List[Guerrero]:
        return [
            Guerrero("Liu Kang", 100, 22, 10, 7, 0.15, 0.10),
            Guerrero("Kung Lao", 90, 24, 8, 8, 0.20, 0.10),
            Guerrero("Johnny Cage", 95, 20, 9, 6, 0.25, 0.10),
            Guerrero("Reptile", 85, 23, 7, 9, 0.15, 0.08),
            Guerrero("Sub-Zero", 110, 21, 13, 5, 0.10, 0.20),
            Guerrero("Shang Tsung", 90, 26, 6, 5, 0.20, 0.08),
            Guerrero("Kitana", 88, 22, 8, 9, 0.18, 0.12),
            Guerrero("Jax", 120, 28, 12, 3, 0.10, 0.10),
            Guerrero("Mileena", 85, 24, 6, 10, 0.22, 0.07),
            Guerrero("Baraka", 105, 27, 9, 4, 0.12, 0.10),
            Guerrero("Scorpion", 95, 25, 8, 6, 0.20, 0.10),
            Guerrero("Raiden", 100, 25, 10, 7, 0.25, 0.15),
        ]
