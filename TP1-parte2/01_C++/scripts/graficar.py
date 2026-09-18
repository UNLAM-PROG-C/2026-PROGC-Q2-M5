"""Genera el gráfico de tiempo total vs. cantidad de clones."""
import csv
import pathlib

import matplotlib.pyplot as plt

RUTA_BASE = pathlib.Path(__file__).resolve().parent.parent
RUTA_CSV = RUTA_BASE / "resultados" / "resultados.csv"
RUTA_GRAFICO = RUTA_BASE / "resultados" / "grafico_tiempo_vs_clones.png"


def leer_resultados():
    with open(RUTA_CSV, newline="", encoding="utf-8") as archivo:
        filas = list(csv.DictReader(archivo))
    cantidades = [int(fila["cantidad_clones"]) for fila in filas]
    tiempos = [int(fila["duracion_total_ms"]) for fila in filas]
    return cantidades, tiempos


def graficar(cantidades, tiempos):
    plt.figure(figsize=(8, 5))
    plt.plot(cantidades, tiempos, marker="o")
    plt.xlabel("Cantidad de clones (N)")
    plt.ylabel("Tiempo total de entrenamiento (ms)")
    plt.title("Tiempo de entrenamiento vs. cantidad de clones")
    plt.grid(True)
    plt.savefig(RUTA_GRAFICO)


def main():
    cantidades, tiempos = leer_resultados()
    graficar(cantidades, tiempos)
    print(f"Gráfico guardado en {RUTA_GRAFICO}")


if __name__ == "__main__":
    main()
