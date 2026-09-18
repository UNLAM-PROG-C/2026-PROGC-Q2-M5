"""Punto de entrada: corre la simulación y guarda el resultado en CSV."""
import csv
import sys
from pathlib import Path

from combate import EstrategiaAtaqueClasica
from guerreros import FabricaGuerreros
from simulador import ResultadoGlobal, SimuladorConcurrente

RUTA_RESULTADOS_CSV = Path(__file__).resolve().parent.parent / "resultados" / "resultados.csv"


def imprimir_resultado(resultado: ResultadoGlobal) -> None:
    campeon = max(resultado.campeonatos_por_guerrero.items(), key=lambda item: item[1])
    print(
        f"Hilos: {resultado.cantidad_hilos} | Torneos: {resultado.cantidad_torneos} | "
        f"Tiempo: {resultado.duracion_ms:.1f} ms | Turnos: {resultado.turnos_totales} | "
        f"Más campeón: {campeon[0]} ({campeon[1]})"
    )


def guardar_resultado_en_csv(resultado: ResultadoGlobal, ruta: Path) -> None:
    existia = ruta.exists()
    with open(ruta, "a", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        if not existia:
            escritor.writerow(["cantidad_hilos", "cantidad_torneos", "duracion_ms", "turnos_totales"])
        escritor.writerow([resultado.cantidad_hilos, resultado.cantidad_torneos, f"{resultado.duracion_ms:.3f}", resultado.turnos_totales])


def leer_argumentos(argv: list) -> tuple:
    if len(argv) != 3:
        raise ValueError("Uso: python main.py <cantidad_torneos> <cantidad_hilos>")
    return int(argv[1]), int(argv[2])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        cantidad_torneos, cantidad_hilos = leer_argumentos(sys.argv)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    roster = FabricaGuerreros.crear_roster()
    simulador = SimuladorConcurrente(roster, EstrategiaAtaqueClasica())
    resultado = simulador.ejecutar(cantidad_torneos, cantidad_hilos)

    imprimir_resultado(resultado)
    guardar_resultado_en_csv(resultado, RUTA_RESULTADOS_CSV)
    return 0


if __name__ == "__main__":
    sys.exit(main())
