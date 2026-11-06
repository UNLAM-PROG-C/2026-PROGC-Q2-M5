"""Futbol De Cabeza - entry point.

Usage:
    .venv/bin/python main.py                 # normal game
    .venv/bin/python main.py --test          # test mode (powers on demand)
    .venv/bin/python main.py --seed 1234     # repeatable randomness
    .venv/bin/python main.py --server wss://my-domain/ws   # online server
"""
import argparse
import multiprocessing
import os
import sys

# Command line options: (flags, argparse settings). The help texts are in
# Spanish because the player reads them.
COMMAND_LINE = (
    (("--test",), {"dest": "test_mode", "action": "store_true",
                   "default": os.environ.get("FDC_TEST") == "1",
                   "help": "modo de prueba: F5/F6 elegir poder, F7 "
                           "generarlo, F8/F9 darlo a J1/J2, F12 provocar un "
                           "fallo en la simulación"}),
    (("--seed",), {"dest": "seed", "type": int, "default": None,
                   "help": "semilla fija para el azar de la simulación"}),
    (("--duration",), {"dest": "duration", "type": float, "default": None,
                       "help": "duración del partido en segundos (por "
                               "defecto 60; útil para pruebas)"}),
    (("--no-audio",), {"dest": "no_audio", "action": "store_true",
                       "help": "desactiva el sonido"}),
    (("--fullscreen",), {"dest": "fullscreen", "action": "store_true",
                         "help": "arranca en pantalla completa"}),
    (("--debug",), {"dest": "debug_panel", "action": "store_true",
                    "help": "muestra el panel de depuración (F3) desde el "
                            "inicio"}),
    (("--server",), {"dest": "server_url", "default": None,
                     "help": "servidor online (ej. ws://localhost:8765/ws o "
                             "wss://mi-dominio/ws); también se puede usar la "
                             "variable FDC_SERVER"}),
    (("--no-gpu",), {"dest": "no_gpu", "action": "store_true",
                     "help": "apaga los efectos de GPU (el juego queda "
                             "igual que antes)"}),
    (("--gpu-quality",), {"dest": "gpu_quality", "default": None,
                          "choices": ("baja", "media", "alta"),
                          "help": "calidad de los efectos (baja|media|alta)"}),
    (("--gpu-cpu",), {"dest": "force_cpu", "action": "store_true",
                      "help": "efectos con la versión numpy (para comparar "
                              "contra la GPU)"}),
)


def parse_args(argv=None):
    """Options of the command line (see COMMAND_LINE)."""
    parser = argparse.ArgumentParser(
        description="Futbol De Cabeza: duelo de cabezones (local u online).")
    for flags, settings in COMMAND_LINE:
        parser.add_argument(*flags, **settings)
    return parser.parse_args(argv)


def main(argv=None):
    """Parses the options and runs the game."""
    options = parse_args(argv)
    # The interface is imported here and not at the top: with the "spawn"
    # method the simulation process imports this module again, and this way
    # it never loads pygame nor opens windows.
    # pylint: disable-next=import-outside-toplevel
    from fdc.ui import app
    app.setup_logging()
    return app.run_app(options)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
