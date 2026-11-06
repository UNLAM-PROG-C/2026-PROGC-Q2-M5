"""Performance overlay for the projector: what the demo is showing and how
fast it runs.

It is a semitransparent black panel at the bottom left with white text of at
least 22 px (readable from the back of a classroom) and a big GPU/CPU badge.
`F2` or `--overlay` cycles off -> compact -> full. The texts are rebuilt
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
MODES = (OFF, COMPACT, FULL)
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
TWO_DECIMALS = 2          # decimals of the cached values
NO_VALUE = "-"


def lines(info, mode=FULL):
    """Text lines of the overlay for an `info` dict (see `info_of`)."""
    if mode == OFF:
        return ()
    out = [_mode_line(info)]
    out.append(_device_line(info))
    if mode == COMPACT:
        return out
    out.append(_window_line(info))
    out.append(_effects_line(info))
    out.append(_kernels_line(info))
    other = info.get("other")
    if other:
        out.append(f"Otro modo (última medición): {other}")
    return out


def _mode_line(info):
    """Line 1: mode, real FPS and capacity (work without the limiter)."""
    ms = float(info.get("work_ms") or 0.0)
    capacity = config.Gpu.MEASURE_FPS / ms if ms > 0 else 0.0
    return (f"MODO: {_mode_name(info)}   ·   FPS {info.get('fps', 0):.0f}"
            f"   ·   capacidad {capacity:.0f} fps ({ms:.1f} ms/frame)")


def _mode_name(info):
    """Readable name of the backend of the effects."""
    if info.get("mode") == "gpu":
        return "GPU (CUDA)"
    if info.get("mode") == "cpu":
        return "CPU (numpy)"
    return "SIN EFECTOS"


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
    return (f"CPU: {info.get('device', 'cpu')} · numpy {info.get('numpy', '?')}"
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
    keys = ("glow", "particles", "lights", "heat", "trail", "histogram",
            "shock", "fire", "confusion", "confusion_rot", "ice_edges",
            "ice_tint", "blackout", "night", "exposure", "crt", "var")
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
        """Next mode: off -> compact -> full -> off."""
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        self._cache = None
        return self.mode

    def draw(self, surface, info):
        """Paints the panel (it is rebuilt at most 4 times per second)."""
        if self.mode == OFF:
            return
        key = (self.mode, tuple(sorted(self._flatten(info))))
        if key != self._last:
            self._cache = self._build(info)
            self._last = key
        self._paint(surface, self._cache)

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

    def _paint(self, surface, cache):
        """Blits the background, the badge and the lines, bottom left."""
        if not cache:
            return
        panel = self._panel(cache)
        surface.blit(panel, (MARGIN, surface.get_height() - panel.get_height()
                             - MARGIN))

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
