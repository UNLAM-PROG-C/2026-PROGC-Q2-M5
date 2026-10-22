"""Punto de entrada: python main.py <izquierda> <derecha>."""
import sys

from constantes import CAPACIDAD_CUERDA, CODIGO_ERROR
from direccion import Direccion
from observadores import InformeAuditoria, RegistroConsola
from simulacion import simular

USO = "Uso: python main.py <babuinos_izquierda> <babuinos_derecha>"
ARGUMENTOS_ESPERADOS = 3


def leer_argumentos(argv: list) -> tuple:
    if len(argv) != ARGUMENTOS_ESPERADOS:
        raise ValueError(USO)
    izquierda, derecha = int(argv[1]), int(argv[2])
    if izquierda < 0 or derecha < 0 or izquierda + derecha == 0:
        raise ValueError(f"{USO} (cantidades >= 0, al menos un babuino)")
    return izquierda, derecha


def imprimir_informe(informe: InformeAuditoria, total: int) -> None:
    izquierda_a_derecha = informe.cruzaron[Direccion.IZQUIERDA_A_DERECHA]
    derecha_a_izquierda = informe.cruzaron[Direccion.DERECHA_A_IZQUIERDA]
    print(f"\nCruzaron {informe.total_cruzaron} de {total} babuinos ({izquierda_a_derecha} hacia la derecha, {derecha_a_izquierda} hacia la izquierda)")
    print(f"Máximo simultáneo en la cuerda: {informe.maximo_simultaneo} (límite {CAPACIDAD_CUERDA})")
    print(f"Peleas (direcciones opuestas a la vez): {informe.peleas}")
    print(f"Cuerdas rotas (más de {CAPACIDAD_CUERDA}): {informe.cuerdas_rotas}")
    print(f"Ingresos fuera de turno: {informe.fuera_de_turno}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        izquierda, derecha = leer_argumentos(sys.argv)
    except ValueError as error:
        print(error, file=sys.stderr)
        return CODIGO_ERROR
    informe = simular(izquierda, derecha, [RegistroConsola()])
    imprimir_informe(informe, izquierda + derecha)
    return 0 if informe.es_correcto() else CODIGO_ERROR


if __name__ == "__main__":
    sys.exit(main())
