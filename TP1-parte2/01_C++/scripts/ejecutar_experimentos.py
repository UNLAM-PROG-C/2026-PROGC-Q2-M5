"""Compila el simulador y lo corre para varias cantidades de clones.

Nota: se compila y se ejecuta en una carpeta LOCAL fuera de OneDrive
(%LOCALAPPDATA%) y recién al final se copia el CSV al repo. Ejecutar el
binario con el directorio de trabajo dentro de una carpeta sincronizada
por OneDrive provoca cierres inesperados (segmentation fault) apenas el
programa intenta escribir el archivo de resultados: es una interferencia
del propio OneDrive/antivirus con el proceso, no un bug del programa.
"""
import os
import pathlib
import shutil
import subprocess

RUTA_REPO = pathlib.Path(__file__).resolve().parent.parent
RUTA_BUILD_LOCAL = pathlib.Path(os.environ["LOCALAPPDATA"]) / "naruto_tp1_build"
RUTA_BINARIO = RUTA_BUILD_LOCAL / "naruto_entrenamiento.exe"
RUTA_CSV_LOCAL = RUTA_BUILD_LOCAL / "resultados" / "resultados.csv"
RUTA_CSV_REPO = RUTA_REPO / "resultados" / "resultados.csv"
CANTIDADES_DE_CLONES = [5, 10, 20, 40, 80, 160]


def compilar():
    fuentes = sorted(str(p) for p in (RUTA_REPO / "src").glob("*.cpp"))
    comando = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", *fuentes, "-o", str(RUTA_BINARIO)]
    subprocess.run(comando, check=True)


def ejecutar_experimentos():
    if RUTA_CSV_LOCAL.exists():
        RUTA_CSV_LOCAL.unlink()
    for cantidad in CANTIDADES_DE_CLONES:
        subprocess.run([str(RUTA_BINARIO), str(cantidad)], check=True, cwd=RUTA_BUILD_LOCAL)


def main():
    RUTA_BUILD_LOCAL.mkdir(exist_ok=True)
    (RUTA_BUILD_LOCAL / "resultados").mkdir(exist_ok=True)
    (RUTA_REPO / "resultados").mkdir(exist_ok=True)

    compilar()
    ejecutar_experimentos()
    shutil.copy2(RUTA_CSV_LOCAL, RUTA_CSV_REPO)
    print(f"Resultados guardados en {RUTA_CSV_REPO}")


if __name__ == "__main__":
    main()
