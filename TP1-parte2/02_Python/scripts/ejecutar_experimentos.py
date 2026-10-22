"""Corre la simulación con distintas cantidades de hilos, repitiendo cada
configuración varias veces (la cantidad total de torneos queda fija)."""
import pathlib
import subprocess
import sys

RUTA_BASE = pathlib.Path(__file__).resolve().parent.parent
RUTA_MAIN = RUTA_BASE / "src" / "main.py"
RUTA_CSV = RUTA_BASE / "resultados" / "resultados.csv"

CANTIDAD_TORNEOS = 20000
CANTIDADES_DE_HILOS = [1, 2, 4, 8, 16, 32]
REPETICIONES_POR_CONFIGURACION = 5


def ejecutar_experimentos():
    if RUTA_CSV.exists():
        RUTA_CSV.unlink()
    for cantidad_hilos in CANTIDADES_DE_HILOS:
        for repeticion in range(REPETICIONES_POR_CONFIGURACION):
            comando = [sys.executable, str(RUTA_MAIN), str(CANTIDAD_TORNEOS), str(cantidad_hilos)]
            subprocess.run(comando, check=True, cwd=RUTA_BASE)


def main():
    (RUTA_BASE / "resultados").mkdir(exist_ok=True)
    ejecutar_experimentos()
    print(f"Resultados guardados en {RUTA_CSV}")


if __name__ == "__main__":
    main()
