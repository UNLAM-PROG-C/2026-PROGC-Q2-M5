"""Futbol De Cabeza - punto de entrada.

Uso:
    .venv/bin/python main.py                 # juego normal
    .venv/bin/python main.py --prueba        # modo de prueba (poderes a demanda)
    .venv/bin/python main.py --semilla 1234  # azar reproducible
    .venv/bin/python main.py --servidor wss://mi-dominio/ws   # servidor online
"""
import argparse
import multiprocessing as mp
import os
import sys


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Futbol De Cabeza: duelo de cabezones (local u online).")
    p.add_argument("--prueba", "--test", dest="test_mode", action="store_true",
                   default=os.environ.get("FDC_PRUEBA") == "1",
                   help="modo de prueba: F5/F6 elegir poder, F7 generarlo, F8/F9 darlo a J1/J2, "
                        "F12 provocar un fallo en la simulación")
    p.add_argument("--semilla", "--seed", dest="seed", type=int, default=None,
                   help="semilla fija para el azar de la simulación")
    p.add_argument("--duracion", dest="duration", type=float, default=None,
                   help="duración del partido en segundos (por defecto 60; útil para pruebas)")
    p.add_argument("--sin-audio", dest="no_audio", action="store_true", help="desactiva el sonido")
    p.add_argument("--pantalla-completa", dest="fullscreen", action="store_true")
    p.add_argument("--depuracion", dest="debug_panel", action="store_true",
                   help="muestra el panel de depuración (F3) desde el inicio")
    p.add_argument("--servidor", dest="server_url", default=None,
                   help="servidor online (ej. ws://localhost:8765/ws o wss://mi-dominio/ws); "
                        "también se puede usar la variable FDC_SERVIDOR")
    return p.parse_args(argv)


def main(argv=None):
    options = parse_args(argv)
    # La interfaz se importa acá y no al principio del archivo: con el método
    # "spawn" el proceso de simulación vuelve a importar este módulo y así
    # nunca carga pygame ni abre ventanas.
    from fdc.ui.app import run_app, setup_logging
    setup_logging()
    return run_app(options)


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
