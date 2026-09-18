"""Compila y ejecuta el bano compartido.

Uso:
    python scripts/ejecutar.py bano <hombres> <mujeres>
    python scripts/ejecutar.py verificar

Se compila y se corre en una carpeta LOCAL (%LOCALAPPDATA%), no dentro de OneDrive: en el TP de
Naruto vimos que los binarios ejecutados con el directorio de trabajo dentro de OneDrive se cerraban
inesperadamente.
"""
import os
import pathlib
import shutil
import subprocess
import sys

RUTA_BASE = pathlib.Path(__file__).resolve().parent.parent
RUTA_BUILD_LOCAL = pathlib.Path(os.environ["LOCALAPPDATA"]) / "bano_build"
BANDERAS = ["-std=c++17", "-O2", "-Wall", "-Wextra", "-pthread"]
CODIGO_ERROR = 1
ARGUMENTOS_BANO = 4


def fuentes_de_la_simulacion():
    """Todos los .cpp de src/ menos el main de la simulacion."""
    return sorted(str(p) for p in (RUTA_BASE / "src").glob("*.cpp") if p.name != "main.cpp")


def compilar(nombre, fuentes):
    RUTA_BUILD_LOCAL.mkdir(exist_ok=True)
    salida = RUTA_BUILD_LOCAL / f"{nombre}.exe"
    subprocess.run([shutil.which("g++"), *BANDERAS, *fuentes, "-o", str(salida)], check=True)
    return salida


def main(argv):
    if len(argv) >= 2 and argv[1] == "bano" and len(argv) == ARGUMENTOS_BANO:
        ejecutable = compilar("bano", [str(RUTA_BASE / "src" / "main.cpp"), *fuentes_de_la_simulacion()])
        return subprocess.run([str(ejecutable), argv[2], argv[3]], cwd=RUTA_BUILD_LOCAL).returncode
    if len(argv) == 2 and argv[1] == "verificar":
        ejecutable = compilar("verificar", [str(RUTA_BASE / "tests" / "verificar.cpp"), *fuentes_de_la_simulacion()])
        return subprocess.run([str(ejecutable)], cwd=RUTA_BUILD_LOCAL).returncode
    print(__doc__)
    return CODIGO_ERROR


if __name__ == "__main__":
    sys.exit(main(sys.argv))
