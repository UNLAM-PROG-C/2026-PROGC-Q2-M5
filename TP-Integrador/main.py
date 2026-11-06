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
    (("--quality",), {"dest": "quality", "default": "auto",
                      "choices": ("auto", "0", "1", "2", "3"),
                      "help": "calidad de los efectos: auto (baja el nivel "
                              "sola en CPU) o Q0..Q3 fija"}),
    (("--calidad",), {"dest": "quality_mode", "default": "full",
                      "choices": ("full", "optimizado", "auto"),
                      "help": "modo de calidad: full (todo, sin gobernador), "
                              "optimizado (liviano, anda fluido en CPU) o "
                              "auto (el gobernador decide)"}),
    (("--backend",), {"dest": "backend", "default": "auto",
                      "choices": ("auto", "gpu", "cpu"),
                      "help": "backend de los efectos (auto|gpu|cpu)"}),
    (("--block",), {"dest": "block", "default": None,
                    "help": "hilos por bloque de los kernels, WxH "
                            "(por defecto 32x8)"}),
    (("--window",), {"dest": "window", "default": None,
                     "help": "tamaño de la ventana, WxH (por defecto "
                             "1280x720, nunca en pantalla exclusiva)"}),
    (("--render",), {"dest": "render", "default": None,
                     "help": "driver de SDL_RENDER_DRIVER (ej. software); "
                             "útil por escritorio remoto"}),
    (("--overlay",), {"dest": "overlay", "default": None,
                      "choices": ("off", "compact", "full"),
                      "help": "overlay de rendimiento (F2 lo cambia en vivo)"}),
    (("--demo",), {"dest": "demo", "action": "store_true",
                   "help": "demo automática de 10 segmentos, sin menús"}),
    (("--demo-seconds",), {"dest": "demo_seconds", "type": float,
                           "default": None,
                           "help": "segundos de cada segmento (por defecto "
                                   "10)"}),
    (("--demo-backends",), {"dest": "demo_backends", "default": "both",
                            "choices": ("both", "gpu", "cpu"),
                            "help": "la demo corre en los dos backends o en "
                                    "uno solo"}),
    (("--demo-frame-clock",), {"dest": "demo_frame_clock",
                               "action": "store_true",
                               "help": "la demo avanza con 1/60 s fijo por "
                                       "frame (para capturas reproducibles)"}),
    (("--measure-csv",), {"dest": "measure_csv", "default": None,
                          "help": "CSV de tiempos de la demo (por defecto "
                                  "mediciones/demo_<fecha>_<host>.csv)"}),
    (("--measure-frames",), {"dest": "measure_frames", "action": "store_true",
                             "help": "además del resumen, un CSV por frame"}),
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
    _apply_gpu_options(options)
    # The interface is imported here and not at the top: with the "spawn"
    # method the simulation process imports this module again, and this way
    # it never loads pygame nor opens windows.
    # pylint: disable-next=import-outside-toplevel
    from fdc.ui import app
    app.setup_logging()
    return app.run_app(options)


def _prepare_toolchain(options):
    """nvcc and cl.exe in the PATH (jugar.bat does not activate them)."""
    if options.backend == "cpu" or options.no_gpu:
        return
    from fdc.gpu import env    # pylint: disable=import-outside-toplevel
    env.setup()


def _apply_gpu_options(options):
    """--backend, --block and --render: before the effects start."""
    from fdc.gpu import backend    # pylint: disable=import-outside-toplevel
    _prepare_toolchain(options)
    if options.backend == "cpu":
        options.force_cpu = True
    if options.block:
        backend.set_block(options.block)
    if options.backend == "gpu" and not options.no_gpu:
        found = backend.detect()
        if found["kind"] != "gpu":
            print("GPU pedida con --backend gpu pero no disponible: "
                  f"{found['reason']}")
            print("Se usan los efectos en CPU (numpy).")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
