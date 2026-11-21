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
from fdc.gpu import celebration
from fdc.gpu import crowd
from fdc.gpu import cpu_ref
from fdc.gpu import effects_state
from fdc.gpu import exposure
from fdc.gpu import five_steps
from fdc.gpu import heatmap
from fdc.gpu import metrics as gpu_metrics
from fdc.gpu import particles
from fdc.gpu import quality
from fdc.gpu import replay

MS_PER_S = 1000.0       # seconds to milliseconds
CHANNELS = 3            # rgb (the images of the chain)
WHITE = 255             # channel value of the flash
LIGHT_FIELDS = 4        # x, y, radius, power of the ice focus
CLIP = 0.005            # fraction of pixels left outside the contrast range
LIGHT_AMBIENT = 1.0     # 0-1: light far from the focus (the pixel unchanged)
LIGHT_TINT = (1.0, 1.0, 1.0)   # rgb: the focus brightens, it does not tint
NO_LIGHT_CAP = 0.0      # spotlights without a top: the classic sum
# The night sky keeps the ambient of the lamps; this light blue multiplier
# takes it to a night blue (a flat gray would lose the sky of the palette).
NIGHT_SKY = (0.55, 0.62, 0.80)
TOUCH_SPEED = 120.0     # px/s: from this impact a touch makes sparks
GOAL_SPARKS = 40        # sparks of a goal
BOMB_SPARKS = 26        # sparks of an explosion
TOUCH_SPARKS = 10       # sparks of a kick or a bounce
SPARK_COLOUR = (1.0, 0.85, 0.55)     # rgb of the sparks
FIRE_COLOUR = (1.0, 0.45, 0.15)      # rgb of the fire power
# Embers of a burnt player (the fire power of 1.0.2): small and few, so the
# glow stage never saturates.
EMBER_EVERY = 0.07       # s between two batches over the same player
EMBER_COUNT = 3          # embers of each batch
EMBER_COLOUR = (1.0, 0.30, 0.06)     # rgb of the embers (deep orange)
EMBER_RAISE = 55         # px above the feet where the embers are born
ICE_COLOUR = (0.55, 0.85, 1.0)       # rgb of the ice power
# Readable name of each effect for the overlay (line 4).
_EFFECT_NAMES = {"ice": "hielo", "blackout": "apagón", "confusion": "confusión",
                 "fire": "fuego", "night": "noche", "shock": "onda",
                 "burned": "quemado",
                 "trail": "estela", "crt": "repetición", "var": "VAR"}
_CELEBRATION_NAME = "festejo"   # the party of a goal (F10)
# Glow with a goal or a power, and its vignette: the histogram applies it at the
# end of the chain, so a frame without halo does not pay an extra pass.
SPECTACLE_FX = ("ice", "blackout", "confusion", "fire", "night")
SHOW_VIGNETTE = 0.0     # the glow stage never darkens the corners
# Breathing of the powers (F11): the three numbers the formula needs.
PULSE_ONE = 1.0         # no breathing
PULSE_HALF = 0.5        # the sine goes between -PULSE_HALF and +PULSE_HALF
PULSE_ZERO = 0.0        # an amount of zero means "no breathing"


class PostFx:
  """The effects chain: surface in, surface out, with its own metrics."""

  def __init__(self, options, size):
    self.mode = "cpu"
    self.allowed = _wanted(options)
    self.enabled = self.allowed
    self.force_cpu = bool(getattr(options, "force_cpu", False))
    self.ops, self.error = None, None
    self.reasons = []            # why the GPU was not used (screen)
    self.device = "CPU"          # set again when the backend starts
    self._init_buffers(size)
    self._init_effects()
    self._init_mode(options)
    self.forced = {}            # FxParams forced by the demo director

  def _init_buffers(self, size):
    """Metrics, particles, target surface and the effect buffers."""
    self.metrics = gpu_metrics.Metrics()
    self.particles = particles.Field()
    self.target = pygame.Surface(size).convert()
    self.state = None
    self.trail = None
    self.phase = 0.0
    self.lights = _no_lights()
    self.processed_size = None
    self.probe = five_steps.FiveStepProbe()
    self.probe_active = False

  def _init_mode(self, options):
    """Mode chosen by the player, or the default of the backend."""
    # Without a choice the mode follows the backend (see start()): the
    # chain starts as FULL and then takes the default of the backend.
    chosen = getattr(options, "quality_mode", None)
    self.chosen_mode = chosen is not None
    self.quality_mode = quality.mode_of(chosen)
    # "sin-efectos": the chain stays off (plain pygame render).
    self.enabled = self.allowed and self.quality_mode != quality.OFF

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
    self._init_party()

  def _init_party(self):
    """F10: the celebration of a goal, its paper and the flash."""
    self.celebration = None     # the goal being celebrated
    self.confetti = celebration.ConfettiField()
    self.pending = None         # goal waiting for the replay
    self.white = None           # image of the flash (built once)
    self.ember_acc = 0.0        # s to the next batch of embers (FULL)

  # ------------------------------------------------------------- lifecycle
  def start(self):
    """Builds the backend (GPU if it works, CPU otherwise)."""
    if not self.enabled:
      return
    try:
      self.ops = _make_ops(self.force_cpu, self.reasons)
      self.mode = "gpu" if isinstance(self.ops, backend.Gpu) else "cpu"
    except Exception as exc:      # pylint: disable=broad-except
      self.error = str(exc)
      self.enabled = False
    self.device = (backend.device_name() if self.mode == "gpu" else "CPU")
    backend.log_backend(self.mode, self.device)
    self._apply_default_mode()

  def _apply_default_mode(self):
    """Without a mode chosen by the player: FULL on the GPU, none on
        the CPU.

        It is decided here, when the backend is already known, so a GPU that
        falls back to the CPU ends up with the plain pygame render.
        """
    if not self.chosen_mode:
      self.set_quality_mode(quality.default_for(self.mode))

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

  # ------------------------------------------------------- quality modes
  def quality_mode_name(self):
    """The current mode name for the overlay."""
    return quality.name_of(self.quality_mode if self.allowed else quality.OFF)

  def set_quality_mode(self, mode):
    """Changes the mode (key F10, options menu): returns the new one."""
    self.quality_mode = quality.mode_of(mode)
    self.enabled = self.allowed and self.full_quality()
    if not self.enabled:
      self.clear()
    self.metrics.clear()
    self.processed_size = None
    self.probe.invalidate()
    self._forget_device()
    return self.quality_mode

  def cycle_quality_mode(self):
    """Alternate between the effects chain and the plain render."""
    if not self.allowed:
      return None
    self.chosen_mode = True     # F10 and the menu are a choice
    return self.set_quality_mode(quality.next_mode(self.quality_mode))

  def punch(self):
    """Power effect strength: zero without the chain."""
    return config.Gpu.FULL_PUNCH if self.full_quality() else 0.0

  def full_quality(self):
    """True in FULL: the extra animation of the powers (F11)."""
    return self.quality_mode == quality.FULL

  def _pulse(self, amount):
    """FULL only: the effect breathes (a 0-1 multiplier of its strength)."""
    if amount <= PULSE_ZERO or not self.full_quality():
      return PULSE_ONE
    wave = PULSE_HALF + PULSE_HALF * math.sin(
        self.clock * config.Gpu.PULSE_HZ)
    return PULSE_ONE - amount * wave

  def standing_crowd(self):
    """True if the stands have to be animated this frame."""
    return bool(self.enabled and self.ops is not None
                and self.full_quality())

  def draw_crowd(self, surface):
    """Repaints the band of the stands of `surface` (before the world)."""
    if not self.standing_crowd():
      return
    rect = crowd.band(surface.get_size())
    if rect.height <= 0:
      return
    side, boost = crowd.scene(self.celebration, self.clock)
    cfg, pal = crowd.params()
    band = surface.subsurface(rect)
    image = self._timed(crowd.CROWD, self.ops.crowd, to_array(band),
                        self.clock, side, boost, cfg, pal)
    to_screen(image, band)

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
    if channel is None or self.ops is None or not self.full_quality():
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
    result = self._chain(to_array(self.target), dt)
    ms = (time.perf_counter() - start) * MS_PER_S
    self.metrics.frame(ms)
    to_screen(result, screen)
    self._probe_frame(result)

  def _probe_frame(self, image):
    size = image.shape[1], image.shape[0]
    if size != self.processed_size:
      self.probe.invalidate()
    self.processed_size = size
    if self.probe_active:
      self.probe.maybe_run(self.ops, image)

  def steps_info(self):
    size = self.processed_size if self.enabled else None
    return self.probe.info(self.ops, size)

  def launch_info(self):
    return five_steps.geometry(self.processed_size) if self.enabled else {}

  def quality_label(self):
    """Fixed full-resolution label for the overlay and CSV."""
    return quality.FULL_RESOLUTION

  def toggle(self):
    """Switches between the GPU and the numpy version (F4 key)."""
    if not self.enabled:
      return self.mode
    self.force_cpu = self.mode == "gpu"
    self.reasons.clear()
    self.ops = _make_ops(self.force_cpu, self.reasons)
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
    self.celebration = None
    self.confetti.clear()
    self.pending = None

  # ---------------------------------------------------------------- events
  def event(self, msg):
    """Sparks for the events the simulation sends (cosmetic only)."""
    if not self.allowed or not self.full_quality():
      return
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
    """Sparks, shock wave, celebration and (after it) the replay."""
    x, y = msg.get("x") or 0.0, msg.get("y") or 0.0
    self.particles.spawn(x, y, SPARK_COLOUR, GOAL_SPARKS)
    self.events.append(effects_state.EventFx(
        effects_state.SHOCK_KIND, x, y, self.clock,
        config.Gpu.SHOCK_DURATION))
    if msg.get("side") is None:
      return          # the demo forces a wave: no goal, no celebration
    self.celebration = celebration.Celebration(self.clock, msg)
    self.pending = {"time": self.clock,
                    "close": self.history.is_close(msg.get("side"),
                                                   (x, y)),
                    "state": self.history.last_state()}

  def _start_replay(self):
    """Replay of a goal, or the VAR when it went in by very little.

        It starts after the celebration and shows the goal plus
        `config.Gpu.REPLAY_AFTER_GOAL` seconds of the net. The party is over
        here: the paper is cleared because the replay takes the screen.
        """
    pending, self.pending = self.pending, None
    self.player = None      # the old clip (if any) is not shown again
    self.celebration = None
    self.confetti.clear()
    frames = self.history.window(pending["time"]) if pending else []
    if frames:
      self.player = self._replay_player(pending, frames)
      # The screen closes the replay when the window of the goal ends.
      self.player.from_goal = True

  def _replay_player(self, pending, frames):
    """The VAR when the ball grazed the bar, else the clip of the goal."""
    if pending["close"] or self.force_var:
      return replay.VarPlayer(pending["state"], self.clock)
    span = frames[-1][0] - frames[0][0]
    return replay.ReplayPlayer(frames, self.clock, span)

  def _celebrate(self):
    """Throws the confetti that is due and starts the replay at the end."""
    if self.celebration is None:
      return
    for index in self.celebration.due_bursts(self.clock):
      self.confetti.burst(*self.celebration.burst_shape(index))
    if self.celebration.finished(self.clock):
      self.celebration = None
      self._start_replay()

  def _touch(self, x, y, speed):
    """Sparks of a kick or a bounce (only if it was strong)."""
    if speed > TOUCH_SPEED:
      self.particles.spawn(x, y, SPARK_COLOUR, TOUCH_SPARKS)

  # ----------------------------------------------------------------- chain
  def _chain(self, image, dt):
    self.clock += dt
    self.frame_no += 1
    self.particles.update(dt)
    self.confetti.update(dt)
    self._celebrate()
    self._record_heat()
    if self._advance_player():
      return self._screened(image)      # replay or VAR: only its look
    self.fx = self._derive()
    self._spawn_embers(dt)
    self.phase += config.Gpu.HEAT_SPEED * dt
    return self._flash(self._night(self._stages(image, dt)))

  def _flash(self, image):
    """Warm white flash of the first frames of the celebration."""
    amount = 0.0 if self.celebration is None else self.celebration.flash(
        self.clock)
    if amount <= 0.0:
      return image
    if self.white is None or self.white.shape != image.shape:
      self.white = np.full(image.shape, WHITE, np.uint8)
    return self.ops.mix(image, self.white, amount)

  def _stages(self, image, dt):
    """Run the full chain in its fixed order."""
    out = self._timed("glow", self._glow, image)
    out = self._timed("particles", self._sparks, out)
    if self.confetti.alive():
      out = self._timed("confetti", self._confetti, out)
    out = self._timed("lights", self._lights, out)
    out = self._powers(out, dt)
    out = self._timed("heat", self._heat, out)
    return self._timed("histogram", self._contrast, out)

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

  def _spawn_embers(self, dt):
    """FULL: a small batch of embers over each burnt player."""
    if not self.fx.burned or not self.full_quality():
      return
    self.ember_acc += dt
    if self.ember_acc < EMBER_EVERY:
      return
    self.ember_acc = 0.0
    for x, y in self.fx.burned:
      self.particles.spawn(x, y - EMBER_RAISE, EMBER_COLOUR, EMBER_COUNT)

  def _screened(self, image):
    """Replay or VAR: the chain ends with the look of the screen."""
    if self.player.kind == replay.VAR_KIND:
      return self._timed("var", self._var_look, image)
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
    if not self.enabled:
      return False
    frames = self.history.window(self.clock)
    if not frames:
      return False
    if var:
      self.player = replay.VarPlayer(frames[-1][1], self.clock)
    else:
      span = frames[-1][0] - frames[0][0]
      self.player = replay.ReplayPlayer(frames, self.clock, span)
    return True

  def start_goal_replay(self):
    """Starts the replay (or the VAR) of the goal the tally announced.

        The clip is the one around the goal (not "the last seconds"): the
        screen calls it when the simulation says the replay begins.
        """
    if not self.enabled or self.pending is None:
      return False
    self.celebration = None
    self.confetti.clear()
    self._start_replay()
    return self.player is not None

  def drive_replay(self, progress):
    """Puts the clip at `progress` (0..1) of the simulation's window."""
    if self.player is not None:
      self.player.start = self.clock - progress * self.player.duration

  def end_goal_replay(self):
    """The window of the goal replay is over: back to the live match."""
    if getattr(self.player, "from_goal", False):
      self.player = None

  def skip(self):
    """Jumps the party of the goal and its replay: the match comes back."""
    playing = (self.celebration is not None or self.player is not None)
    self.celebration = None
    self.pending = None
    self.player = None
    self.confetti.clear()
    return playing

  def active_effects(self):
    """Readable list of the effects on this frame (overlay line 4)."""
    names = []
    for name in ("ice", "blackout", "confusion", "fire", "burned",
                 "night", "shock", "trail", "crt", "var"):
      value = getattr(self.fx, name, None)
      if value not in (None, (), 0, 0.0, False):
        names.append(_EFFECT_NAMES.get(name, name))
    if self.celebration is not None:
      names.append(_CELEBRATION_NAME)
    return " + ".join(names) if names else "ninguno"

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
    if not self.trail_gate.update(speed, dt):
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
    """SHOCK: the ring of a goal grows over the pitch and nothing else."""
    if self.fx.shock is None:
      return image
    x, y, age = self.fx.shock
    gpu = config.Gpu
    if age >= gpu.SHOCK_DURATION:
      return image
    amp = gpu.SHOCK_AMP * self.punch() * (1.0 - age / gpu.SHOCK_DURATION)
    return self._timed("shock", self.ops.ripple_ring, image,
                       x, y,
                       gpu.SHOCK_RADIUS * age,
                       gpu.SHOCK_WIDTH * self.punch(),
                       amp, gpu.PITCH_TOP)

  def _fire(self, image):
    """FIRE: hot air around the ball."""
    if self.fx.fire is None:
      return image
    x, y, radius = self.fx.fire
    return self._timed("fire", self.ops.heat_distort, image,
                       x, y, radius,
                       self.clock, config.Gpu.FIRE_AMP * self.punch())

  def _confusion(self, image):
    """CONFUSION: inverted and slowly turning image."""
    if self.fx.confusion <= 0:
      return image
    out = self._timed("confusion", self.ops.invert, image)
    gpu = config.Gpu
    angle = (math.radians(gpu.CONFUSION_MAX_DEG) * self.fx.confusion
             * self.punch() * math.sin(gpu.CONFUSION_SPEED * self.clock))
    return self._timed("confusion_rot", self.ops.rotate, out, angle)

  def _ice(self, image):
    """ICE: bright edges, then a blue tint weighted by the strength.

        One fused stage (`ops.ice`): the edges, the tint and the mix happen in
        two device passes, so the ice no longer costs six round trips.
        """
    if self.fx.ice <= 0:
      return image
    gpu = config.Gpu
    amount = gpu.ICE_STRENGTH * self.fx.ice
    strength = gpu.ICE_EDGES * self.fx.ice
    return self._timed("ice", self.ops.ice, image, min(1.0, strength),
                       gpu.ICE_TINT,
                       min(1.0, amount * self._pulse(gpu.ICE_PULSE)))

  def _blackout(self, image):
    """BLACKOUT: only the light around the affected player stays."""
    if not self.fx.blackout:
      return image
    lights = effects_state.light_array(self.fx.blackout,
                                       config.Gpu.BLACKOUT_RADIUS, 1.0)
    ambient = config.Gpu.BLACKOUT_AMBIENT * self._pulse(
        config.Gpu.BLACKOUT_PULSE)
    return self._timed("blackout", self.ops.spotlights, image,
                       lights, ambient,
                       config.Gpu.BLACKOUT_TINT, NO_LIGHT_CAP)

  def _night(self, image):
    """NIGHT: six spotlights and auto exposure (gain of the last frame)."""
    if not self.fx.night:
      self.exposure.reset()
      return image
    gpu = config.Gpu
    lights = self._sweeping(effects_state.night_lights())
    out = self._timed("night", self.ops.spotlights, image, lights,
                      gpu.NIGHT_AMBIENT, gpu.NIGHT_TINT,
                      gpu.NIGHT_LIGHT_MAX)
    return self._night_sky(self._expose(out))

  def _night_sky(self, image):
    """NIGHT: the sky keeps the ambient light (exposure burnt it)."""
    rows = config.Gpu.CROWD_TOP
    image[:rows] = self.ops.tint(image[:rows], NIGHT_SKY)
    return image

  def _expose(self, image):
    """Auto exposure: the gain found here is used on the next frame.

        The mean is taken on the grass only (the world below `PITCH_TOP`):
        the sky and the stands do not ask for more gain, and the meter
        measures the same surface the players walk on.
        """
    if self.exposure.gain != 1.0:
      image = self._timed("exposure", self.ops.gain, image,
                          self.exposure.gain)
    top = config.Gpu.PITCH_TOP
    grass = image[top:] if 0 < top < image.shape[0] else image
    self.exposure.update(self.ops.luma_stats(grass)[0])
    return image

  def _sweeping(self, lights):
    """FULL: the lamps of the night swing, so the beams move."""
    if not self.full_quality() or len(lights) == 0:
      return lights
    gpu = config.Gpu
    moved = np.array(lights, np.float32, copy=True)
    phase = np.arange(len(moved), dtype=np.float32) * gpu.NIGHT_SWEEP_GAP
    moved[:, 0] += gpu.NIGHT_SWEEP * np.sin(self.clock
                                            * gpu.NIGHT_SWEEP_HZ + phase)
    return moved


  def _glow(self, image):
    """Halo: barely there in a normal frame, strong on a goal or a power."""
    gpu = config.Gpu
    strength = (gpu.GLOW_STRENGTH_FX if self._spectacle()
                else gpu.GLOW_STRENGTH)
    if strength < gpu.GLOW_MIN_STRENGTH:
      return image             # no halo: the pass is not paid
    # The histogram applies the vignette at the end of the chain.
    params = (gpu.EXPOSURE, gpu.GAMMA, SHOW_VIGNETTE, strength)
    return self.ops.glow_composite(image, gpu.GLOW_THRESHOLD,
                                   gpu.GLOW_RADIUS, gpu.GLOW_PASSES,
                                   params)

  def _spectacle(self):
    """True on a goal or a power: only there the halo adds something."""
    if self.celebration is not None:
      return True
    return any(_is_on(getattr(self.fx, name, None))
               for name in SPECTACLE_FX)

  def _sparks(self, image):
    pos, col = self.particles.live()
    if len(pos) == 0:
      return image
    gain = config.Gpu.PARTICLE_GAIN * config.Gpu.FULL_PARTICLES
    return self.ops.particles(image, pos, col, gain)

  def _confetti(self, image):
    """Paper bits of the goal celebration (the `confetti` kernel)."""
    pos, col = self.confetti.live()
    return self.ops.confetti(image, pos, col,
                             config.Gpu.CONFETTI_GAIN)

  def _lights(self, image):
    """ICE: soft focus on the frozen player, over the pitch only.

        The focus multiplies the pixel (it never adds white) and the stands
        above the boards are left out, so no light vein crosses the crowd.
        """
    top = min(image.shape[0], self._pitch_row())
    lamps = self._light_table()
    if len(lamps) == 0 or top >= image.shape[0]:
      return image
    lamps[:, 1] -= top            # measured from the top of the grass
    image[top:] = self.ops.spotlights(image[top:], lamps,
                                      LIGHT_AMBIENT, LIGHT_TINT)
    return image

  def _pitch_row(self):
    """First row of grass in the image of the chain."""
    return config.Gpu.PITCH_TOP

  def _heat(self, image):
    """Heat waves: only with the Fuego power (the stands stay still)."""
    if not _is_on(self.fx.fire):
      return image
    gpu = config.Gpu
    return self.ops.heat(image, self.phase, gpu.HEAT_AMP, gpu.HEAT_PERIOD)

  def _trail(self, image, dt):
    """Kept for the F2 API: the F4 trail is `_ball_trail`."""
    del dt
    return self._ball_trail(image, config.Gpu.TRAIL_MIN_SPEED)

  def _contrast(self, image):
    """Histogram stretch and, at the end, the vignette of the guide."""
    hist = self.ops.histogram(image)
    low, high = _levels(hist, image.size)
    if high <= low:
      return image
    return self.ops.stretch(image, low, high, config.Gpu.VIGNETTE)

  def _light_table(self):
    """Lamp of the freeze power: (x, y, radius, power), in screen px."""
    rows = []
    state = self.state or {}
    players = state.get("players") or []
    for effect in state.get("effects") or []:
      row = _power_light(effect, players)
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
    data["quality"] = quality.FULL_STAGE if self.enabled else "-"
    data["quality_level"] = self.quality_label()
    data["quality_mode"] = self.quality_mode
    data["quality_name"] = self.quality_mode_name()
    data["active"] = self.active_effects()
    data["gpu"] = self.device
    data["reason"] = self.gpu_failure()
    return data

  def gpu_failure(self):
    """Why the GPU is not used (None if it works or was not wanted)."""
    if self.mode == "gpu" or not self.reasons:
      return None
    return self.reasons[-1]


def _wanted(options):
  """True if the effects are enabled and the command line allows them."""
  return (bool(config.Effects.ENABLED)
          and not getattr(options, "no_gpu", False))


def _no_lights():
  """Empty table of lamps (x, y, radius, power)."""
  return np.zeros((0, LIGHT_FIELDS), np.float32)


def _is_on(value):
  """True if an effect parameter is active (float, light or table)."""
  if value is None or value is False:
    return False
  if isinstance(value, np.ndarray):
    return bool(value.size and np.any(value))
  return bool(value)


def _make_ops(force_cpu=False, reasons=None):
  """GPU if PyCUDA loads the kernels here, numpy otherwise.

    The reason of a failure goes to the log and to `reasons` (a list the
    caller shows on screen). A build without PyCUDA (the CPU zip) is not a
    failure: it is silent.
    """
  if force_cpu or not config.Gpu.ENABLED:
    return cpu_ref.Cpu()       # FDC_GPU=0: never import PyCUDA
  try:
    return backend.Gpu()
  except ModuleNotFoundError as exc:
    if not str(exc.name).startswith("pycuda"):
      _report(exc, reasons)
  except Exception as exc:       # pylint: disable=broad-except
    _report(exc, reasons)
  return cpu_ref.Cpu()


def _report(exc, reasons):
  """Logs why the GPU is not used and keeps the reason for the screen."""
  reason = backend.failure_reason(exc)
  if reasons is not None:
    reasons.append(reason)


def to_array(surface):
  """pygame surface -> numpy RGB (h, w, 3)."""
  width, height = surface.get_size()
  raw = pygame.image.tostring(surface, "RGB")
  image = np.frombuffer(raw, np.uint8)
  return image.reshape(height, width, CHANNELS).copy()


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


def _power_light(effect, players):
  """Lamp of a freeze power, or None if it is not one."""
  if effect.get("prop") != effects_state.ICE_PROP:
    return None
  for index, player in enumerate(players):
    if _targets_player(effect, index):
      return (player["x"], player["y"], config.Gpu.FREEZE_RADIUS,
              config.Gpu.FREEZE_GAIN)
  return None


def _targets_player(effect, index):
  """True if the effect belongs to the player at `index`."""
  return effect.get("target") == f"p{index}"
