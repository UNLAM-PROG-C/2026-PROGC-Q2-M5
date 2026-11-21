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

from fdc import config

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
                             "wss://mi-dominio/ws); también la variable "
                             "FDC_SERVER o la primera línea de "
                             "servidor.txt, junto al juego"}),
    (("--no-gpu", "--sin-efectos"),
     {"dest": "no_gpu", "action": "store_true",
      "help": "apaga los efectos (igual que FDC_EFECTOS=0): el juego "
              "queda igual que antes"}),
    (("--sin-prediccion",),
     {"dest": "no_prediction", "action": "store_true",
      "help": "online: no predice el jugador propio (si se ve raro con "
              "una conexión mala)"}),
    (("--gpu-cpu",), {"dest": "force_cpu", "action": "store_true",
                      "help": "efectos con la versión numpy (para comparar "
                              "contra la GPU)"}),
    (("--calidad",), {"dest": "quality_mode", "default": None,
                      "choices": (*config.Gpu.MODES, "off"),
                      "help": "full: todos los efectos; sin-efectos (u "
                              "off): sin postproceso. Por defecto: full "
                              "con GPU, sin-efectos con CPU"}),
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
                      "choices": ("off", "compact", "full", "steps"),
                      "help": "overlay de rendimiento (F2 lo cambia en vivo)"}),
    (("--demo",), {"dest": "demo", "action": "store_true",
                   "help": "demo automática de 7 segmentos, sin menús"}),
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
  apply_gpu_options(options)
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
  if not (config.Gpu.ENABLED and config.Effects.ENABLED):
    return                     # no CUDA and/or no effects: nothing to set
  from fdc.gpu import env    # pylint: disable=import-outside-toplevel
  env.setup()


def apply_gpu_options(options):
  """--backend, --block and --render: before the effects start."""
  from fdc.gpu import backend    # pylint: disable=import-outside-toplevel
  _prepare_toolchain(options)
  if options.backend == "cpu" or not config.Gpu.ENABLED:
    options.force_cpu = True   # FDC_GPU=0: numpy, never PyCUDA
  if options.block:
    backend.set_block(options.block)
  if _asks_cuda(options):
    _report_cuda(backend.detect())


def _asks_cuda(options):
  """True if this run wants CUDA: --backend gpu, FDC_GPU=1 and effects."""
  return (options.backend == "gpu" and not options.no_gpu
          and config.Gpu.ENABLED and config.Effects.ENABLED)


def _report_cuda(found):
  """One line when CUDA was asked for and it does not work here."""
  if found["kind"] == "gpu":
    return
  print("GPU pedida con --backend gpu pero no disponible: "
        f"{found['reason']}")
  print("Se usan los efectos en CPU (numpy).")


if __name__ == "__main__":
  multiprocessing.freeze_support()
  sys.exit(main())
