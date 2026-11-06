"""Post-processing chain of the match: pygame in, pygame out.

`PostFx.begin` hands the screen (or an offscreen copy when the chain runs)
to whoever draws the world; `PostFx.finish` takes that image, runs the
stages on the GPU (or on the CPU when there is no CUDA) and puts the result
on the screen. The rest of the interface (HUD, menus) is never touched.

The chain is presentation only: it reads the match state, never changes it.
"""
import math
import time

import numpy as np
import pygame

from fdc import config
from fdc import protocol
from fdc.gpu import backend
from fdc.gpu import cpu_ref
from fdc.gpu import effects_state
from fdc.gpu import exposure
from fdc.gpu import heatmap
from fdc.gpu import metrics as gpu_metrics
from fdc.gpu import particles
from fdc.gpu import quality
from fdc.gpu import replay

MS_PER_S = 1000.0       # seconds to milliseconds
LIGHT_FIELDS = 7        # x, y, radius, power, r, g, b
CLIP = 0.005            # fraction of pixels left outside the contrast range
LIGHT_POWER = 0.8       # 0-1: strength of the spotlight of a power
TOUCH_SPEED = 120.0     # px/s: from this impact a touch makes sparks
GOAL_SPARKS = 40        # sparks of a goal
BOMB_SPARKS = 26        # sparks of an explosion
TOUCH_SPARKS = 10       # sparks of a kick or a bounce
COORD_COLUMNS = 3                   # x, y and radius of a light
SPARK_COLOUR = (1.0, 0.85, 0.55)     # rgb of the sparks
FIRE_COLOUR = (1.0, 0.45, 0.15)      # rgb of the fire power
ICE_COLOUR = (0.55, 0.85, 1.0)       # rgb of the ice power
# Readable name of each effect for the overlay (line 4).
_EFFECT_NAMES = {"ice": "hielo", "blackout": "apagón", "confusion": "confusión",
                 "fire": "fuego", "night": "noche", "shock": "onda",
                 "trail": "estela", "crt": "repetición", "var": "VAR"}


class PostFx:
    """The effects chain: surface in, surface out, with its own metrics."""

    def __init__(self, options, size):
        self.mode = "cpu"
        self.enabled = _wanted(options)
        self.level, self.force_cpu = _choices(options)
        self.ops, self.error = None, None
        self.device = "CPU"          # set again when the backend starts
        self._init_buffers(size)
        self._init_effects()
        self._init_demo(options)

    def _init_buffers(self, size):
        """Metrics, particles, target surface and the effect buffers."""
        self.metrics = gpu_metrics.Metrics()
        self.particles = particles.Field()
        self.target = pygame.Surface(size).convert()
        self.state = None
        self.trail = None
        self.phase = 0.0
        self.lights = _no_lights()

    def _init_demo(self, options):
        """F7 state: adaptive quality, demo forcing and the overlay."""
        self.options = options
        self.quality_option = getattr(options, "quality", None)
        self.governor = quality.QualityGovernor(self.quality_option, "cpu")
        self.px = 1.0               # scale of the coordinates (Q1..Q3)
        self.skips = ()             # stages the CPU level leaves out
        self.forced = {}            # FxParams forced by the demo director
        self.last_ms = {}           # last fx ms of each backend (overlay)

    def _init_effects(self):
        """State of the effects (viewer, night, clock, trail, replay, heat)."""
        self.viewer = None          # 0, 1 or None on a shared screen
        self.night = False          # local option (key N)
        self.clock = 0.0            # s of the chain (ages of the effects)
        self.events = []            # event driven effects (goal wave)
        self.fx = effects_state.FxParams()
        self.exposure = exposure.AutoExposure()
        self.trail_gate = effects_state.TrailGate()
        self.history = replay.StateHistory()   # saved states (F5)
        self.player = None          # replay or VAR being drawn (F5)
        self.frame_no = 0           # frames drawn (grain of the CRT)
        self.force_var = False      # tests/demo: review every goal
        self.heat = heatmap.HeatmapRecorder()  # heat map of the match (F6)

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
        self.device = (backend.device_name() if self.mode == "gpu" else "CPU")
        self._reset_backend()

    def _reset_backend(self):
        """Governor, buffers and demo rule for the backend just built."""
        self.governor = quality.QualityGovernor(self.quality_option, self.mode)
        self._forget_device()
        forced = self.quality_option not in (None, quality.AUTO)
        # The demo is a measurement: it keeps the level the user asked for.
        # Without --quality the CPU may still adapt, so the university demo
        # stays fluid on a notebook without NVIDIA.
        if getattr(self.options, "demo", False) and forced:
            self.governor.enabled = False

    def _forget_device(self):
        """New backend: its buffers are empty, the heat grid must restart."""
        self.heat.started = False
        self.heat.dirty = False

    def begin(self, screen, state):
        """Surface where the world has to be drawn this frame."""
        self.state = state
        if not self.enabled:
            return screen
        if self.ops is None:
            self.start()
            if not self.enabled:
                return screen
        self.history.feed(state, self.clock)
        return self.target

    def view_state(self, state):
        """State the world is drawn with: the replay one while it runs."""
        if self.player is None:
            return state
        return self.player.state_at(self.clock)

    def replay_mode(self):
        """None, replay.REPLAY_KIND or replay.VAR_KIND (what is on screen)."""
        return None if self.player is None else self.player.kind

    def replay_stage(self):
        """Stage of the VAR (replay.REVIEW / CONFIRMED), or None."""
        if self.player is None or self.player.kind != replay.VAR_KIND:
            return None
        return self.player.stage(self.clock)

    def replay_zoom(self):
        """(x, y) the VAR zoom is centred on, or None."""
        if self.player is None or self.player.kind != replay.VAR_KIND:
            return None
        return replay.ball_xy(self.player.state_at(self.clock))

    def heat_overlay(self, surface, channel):
        """Draws the heat map of a channel over the surface (F6)."""
        if channel is None or self.ops is None:
            return False
        image = to_array(surface)
        to_screen(self.heat.render(self.ops, image, channel), surface)
        return True

    def finish(self, screen, dt):
        """Runs the chain and leaves the result on `screen`."""
        if not self.enabled:
            self.metrics.skip()
            return
        start = time.perf_counter()
        image = to_array(self.target)
        result = self._scaled(image, dt)
        ms = (time.perf_counter() - start) * MS_PER_S
        self.metrics.frame(ms)
        self.last_ms[self.mode] = ms
        self.governor.frame(ms, dt)
        to_screen(result, screen)

    def _scaled(self, image, dt):
        """Q1..Q3: the chain runs on a smaller image and it is stretched."""
        divisor = quality.scale(self.level_index())
        if divisor <= 1:
            return self._chain(image, dt)
        self.px = 1.0 / divisor
        try:
            small = self._chain(image[::divisor, ::divisor], dt)
        finally:
            self.px = 1.0
        return _stretch(small, image.shape)

    def level_index(self):
        """0 with the GPU; with the CPU, what the governor decided."""
        return 0 if self.mode != quality.CPU else self.governor.level

    def quality_label(self):
        """'Q0'..'Q3', for the overlay and the CSV."""
        return quality.label(self.level_index())

    def toggle(self):
        """Switches between the GPU and the numpy version (F4 key)."""
        if not self.enabled:
            return self.mode
        self.force_cpu = self.mode == "gpu"
        self.ops = _make_ops(self.force_cpu)
        self.mode = "gpu" if isinstance(self.ops, backend.Gpu) else "cpu"
        self.device = (backend.device_name() if self.mode == "gpu" else "CPU")
        self._forget_device()
        self.metrics.clear()
        return self.mode

    def clear(self):
        """New match: nothing left (sparks, trail, replay, heat map)."""
        self.particles.clear()
        self.trail = None
        self.lights = _no_lights()
        self.events = []
        self.fx = effects_state.FxParams()
        self.exposure.reset()
        self.trail_gate.reset()
        self.history.clear()
        self.player = None
        self.heat.clear()

    # ---------------------------------------------------------------- events
    def event(self, msg):
        """Sparks for the events the simulation sends (cosmetic only)."""
        kind = msg.get("type")
        x, y = msg.get("x"), msg.get("y")
        if kind == protocol.EV_GOAL:
            self._goal_event(msg)
        elif kind == protocol.EV_BOMB_EXPLODE:
            self.particles.spawn(x or 0.0, y or 0.0, FIRE_COLOUR,
                                 BOMB_SPARKS)
        elif kind == protocol.EV_TOUCH:
            self._touch(x, y, msg.get("speed") or 0.0)

    def _goal_event(self, msg):
        """Sparks, shock wave and replay of a goal."""
        x, y = msg.get("x") or 0.0, msg.get("y") or 0.0
        self.particles.spawn(x, y, SPARK_COLOUR, GOAL_SPARKS)
        self.events.append(effects_state.EventFx(
            effects_state.SHOCK_KIND, x, y, self.clock,
            config.Gpu.SHOCK_DURATION))
        self._start_replay(msg)

    def _start_replay(self, msg):
        """Replay of a goal, or the VAR when it went in by very little."""
        frames = self.history.frames(config.Gpu.REPLAY_DURATION)
        if not frames:
            return
        ball = (msg.get("x"), msg.get("y"))
        close = self.history.is_close(msg.get("side"), ball)
        if close or self.force_var:
            self.player = replay.VarPlayer(frames[-1][1], self.clock)
        else:
            self.player = replay.ReplayPlayer(frames, self.clock,
                                              config.Gpu.REPLAY_DURATION)

    def _touch(self, x, y, speed):
        """Sparks of a kick or a bounce (only if it was strong)."""
        if speed > TOUCH_SPEED:
            self.particles.spawn(x, y, SPARK_COLOUR, TOUCH_SPARKS)

    # ----------------------------------------------------------------- chain
    def _chain(self, image, dt):
        self.clock += dt
        self.frame_no += 1
        self.skips = quality.skipped(self.level_index())
        self.particles.update(dt)
        self._record_heat()
        if self._advance_player():
            return self._screened(image)      # replay or VAR: only its look
        self.fx = self._derive()
        self.phase += config.Gpu.HEAT_SPEED * dt
        return self._night(self._stages(image, dt))

    def _stages(self, image, dt):
        """The stages of the fixed order (spec 5.3) plus the extras."""
        stages = quality.stages(self.level)
        out = image
        if quality.GLOW in stages and quality.GLOW not in self.skips:
            out = self._timed("glow", self._glow, image)
        out = self._timed("particles", self._sparks, out)
        out = self._timed("lights", self._lights, out)
        out = self._powers(out, dt)
        return self._extras(out, dt, stages)

    def _advance_player(self):
        """Drops the replay when it is over; True while one is drawn."""
        if self.player is not None and self.player.finished(self.clock):
            self.player = None
        return self.player is not None

    def _record_heat(self):
        """Feeds the heat map of the match (F6)."""
        self.heat.feed(self.state)
        if self.ops is not None and self.heat.due():
            self.heat.flush(self.ops)

    def _screened(self, image):
        """Replay or VAR: the chain ends with the look of the screen."""
        if self.player.kind == replay.VAR_KIND:
            if "crt" in self.skips:
                return image
            return self._timed("var", self._var_look, image)
        if "crt" in self.skips:
            return image
        return self._timed("crt", self._crt, image)

    def _crt(self, image):
        """Old television of the replay (k_crt)."""
        gpu = config.Gpu
        return self.ops.crt(image, self.frame_no, gpu.CRT_AMOUNT,
                            gpu.CRT_SCAN, gpu.CRT_VIGNETTE, gpu.CRT_NOISE,
                            gpu.CRT_ROWS, gpu.CRT_TINT)

    def _var_look(self, image):
        """VAR: gray image with the bright edges in green (spec 5.4)."""
        gpu = config.Gpu
        edges = self.ops.sobel(self.ops.to_gray(image))
        norm = self.ops.sobel_normalize(edges, float(edges.max() or 1.0))
        tinted = self.ops.tint(norm, gpu.VAR_TINT)
        return self.ops.edge_glow(self.ops.gray(image), tinted, gpu.VAR_EDGES)

    def _derive(self):
        """FxParams of this frame (pure rules, see effects_state)."""
        self.events = [fx for fx in self.events if fx.alive(self.clock)]
        fx = effects_state.derive(self.state, self.viewer, self.clock,
                                  self.events, night=self.night)
        return self._forced(fx) if self.forced else fx

    def _forced(self, fx):
        """Demo: the director forces the parameters of the segment."""
        for name in ("ice", "confusion", "trail", "crt"):
            if name in self.forced:
                setattr(fx, name, self.forced[name])
        if "blackout" in self.forced:
            fx.blackout = self.forced["blackout"](self.state)
        if "fire" in self.forced:
            fx.fire = self.forced["fire"](self.state)
        return fx

    def force(self, **params):
        """Forces (or clears, with `clear=True`) the params of the demo."""
        if params.pop("clear", False):
            self.forced = {}
            return
        self.forced = params

    def begin_replay(self, var=False):
        """Starts a replay (or the VAR) of the last seconds of real play."""
        frames = self.history.frames(config.Gpu.REPLAY_DURATION)
        if not frames:
            return False
        if var:
            self.player = replay.VarPlayer(frames[-1][1], self.clock)
        else:
            self.player = replay.ReplayPlayer(frames, self.clock,
                                              config.Gpu.REPLAY_DURATION)
        return True

    def active_effects(self):
        """Readable list of the effects on this frame (overlay line 4)."""
        names = []
        for name in ("ice", "blackout", "confusion", "fire", "night",
                     "shock", "trail", "crt", "var"):
            value = getattr(self.fx, name, None)
            if value not in (None, (), 0, 0.0, False):
                names.append(_EFFECT_NAMES.get(name, name))
        return " + ".join(names) if names else "ninguno"

    def other_measurement(self):
        """Line 6 of the overlay: the last fx ms of the other backend."""
        mode = "cpu" if self.mode == "gpu" else "gpu"
        ms = self.last_ms.get(mode)
        if not ms:
            return None
        speedup = self.last_ms.get(self.mode, 0.0)
        ratio = f" (x{speedup / ms:.0f} vs GPU)" if mode == "cpu" else ""
        return f"{mode.upper()} fx {ms:.1f} ms{ratio}"

    def _powers(self, image, dt):
        """F3/F4 stages, in the fixed order of the spec (5.3)."""
        out = self._ball_trail(image, dt)
        out = self._shock(out)
        out = self._fire(out)
        out = self._confusion(out)
        out = self._ice(out)
        return self._blackout(out)

    def _ball_trail(self, image, dt):
        """TRAIL: bright pixels of the fast ball stay a moment (maximum)."""
        speed = effects_state.ball_speed(self.state or {})
        if quality.TRAIL in self.skips or not self.trail_gate.update(speed, dt):
            self.trail = None
            return image
        if self.trail is None or self.trail.shape != image.shape:
            self.trail = image.copy()
            return image
        out = self._timed("trail", self.ops.trail_blend, image, self.trail,
                          config.Gpu.TRAIL_DECAY)
        self.trail = image.copy()      # prev <- cur, as the spec asks
        return out

    def _shock(self, image):
        """SHOCK: the ring of a goal grows and warps what it crosses."""
        if self.fx.shock is None:
            return image
        x, y, age = self.fx.shock
        gpu = config.Gpu
        radius = gpu.SHOCK_RADIUS * age
        amp = gpu.SHOCK_AMP * (1.0 - age / gpu.SHOCK_DURATION)
        return self._timed("shock", self.ops.ripple_ring, image,
                           x * self.px, y * self.px, radius * self.px,
                           gpu.SHOCK_WIDTH * self.px, amp)

    def _fire(self, image):
        """FIRE: hot air around the ball."""
        if self.fx.fire is None:
            return image
        x, y, radius = self.fx.fire
        return self._timed("fire", self.ops.heat_distort, image,
                           x * self.px, y * self.px, radius * self.px,
                           self.clock, config.Gpu.FIRE_AMP)

    def _confusion(self, image):
        """CONFUSION: inverted and slowly turning image."""
        if self.fx.confusion <= 0:
            return image
        out = self._timed("confusion", self.ops.invert, image)
        gpu = config.Gpu
        angle = (math.radians(gpu.CONFUSION_MAX_DEG) * self.fx.confusion
                 * math.sin(gpu.CONFUSION_SPEED * self.clock))
        return self._timed("confusion_rot", self.ops.rotate, out, angle)

    def _ice(self, image):
        """ICE: bright edges, then a blue tint weighted by the strength."""
        if self.fx.ice <= 0:
            return image
        gpu = config.Gpu
        out = self._timed("ice_edges", self._ice_edges, image)
        tinted = self.ops.tint(out, gpu.ICE_TINT)
        return self._timed("ice_tint", self.ops.mix, out, tinted,
                           gpu.ICE_STRENGTH * self.fx.ice)

    def _ice_edges(self, image):
        """Edge glow of the ice (sobel normalised over the whole image)."""
        edges = self.ops.sobel(self.ops.to_gray(image))
        norm = self.ops.sobel_normalize(edges, float(edges.max() or 1.0))
        return self.ops.edge_glow(image, norm,
                                  config.Gpu.ICE_EDGES * self.fx.ice)

    def _blackout(self, image):
        """BLACKOUT: only the light around the affected player stays."""
        if not self.fx.blackout:
            return image
        lights = effects_state.light_array(self.fx.blackout,
                                           config.Gpu.BLACKOUT_RADIUS, 1.0)
        return self._timed("blackout", self.ops.spotlights, image,
                           self._scaled_lights(lights),
                           config.Gpu.BLACKOUT_AMBIENT,
                           config.Gpu.BLACKOUT_TINT)

    def _night(self, image):
        """NIGHT: six spotlights and auto exposure (gain of the last frame)."""
        if not self.fx.night:
            self.exposure.reset()
            return image
        gpu = config.Gpu
        lights = self._scaled_lights(effects_state.night_lights())
        out = self._timed("night", self.ops.spotlights, image, lights,
                          gpu.NIGHT_AMBIENT, gpu.NIGHT_TINT)
        if self.exposure.gain != 1.0:
            out = self._timed("exposure", self.ops.gain, out,
                              self.exposure.gain)
        mean = self.ops.luma_stats(out)[0]
        self.exposure.update(mean)      # it is applied on the next frame
        return out

    def _extras(self, image, dt, stages):
        """The expensive stages (only in the 'alta' level)."""
        del dt  # the trail moved to `_powers` (F4)
        out = image
        if quality.HEAT in stages and quality.HEAT not in self.skips:
            out = self._timed("heat", self._heat, out)
        if (quality.HISTOGRAM in stages
                and quality.HISTOGRAM not in self.skips):
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
        return self.ops.particles(image, self._scaled_points(pos), col,
                                  config.Gpu.PARTICLE_GAIN)

    def _lights(self, image):
        table = self._scaled_lights(self._light_table())
        if len(table) == 0:
            return image
        return self.ops.lights(image, table, config.Gpu.LIGHT_GAIN)

    def _heat(self, image):
        gpu = config.Gpu
        return self.ops.heat(image, self.phase, gpu.HEAT_AMP, gpu.HEAT_PERIOD)

    def _trail(self, image, dt):
        """Kept for the F2 API: the F4 trail is `_ball_trail`."""
        del dt
        return self._ball_trail(image, config.Gpu.TRAIL_MIN_SPEED)

    def _contrast(self, image):
        hist = self.ops.histogram(image)
        low, high = _levels(hist, image.size)
        return self.ops.stretch(image, low, high) if high > low else image

    def _light_table(self):
        """Soft glow of the freeze powers (x, y, radius, power, r, g, b)."""
        rows = []
        state = self.state or {}
        players = state.get("players") or []
        for effect in state.get("effects") or []:
            row = _power_light(effect, players)
            if row is not None:
                rows.append(row)
        return (np.array(rows, np.float32) if rows
                else _no_lights())

    def _scaled_lights(self, table):
        """Light table with the coordinates and radii of the small image."""
        if self.px == 1.0:
            return table
        scaled = np.array(table, np.float32)
        if scaled.size == 0:
            return table
        scaled[:, :COORD_COLUMNS] *= self.px
        return scaled

    def _scaled_points(self, points):
        """Particle positions in the coordinates of the small image."""
        return points if self.px == 1.0 else points * self.px

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
        data["quality_level"] = self.quality_label()
        data["active"] = self.active_effects()
        data["other"] = self.other_measurement()
        data["gpu"] = self.device
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


def _stretch(image, shape):
    """Stretches a small RGB image to `shape` (bilinear, through pygame)."""
    small = pygame.surfarray.make_surface(np.transpose(image, (1, 0, 2)))
    big = pygame.transform.smoothscale(small, (shape[1], shape[0]))
    return np.transpose(pygame.surfarray.array3d(big), (1, 0, 2))


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


def _power_light(effect, players):
    """Soft glow of a freeze power, or None if it is not one."""
    if effect.get("prop") != effects_state.ICE_PROP:
        return None
    for index, player in enumerate(players):
        if _targets_player(effect, index):
            return (player["x"], player["y"], config.Gpu.FREEZE_RADIUS,
                    LIGHT_POWER, ICE_COLOUR[0], ICE_COLOUR[1], ICE_COLOUR[2])
    return None


def _targets_player(effect, index):
    """True if the effect belongs to the player at `index`."""
    return effect.get("target") == f"p{index}"
