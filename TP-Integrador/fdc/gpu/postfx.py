"""Post-processing chain of the match: pygame in, pygame out.

`PostFx.begin` hands the screen (or an offscreen copy when the chain runs)
to whoever draws the world; `PostFx.finish` takes that image, runs the
stages on the GPU (or on the CPU when there is no CUDA) and puts the result
on the screen. The rest of the interface (HUD, menus) is never touched.

The chain is presentation only: it reads the match state, never changes it.
"""
import time

import numpy as np
import pygame

from fdc import config
from fdc import protocol
from fdc.gpu import backend
from fdc.gpu import cpu_ref
from fdc.gpu import metrics as gpu_metrics
from fdc.gpu import particles
from fdc.gpu import quality

MS_PER_S = 1000.0       # seconds to milliseconds
LIGHT_FIELDS = 7        # x, y, radius, power, r, g, b
CLIP = 0.005            # fraction of pixels left outside the contrast range
LIGHT_POWER = 0.8       # 0-1: strength of the spotlight of a power
TOUCH_SPEED = 120.0     # px/s: from this impact a touch makes sparks
GOAL_SPARKS = 40        # sparks of a goal
BOMB_SPARKS = 26        # sparks of an explosion
TOUCH_SPARKS = 10       # sparks of a kick or a bounce
SPARK_COLOUR = (1.0, 0.85, 0.55)     # rgb of the sparks
FIRE_COLOUR = (1.0, 0.45, 0.15)      # rgb of the fire power
ICE_COLOUR = (0.55, 0.85, 1.0)       # rgb of the ice power


class PostFx:
    """The effects chain: surface in, surface out, with its own metrics."""

    def __init__(self, options, size):
        self.mode = "cpu"
        self.enabled = _wanted(options)
        self.level, self.force_cpu = _choices(options)
        self.ops = None
        self.error = None
        self.metrics = gpu_metrics.Metrics()
        self.particles = particles.Field()
        self.target = pygame.Surface(size).convert()
        self.state = None
        self.trail = None
        self.phase = 0.0
        self.lights = _no_lights()

    # ------------------------------------------------------------- lifecycle
    def start(self):
        """Builds the backend (GPU if it works, CPU otherwise)."""
        if not self.enabled:
            return
        try:
            self.ops = _make_ops(self.force_cpu)
            self.mode = "gpu" if isinstance(self.ops, backend.Gpu) else "cpu"
        except Exception as exc:      # pylint: disable=broad-except
            self.error = str(exc)
            self.enabled = False

    def begin(self, screen, state):
        """Surface where the world has to be drawn this frame."""
        self.state = state
        if not self.enabled:
            return screen
        if self.ops is None:
            self.start()
            if not self.enabled:
                return screen
        return self.target

    def finish(self, screen, dt):
        """Runs the chain and leaves the result on `screen`."""
        if not self.enabled:
            self.metrics.skip()
            return
        start = time.perf_counter()
        image = to_array(self.target)
        result = self._chain(image, dt)
        self.metrics.frame((time.perf_counter() - start) * MS_PER_S)
        to_screen(result, screen)

    def clear(self):
        """New match: no sparks, no trail, no lights."""
        self.particles.clear()
        self.trail = None
        self.lights = _no_lights()

    # ---------------------------------------------------------------- events
    def event(self, msg):
        """Sparks for the events the simulation sends (cosmetic only)."""
        kind = msg.get("type")
        x, y = msg.get("x"), msg.get("y")
        if kind == protocol.EV_GOAL:
            self.particles.spawn(x or 0.0, y or 0.0, SPARK_COLOUR,
                                 GOAL_SPARKS)
        elif kind == protocol.EV_BOMB_EXPLODE:
            self.particles.spawn(x or 0.0, y or 0.0, FIRE_COLOUR,
                                 BOMB_SPARKS)
        elif kind == protocol.EV_TOUCH:
            self._touch(x, y, msg.get("speed") or 0.0)

    def _touch(self, x, y, speed):
        """Sparks of a kick or a bounce (only if it was strong)."""
        if speed > TOUCH_SPEED:
            self.particles.spawn(x, y, SPARK_COLOUR, TOUCH_SPARKS)

    # ----------------------------------------------------------------- chain
    def _chain(self, image, dt):
        self.particles.update(dt)
        self.phase += config.Gpu.HEAT_SPEED * dt
        stages = quality.stages(self.level)
        out = image
        if quality.GLOW in stages:
            out = self._timed("glow", self._glow, image)
        out = self._timed("particles", self._sparks, out)
        out = self._timed("lights", self._lights, out)
        return self._extras(out, dt, stages)

    def _extras(self, image, dt, stages):
        """The expensive stages (only in the 'alta' level)."""
        out = image
        if quality.HEAT in stages:
            out = self._timed("heat", self._heat, out)
        if quality.TRAIL in stages:
            out = self._timed("trail", self._trail, out, dt)
        if quality.HISTOGRAM in stages:
            out = self._timed("histogram", self._contrast, out)
        return out

    def _glow(self, image):
        gpu = config.Gpu
        params = (gpu.EXPOSURE, gpu.GAMMA, gpu.VIGNETTE, gpu.GLOW_STRENGTH)
        return self.ops.glow_composite(image, gpu.GLOW_THRESHOLD,
                                       gpu.GLOW_RADIUS, gpu.GLOW_PASSES,
                                       params)

    def _sparks(self, image):
        pos, col = self.particles.live()
        if len(pos) == 0:
            return image
        return self.ops.particles(image, pos, col, config.Gpu.PARTICLE_GAIN)

    def _lights(self, image):
        table = self._light_table()
        if len(table) == 0:
            return image
        return self.ops.lights(image, table, config.Gpu.LIGHT_GAIN)

    def _heat(self, image):
        gpu = config.Gpu
        return self.ops.heat(image, self.phase, gpu.HEAT_AMP, gpu.HEAT_PERIOD)

    def _trail(self, image, dt):
        if self.trail is None or self.trail.shape != image.shape:
            self.trail = image.copy()
            return image
        out, self.trail = self.ops.trail(image, self.trail,
                                         config.Gpu.TRAIL_ALPHA)
        return out

    def _contrast(self, image):
        hist = self.ops.histogram(image)
        low, high = _levels(hist, image.size)
        return self.ops.stretch(image, low, high) if high > low else image

    def _light_table(self):
        """Spotlights of the powers active right now (x, y, radius, ...)."""
        rows = []
        state = self.state or {}
        effects = (state.get("powers") or {}).get("effects") or []
        for effect in effects:
            row = _power_light(effect, state)
            if row is not None:
                rows.append(row)
        return (np.array(rows, np.float32) if rows
                else _no_lights())

    def _timed(self, name, fn, *args):
        start = time.perf_counter()
        out = fn(*args)
        self.metrics.add(name, (time.perf_counter() - start) * MS_PER_S)
        return out

    def summary(self):
        """Numbers for the overlay and the measurement script."""
        data = self.metrics.summary()
        data["mode"] = self.mode if self.enabled else "off"
        data["quality"] = self.level
        data["gpu"] = backend.device_name() if self.mode == "gpu" else "CPU"
        return data


def _choices(options):
    """Quality level and whether the numpy version was forced."""
    return (getattr(options, "gpu_quality", None) or config.Gpu.QUALITY,
            bool(getattr(options, "force_cpu", False)))


def _wanted(options):
    """True if the effects are enabled and the command line allows them."""
    return bool(config.Gpu.ENABLED) and not getattr(options, "no_gpu", False)


def _no_lights():
    """Empty table of spotlights (x, y, radius, power, r, g, b)."""
    return np.zeros((0, LIGHT_FIELDS), np.float32)


def _make_ops(force_cpu=False):
    """GPU if PyCUDA compiles the kernels here, numpy otherwise."""
    if force_cpu:
        return cpu_ref.Cpu()
    try:
        return backend.Gpu()
    except Exception:              # pylint: disable=broad-except
        return cpu_ref.Cpu()


def to_array(surface):
    """pygame surface -> numpy RGB (h, w, 3)."""
    return np.transpose(pygame.surfarray.array3d(surface), (1, 0, 2))


def to_screen(image, surface):
    """numpy RGB (h, w, 3) -> pygame surface."""
    pygame.surfarray.blit_array(surface, np.transpose(image, (1, 0, 2)))


def _levels(hist, total, clip=None):
    """Low and high levels that leave `clip` of the pixels outside."""
    if total <= 0:
        return 0.0, 0.0
    limit = total * (clip or CLIP)
    return _first(hist, limit), _last(hist, limit)


def _first(hist, limit):
    """First level where the accumulated count passes `limit`."""
    acc = 0
    for value, count in enumerate(hist):
        acc += count
        if acc > limit:
            return float(value)
    return 0.0


def _last(hist, limit):
    """Last level where the count from the top passes `limit`."""
    acc = 0
    for value in range(len(hist) - 1, -1, -1):
        acc += hist[value]
        if acc > limit:
            return float(value)
    return float(len(hist) - 1)


def _power_light(effect, state):
    """One spotlight row for an effect, or None if it is not a light."""
    power = effect.get("power")
    if power not in ("freeze_self", "freeze_rival", "blackout", "fire"):
        return None
    colour = FIRE_COLOUR if power == "fire" else (
        ICE_COLOUR if power.startswith("freeze") else SPARK_COLOUR)
    for player in state.get("players") or []:
        if _targets_player(effect, player):
            return (player["x"], player["y"], config.Gpu.FREEZE_RADIUS,
                    LIGHT_POWER, colour[0], colour[1], colour[2])
    return None


def _targets_player(effect, player):
    """True if the effect belongs to that player (or to nobody)."""
    target = effect.get("target") or ""
    if target.startswith("p"):
        return target == f"p{player['idx']}"
    return effect.get("power") in ("blackout", "fire")
