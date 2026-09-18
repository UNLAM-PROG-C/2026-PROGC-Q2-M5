"""Promedia las repeticiones de cada cantidad de hilos y grafica hilos vs. tiempo."""
import csv
import pathlib
import statistics
from collections import defaultdict

import matplotlib.pyplot as plt

RUTA_BASE = pathlib.Path(__file__).resolve().parent.parent
RUTA_CSV = RUTA_BASE / "resultados" / "resultados.csv"
RUTA_GRAFICO = RUTA_BASE / "resultados" / "grafico_hilos_vs_tiempo.png"


def leer_tiempos_por_hilos():
    tiempos_por_hilos = defaultdict(list)
    with open(RUTA_CSV, newline="", encoding="utf-8") as archivo:
        for fila in csv.DictReader(archivo):
            tiempos_por_hilos[int(fila["cantidad_hilos"])].append(float(fila["duracion_ms"]))
    return dict(sorted(tiempos_por_hilos.items()))


def graficar(tiempos_por_hilos):
    hilos = list(tiempos_por_hilos.keys())
    promedios = [statistics.mean(t) for t in tiempos_por_hilos.values()]

    plt.figure(figsize=(8, 5))
    plt.plot(hilos, promedios, marker="o")
    plt.xlabel("Cantidad de hilos (N)")
    plt.ylabel("Tiempo promedio de ejecución (ms)")
    plt.title("Tiempo de simulación vs. cantidad de hilos")
    plt.xscale("log", base=2)
    plt.xticks(hilos, hilos)
    plt.grid(True)
    plt.savefig(RUTA_GRAFICO)


def main():
    tiempos_por_hilos = leer_tiempos_por_hilos()
    graficar(tiempos_por_hilos)
    print(f"Gráfico guardado en {RUTA_GRAFICO}")


if __name__ == "__main__":
    main()
