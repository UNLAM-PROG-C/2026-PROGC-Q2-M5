"""The two effects modes, their names and backend defaults."""
from fdc import config

FULL, OFF = config.Gpu.MODES
DEFAULT_MODE = FULL
CPU = "cpu"
GPU_BACKEND = "gpu"
FULL_RESOLUTION = "Q0"
FULL_STAGE = "alta"   # Keep the existing metrics label for the full chain.
OFF_ALIASES = ("off", "sin efectos", "sin_efectos", "ninguno", "none")


def mode_of(value):
  """Normalize an off alias; fall back to FULL for unknown values."""
  if isinstance(value, str) and value.strip().lower() in OFF_ALIASES:
    return OFF
  return value if value in config.Gpu.MODES else DEFAULT_MODE


def name_of(mode):
  """Readable name for the menu and performance overlay."""
  return config.Gpu.MODE_NAMES[mode_of(mode)]


def default_for(backend):
  """Start without post-processing unless CUDA is available."""
  return FULL if backend == GPU_BACKEND else OFF


def next_mode(mode):
  """Switch between the full chain and the plain pygame render."""
  return OFF if mode_of(mode) == FULL else FULL
