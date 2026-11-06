"""Quality levels of the effects chain: which stages are drawn.

`baja` keeps only the sparks (the cheapest), `media` adds the glow and the
spotlights and `alta` adds the heat waves, the trail and the contrast
stretch. The game starts with config.Gpu.QUALITY.

`QualityGovernor` (F7) is the adaptive part: on the CPU path it watches the
frame time and moves between Q0 (full) and Q3 (the cheapest) so a notebook
without NVIDIA stays playable. With the GPU the level is always Q0.
"""
import collections

from fdc import config

GLOW = "glow"
PARTICLES = "particles"
LIGHTS = "lights"
HEAT = "heat"
TRAIL = "trail"
HISTOGRAM = "histogram"

# From the cheapest to the most expensive (order of the drops too).
LEVELS = {
    "baja": (PARTICLES,),
    "media": (GLOW, PARTICLES, LIGHTS),
    "alta": (GLOW, PARTICLES, LIGHTS, HEAT, TRAIL, HISTOGRAM),
}

# --- F7: adaptive levels of the CPU path (the GPU always runs Q0) ----------
AUTO = "auto"
CPU = "cpu"
MIN_LEVEL = 0             # best level (full resolution)
NEVER = 0.0                 # start: the first change needs no wait
ONE = 1                   # one level per change
# Stages that each level does NOT run (the pixel size is QUALITY_SCALES).
SKIPPED = {
    0: (),
    1: (HISTOGRAM,),
    2: (HISTOGRAM, HEAT, TRAIL),
    3: (GLOW, HISTOGRAM, HEAT, TRAIL),
}
# --- F11: quality modes of the projector demo ------------------------------
# Four explicit modes, chosen in the menu, with a key and with --calidad:
#   full        everything at full resolution and no governor (it may
#               stutter: that is the point on a notebook without NVIDIA);
#   optimizado  only the cheap stage and no crowd, at full resolution (sharp);
#   "sin-efectos" (or "off"): nothing at all, the plain pygame render: the
#               case of the CPU and Mac builds;
#   auto        the adaptive governor of F7 (the notebook case), not the
#               default.
FULL = "full"
OPTIMIZED = "optimizado"
OFF = "sin-efectos"
MODES = (FULL, OPTIMIZED, OFF, AUTO)
DEFAULT_MODE = FULL
# Other ways of asking for the mode without the effects.
OFF_ALIASES = ("off", "sin efectos", "sin_efectos", "ninguno", "none")
# Stages that the optimized mode never runs: the heavy post-processing.
OPTIMIZED_SKIPS = (GLOW, LIGHTS, HEAT, TRAIL, HISTOGRAM, "crt", "var",
                   "confetti")
# What a mode draws. `stage` is the level name of LEVELS (None for auto:
# the governor's level decides) and `scale` the index of QUALITY_SCALES.
Mode = collections.namedtuple(
    "Mode", "name stage scale governor crowd punch particles skips")



def stages(level=None):
    """Stages of a level ('media' if unknown or missing)."""
    return LEVELS.get(level or config.Gpu.QUALITY, LEVELS["media"])


def known(level):
    """True if the level exists."""
    return level in LEVELS


def downgrade(level):
    """The next cheaper level (the same one if it is already the lowest)."""
    order = config.Gpu.QUALITIES
    index = order.index(level) if level in order else 1
    return order[max(index - 1, 0)]


def level_of(value, default=MIN_LEVEL):
    """Level index (0..3) of a command line value; 'auto' -> `default`."""
    if value is None or str(value) == AUTO:
        return default
    try:
        index = int(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_LEVEL, min(index, len(config.Gpu.QUALITY_LEVELS) - 1))


def label(index):
    """Name of a level: 'Q0', 'Q1', 'Q2' or 'Q3'."""
    return config.Gpu.QUALITY_LEVELS[index]


def scale(index):
    """Image divisor of a level (1 = full resolution)."""
    return config.Gpu.QUALITY_SCALES[index]


def skipped(index):
    """Stages this level leaves out."""
    return SKIPPED.get(index, ())


# --- F11: quality modes ------------------------------------------------
def mode_of(value):
    """Quality mode of a value; 'full' if it is missing or unknown."""
    if isinstance(value, str) and value.strip().lower() in OFF_ALIASES:
        return OFF
    return value if value in MODES else DEFAULT_MODE


def name_of(mode):
    """Readable name of a mode (the overlay and the menu): FULL, ..."""
    return config.Gpu.MODE_NAMES[mode_of(mode)]


def next_mode(mode):
    """The mode that follows in the cycle: full -> optimizado ->
    "sin-efectos" -> auto (F10)."""
    mode = mode_of(mode)
    return MODES[(MODES.index(mode) + 1) % len(MODES)]


def policy(mode=None, level=MIN_LEVEL):
    """What the mode draws; `level` is the governor level (auto only)."""
    mode = mode_of(mode)
    gpu = config.Gpu
    if mode == OFF:
        return Mode(mode, None, MIN_LEVEL, False, False, gpu.MODE_PUNCH[OFF],
                    gpu.MODE_PARTICLES[OFF], tuple(SKIPPED[max(SKIPPED)]))
    if mode == OPTIMIZED:
        return _optimized(mode)
    if mode == FULL:
        return Mode(mode, gpu.MODE_STAGE[FULL], MIN_LEVEL, False, True,
                    gpu.MODE_PUNCH[FULL], gpu.MODE_PARTICLES[FULL], ())
    return Mode(mode, None, level, True, False, gpu.MODE_PUNCH[AUTO],
                gpu.MODE_PARTICLES[AUTO], skipped(level))


def _optimized(mode):
    """The cheap mode: one stage, full resolution, no crowd, no governor."""
    gpu = config.Gpu
    return Mode(mode, gpu.MODE_STAGE[OPTIMIZED], gpu.OPTIMIZED_LEVEL,
                False, False, gpu.MODE_PUNCH[OPTIMIZED],
                gpu.MODE_PARTICLES[OPTIMIZED], OPTIMIZED_SKIPS)


class QualityGovernor:
    """Moves the CPU quality level with the frame time (a pure state machine).

    `frame_ms` is the time of the effects chain (the expensive part of the
    frame). The mean of the last QUALITY_AVG_FRAMES decides: above
    QUALITY_DOWN_MS it goes one level down at once; below QUALITY_UP_MS for
    QUALITY_UP_FRAMES frames it goes one level up. Two changes are always
    QUALITY_MIN_SECONDS apart.
    """

    def __init__(self, quality=AUTO, backend=CPU, level=MIN_LEVEL):
        self.quality = AUTO if quality is None else str(quality)
        self.enabled = (self.quality == AUTO and backend == CPU)
        self.level = level_of(self.quality, level)
        self.samples = collections.deque(
            maxlen=config.Gpu.QUALITY_AVG_FRAMES)
        self.fast = 0                 # frames below QUALITY_UP_MS in a row
        self.wait = NEVER             # s left before another change
        self.changes = 0

    def frame(self, frame_ms, dt):
        """One frame; returns the level that has to be used from now on."""
        self.wait = max(NEVER, self.wait - dt)
        if not self.enabled:
            return self.level
        self.samples.append(frame_ms)
        return self._decide()

    def _decide(self):
        """Applies the hysteresis; a change is what `changes` counts."""
        if self.wait > NEVER or len(self.samples) < self.samples.maxlen:
            return self.level
        mean = sum(self.samples) / len(self.samples)
        if mean > config.Gpu.QUALITY_DOWN_MS:
            return self._move(ONE)
        if mean < config.Gpu.QUALITY_UP_MS:
            self.fast += ONE
            if self.fast >= config.Gpu.QUALITY_UP_FRAMES:
                return self._move(-ONE)
        else:
            self.fast = 0
        return self.level

    def _move(self, delta):
        """Changes the level by `delta`, respecting the range and the wait."""
        last = len(config.Gpu.QUALITY_LEVELS) - 1
        new = max(MIN_LEVEL, min(last, self.level + delta))
        self.fast = 0
        if new == self.level:
            return self.level
        self.level = new
        self.wait = config.Gpu.QUALITY_MIN_SECONDS
        self.changes += ONE
        self.samples.clear()
        return self.level

    def reset(self):
        """Forgets the samples (new match, backend change)."""
        self.samples.clear()
        self.fast = 0
        self.wait = NEVER

