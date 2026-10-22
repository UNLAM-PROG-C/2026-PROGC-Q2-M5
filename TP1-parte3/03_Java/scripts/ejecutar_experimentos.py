"""Compila el simulador Java y lo corre con distintas cantidades de camiones
(la cantidad de viajes queda fija), repitiendo cada configuracion varias veces."""
import csv
import os
import pathlib
import shutil
import subprocess

RUTA_BASE = pathlib.Path(__file__).resolve().parent.parent
RUTA_BUILD_LOCAL = pathlib.Path(os.environ["LOCALAPPDATA"]) / "carga_criolla_build"
RUTA_CSV = RUTA_BASE / "resultados" / "resultados.csv"
ENCABEZADO_CSV = ["camiones", "viajes_por_planta", "horas", "dias"]

VIAJES_POR_PLANTA = 30
CANTIDADES_DE_CAMIONES = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48]
REPETICIONES_POR_CONFIGURACION = 3


def compilar():
    fuentes = sorted(str(p) for p in (RUTA_BASE / "src").rglob("*.java"))
    RUTA_BUILD_LOCAL.mkdir(exist_ok=True)
    subprocess.run([shutil.which("javac"), "-d", str(RUTA_BUILD_LOCAL), *fuentes], check=True)


def correr(camiones):
    comando = [shutil.which("java"), "-cp", str(RUTA_BUILD_LOCAL), "cargacriolla.Main", str(camiones), str(VIAJES_POR_PLANTA), "--csv"]
    salida = subprocess.run(comando, check=True, capture_output=True, text=True).stdout
    return salida.strip().split(",")


def main():
    (RUTA_BASE / "resultados").mkdir(exist_ok=True)
    compilar()
    with open(RUTA_CSV, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(ENCABEZADO_CSV)
        for camiones in CANTIDADES_DE_CAMIONES:
            for _ in range(REPETICIONES_POR_CONFIGURACION):
                fila = correr(camiones)
                escritor.writerow(fila)
                archivo.flush()
                print(f"N={fila[0]:>2}  {fila[3]} dias", flush=True)
    print(f"Resultados guardados en {RUTA_CSV}")


if __name__ == "__main__":
    main()
