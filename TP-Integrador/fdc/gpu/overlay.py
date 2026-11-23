"""Performance overlay for the projector: the active effects and timings.

It is a semitransparent black panel at the bottom left with white text of at
least 22 px (readable from the back of a classroom) and a big GPU/CPU badge.
`F2` cycles off -> compact -> full -> steps. The probe is refreshed
only 4 times per second (config.Gpu.OVERLAY_REFRESH): formatting strings
every frame would be paid in the very numbers it measures.

The lines are a pure function (`lines`) so they can be tested without a
window; `Overlay` only paints them.
"""
import pygame

from fdc import config

OFF = "off"
COMPACT = "compact"
FULL = "full"
STEPS = "steps"
MODES = (OFF, COMPACT, FULL, STEPS)
TEXT = (255, 255, 255)        # colour of the overlay text
BACKGROUND = (0, 0, 0)        # colour of the shadow and panel
GPU_COLOUR = (0x76, 0xB9, 0x00)     # NVIDIA green
CPU_COLOUR = (255, 138, 30)         # the orange of player 1
BADGE_PAD = 10                      # px of the badge around its text
BADGE_GAP = 12                      # px between the badge and the first line
PADDING = 12                        # px of the panel border
LINE_GAP = 4                        # px between two lines
MARGIN = 10                         # px between the panel and the screen
MIN_WIDTH = 520                     # px: narrower panels look broken
THUMB_X = 280                      # px from the badge to the preview
TWO_DECIMALS = 2          # decimals of the cached values
NO_VALUE = "-"
UNMEASURED = "sin medir"         # speedup without a paired measurement
WARP_SIZE = 32  # threads per NVIDIA warp
# Overlay rows of the five course steps (G1 35-48), GPU and numpy.
STEP_LABELS = ("Reservar memoria", "Copiar a la GPU", "Ejecutar el kernel",
               "Leer el resultado", "Liberar memoria")
# numpy has no copies: steps 2, 4 and 5 show "no aplica".
CPU_STEP_LABELS = ("Reservar memoria (CPU)", STEP_LABELS[1],
                   "Calcular con numpy", *STEP_LABELS[3:])


def lines(info, mode=FULL):
  """Text lines of the overlay for an `info` dict (see `info_of`)."""
  if mode == OFF:
    return ()
  if mode == STEPS:
    return _steps_lines(info)
  out = [_mode_line(info)]
  out.append(_device_line(info))
  if mode == COMPACT:
    return out
  out.append(_window_line(info))
  out.append(_effects_line(info))
  out.append(_kernels_line(info))
  return out


def _steps_lines(info):
  totals = info.get('totals', {})
  rows = [f"PASOS · Escala de grises · {_mode_name(info)}",
          _steps_geometry(info), _steps_threads(info)]
  rows.extend(_step_rows(info))
  rows.append(f"Total CPU: {_ms(totals.get('cpu'))} · "
              f"GPU: {_ms(totals.get('gpu'))}")
  rows.append(f"Aceleración (CPU/GPU): "
              f"{info.get('speedup') or UNMEASURED}")
  return rows


def _steps_geometry(info):
  reference = ' · referencia CUDA' if info.get('mode') == 'cpu' else ''
  return (f"Procesado: {info.get('resolution', NO_VALUE)}{reference} · "
          f"grilla {info.get('grid', NO_VALUE)} · "
          f"bloque {info.get('block', NO_VALUE)}")


def _steps_threads(info):
  return (f"Hilos: {info.get('threads', NO_VALUE)} totales, "
          f"{info.get('surplus', NO_VALUE)} sobrantes · "
          f"warp = {WARP_SIZE}")


def _step_rows(info):
  times = info.get('steps', ())
  labels = CPU_STEP_LABELS if info.get('mode') == 'cpu' else STEP_LABELS
  values = [('no aplica' if ms is None else _ms(ms)) for ms in times]
  if not values:
    values = [NO_VALUE] * len(labels)
  return [f"{index}. {label}: {value}"
          for index, (label, value) in enumerate(zip(labels, values), 1)]


def _ms(value):
  return NO_VALUE if value is None else f"{value:.3f} ms"


def _with_thumbnail(badge, thumbnail):
  width = THUMB_X + thumbnail.get_width()
  height = max(badge.get_height(), thumbnail.get_height())
  header = pygame.Surface((width, height), pygame.SRCALPHA)
  header.blit(badge, (0, 0))
  header.blit(thumbnail, (THUMB_X, 0))
  return header


def _mode_line(info):
  """Line 1: quality mode, backend, real FPS and cost of the effects."""
  ms = float(info.get("work_ms") or 0.0)
  capacity = config.Gpu.MEASURE_FPS / ms if ms > 0 else 0.0
  fx = float(info.get("fx_ms") or 0.0)
  return (f"CALIDAD {_quality_name(info)}   ·   {_mode_name(info)}   ·   "
          f"FPS {info.get('fps', 0):.0f}   ·   efectos {fx:.1f} ms"
          f"   ·   capacidad {capacity:.0f} fps")


def _quality_name(info):
  """User-facing quality mode of the chain."""
  return info.get("quality_name") or config.Gpu.MODE_NAMES.get(
      info.get("quality_mode"), "-")


def _mode_name(info):
  """Readable name of the backend of the effects."""
  if info.get("mode") == "gpu":
    return "GPU (CUDA)"
  if info.get("mode") == "cpu":
    return "CPU (numpy)"
  return "SIN EFECTOS"


def _numpy_version(info):
  """The numpy version: from the info, or from the installed module."""
  if info.get("numpy"):
    return info["numpy"]
  try:
    import numpy  # pylint: disable=import-outside-toplevel
    return numpy.__version__
  except ImportError:
    return "no instalado"


def _device_line(info):
  """Line 2: the device, its launch geometry and the CPU quality."""
  if info.get("mode") == "gpu":
    return (f"GPU: {info.get('device', '?')} · bloque "
            f"{info.get('block', '?')} · grilla {info.get('grid', '?')} · "
            f"hilos {info.get('threads', '?')} "
            f"(sobrantes {info.get('surplus', 0)})")
  if info.get("reason"):
    return f"GPU no disponible: {info['reason']}"
  quality = info.get("quality_level") or info.get("quality", "Q0")
  return (f"CPU: {info.get('device', 'cpu')} · numpy {_numpy_version(info)}"
          f" · calidad {quality}")


def _window_line(info):
  """Line 3: processed and window size, and whether it is a remote desk."""
  remote = "sí" if info.get("remote") else "no"
  return (f"Resolución procesada {info.get('resolution', '?')} · ventana "
          f"{info.get('window', '?')} · sesión remota: {remote}")


def _effects_line(info):
  """Line 4: active effects and the total cost of the chain."""
  active = info.get("active") or "ninguno"
  fx = float(info.get("fx_ms") or 0.0)
  htod = float(info.get("htod_ms") or 0.0)
  dtoh = float(info.get("dtoh_ms") or 0.0)
  text = f"Efectos activos: {active}   ·   fx total {fx:.1f} ms"
  if htod or dtoh:
    text += f" (HtoD {htod:.1f} · DtoH {dtoh:.1f})"
  return text


def _kernels_line(info):
  """Line 5: one number per stage of the chain."""
  parts = [f"{name} {ms:.2f}" for name, ms in (info.get("kernels") or [])]
  return " · ".join(parts) if parts else "Sin etapas medidas"


def info_of(postfx_summary, app=None, extra=None):
  """Builds the `info` dict from the numbers of the chain."""
  data = dict(postfx_summary or {})
  data.update(extra or {})
  data.setdefault("kernels", _kernels(data))
  return data


def _kernels(data):
  """[(stage, ms)] of the stages that ran this frame (mean > 0)."""
  keys = ("glow", "particles", "confetti", "lights", "heat",
          "histogram", "fire", "confusion", "confusion_rot",
          "ice", "blackout", "night", "exposure", "crt", "crowd")
  return [(key, float(data.get(key) or 0.0)) for key in keys
          if (data.get(key) or 0.0) > 0.0]


class Overlay:
  """The panel: mode, cached lines and the cached text surfaces."""

  def __init__(self, mode=COMPACT, font_size=None):
    self.mode = mode if mode in MODES else COMPACT
    self.font = pygame.font.Font(None, font_size or config.Gpu.OVERLAY_FONT)
    self.badge_font = pygame.font.Font(None,
                                       (font_size or
                                        config.Gpu.OVERLAY_FONT) + PADDING)
    self._cache = None          # (key, [(surface, surface)])
    self._age = config.Gpu.OVERLAY_REFRESH
    self._last = None

  def cycle(self):
    """Next mode: off -> compact -> full -> steps -> off."""
    self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
    self._last = None
    return self.mode

  def draw(self, surface, info, avoid=None):
    """Paints the panel (it is rebuilt at most 4 times per second)."""
    if self.mode == OFF:
      return
    key = (self.mode, tuple(sorted(self._flatten(info))))
    if key != self._last:
      self._cache = self._build(info)
      self._last = key
    self._paint(surface, self._cache, avoid)

  def _flatten(self, info):
    """Hashable view of the numbers that the panel shows."""
    out = []
    for name, value in info.items():
      if isinstance(value, float):
        value = round(value, TWO_DECIMALS)
      if isinstance(value, list):
        value = tuple(value)
      out.append((name, str(value)))
    return out

  def _build(self, info):
    """Renders every line; the badge is the first one."""
    rows = [self._render(text) for text in lines(info, self.mode)]
    badge = self._badge(info)
    if self.mode == STEPS and info.get('thumbnail') is not None:
      badge = _with_thumbnail(badge, info['thumbnail'])
    return badge, rows

  def _badge(self, info):
    """Green GPU / orange CPU tag of the panel."""
    name = "GPU" if info.get("mode") == "gpu" else "CPU"
    colour = GPU_COLOUR if info.get("mode") == "gpu" else CPU_COLOUR
    text = self.badge_font.render(name, True, TEXT, colour)
    rect = text.get_rect().inflate(BADGE_PAD, BADGE_PAD)
    tag = pygame.Surface(rect.size, pygame.SRCALPHA)
    tag.blit(text, (BADGE_PAD, BADGE_PAD // 2))
    return tag

  def _render(self, text):
    """One white line with a black shadow (it reads over any image)."""
    shadow = self.font.render(text, True, BACKGROUND)
    front = self.font.render(text, True, TEXT)
    width = max(front.get_width(), shadow.get_width())
    height = front.get_height() + shadow.get_height() // 2
    line = pygame.Surface((width, height), pygame.SRCALPHA)
    line.blit(shadow, (1, 1))
    line.blit(front, (0, 0))
    return line

  def _paint(self, surface, cache, avoid):
    """Blits the background, the badge and the lines, bottom left."""
    if not cache:
      return
    panel = self._panel(cache)
    rect = panel.get_rect(bottomleft=(MARGIN, surface.get_height() - MARGIN))
    if avoid is not None and rect.colliderect(avoid):
      rect.bottom = avoid.top - MARGIN
    surface.blit(panel, rect)

  def _panel(self, cache):
    """Panel surface with the badge and every line already drawn."""
    badge, rows = cache
    width = max([badge.get_width()] + [r.get_width() for r in rows])
    width = max(width, MIN_WIDTH) + PADDING * 2
    height = (badge.get_height() + BADGE_GAP
              + sum(r.get_height() + LINE_GAP for r in rows) + PADDING)
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    panel.fill((*BACKGROUND, config.Gpu.OVERLAY_ALPHA))
    panel.blit(badge, (PADDING, PADDING))
    top = PADDING + badge.get_height() + BADGE_GAP
    for row in rows:
      panel.blit(row, (PADDING, top))
      top += row.get_height() + LINE_GAP
    return panel
