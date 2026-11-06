"""Quality levels of the effects chain: which stages are drawn.

`baja` keeps only the sparks (the cheapest), `media` adds the glow and the
spotlights and `alta` adds the heat waves, the trail and the contrast
stretch. The game starts with config.Gpu.QUALITY.
"""
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
