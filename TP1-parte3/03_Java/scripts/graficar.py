"""Promedia las repeticiones y grafica dias necesarios vs. cantidad de camiones."""
import csv
import pathlib
import statistics
from collections import defaultdict

import matplotlib.pyplot as plt

RUTA_BASE = pathlib.Path(__file__).resolve().parent.parent
RUTA_CSV = RUTA_BASE / "resultados" / "resultados.csv"
RUTA_GRAFICO = RUTA_BASE / "resultados" / "grafico_camiones_vs_dias.png"


def leer_dias_por_camiones():
    dias_por_camiones = defaultdict(list)
    with open(RUTA_CSV, newline="", encoding="utf-8") as archivo:
        for fila in csv.DictReader(archivo):
            dias_por_camiones[int(fila["camiones"])].append(float(fila["dias"]))
    return dict(sorted(dias_por_camiones.items()))


def graficar(dias_por_camiones):
    camiones = list(dias_por_camiones.keys())
    promedios = [statistics.mean(d) for d in dias_por_camiones.values()]

    plt.figure(figsize=(8, 5))
    plt.plot(camiones, promedios, marker="o")
    plt.xlabel("Cantidad de camiones (N)")
    plt.ylabel("Tiempo para completar todos los viajes (dias)")
    plt.title("Carga Criolla S.A.: dias necesarios vs. cantidad de camiones")
    plt.xscale("log", base=2)
    plt.xticks(camiones, camiones)
    plt.grid(True)
    plt.savefig(RUTA_GRAFICO)


def main():
    dias_por_camiones = leer_dias_por_camiones()
    graficar(dias_por_camiones)
    for camiones, dias in dias_por_camiones.items():
        print(f"N={camiones:>2}  {statistics.mean(dias):6.2f} dias")
    print(f"Grafico guardado en {RUTA_GRAFICO}")


if __name__ == "__main__":
    main()
