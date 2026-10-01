"""Servidor online de Futbol De Cabeza (salas 1 contra 1 por internet).

Uso:
    .venv/bin/python servidor.py                  # puerto 8765, todas las interfaces
    .venv/bin/python servidor.py --puerto 9000
    .venv/bin/python servidor.py --duracion 20    # partidos cortos (pruebas)

Sirve la página del juego (build/web, ver tools/construir_web.py) y el
WebSocket /ws en el mismo puerto. Ver docs/ONLINE.md.
"""
import multiprocessing as mp
import sys


def main(argv=None):
    from fdc.online.server import main as server_main
    return server_main(argv)


if __name__ == "__main__":
    mp.freeze_support()      # Windows: cada sala lanza su proceso de simulación con "spawn"
    sys.exit(main())
