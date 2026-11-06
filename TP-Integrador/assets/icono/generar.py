"""Icon set of Futbol de Cabeza: three proposals, the sheet and the final set.

Usage (from the repository, with the venv that has Pillow):
    python assets/icono/generar.py                # proposals + sheet + set
    python assets/icono/generar.py --elegida c

The geometry is written once in 1024 units and every raster is drawn at the
exact target size (canvas = size * supersampling, coordinates scaled), so a
16 px icon is a 16 px icon and not a shrunken 1024. Each size gets the detail
its level allows: the wordmark only from 64 px, the ball pattern from 32 px
and just the ball below that. Palette: guia-visual.md (cream #F6E7C1, ink
#23252F) plus the two institutional accents of unlam.edu.ar (#AE152D bordo,
#0F9977 green), taken from the CSS of the site. Own shapes: no escudo and no
official typography are copied.
"""
import argparse
import math
import os

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "icono")
PROPUESTAS = os.path.join(OUT, "propuestas")
SIZE = 1024                 # design canvas, all coordinates below use it
CREAM = "#F6E7C1"
INK = "#23252F"
BORDO = "#AE152D"
VERDE = "#0F9977"
LIGHT = "#F2F5F0"
DARK = "#23252F"
WHITE = "#FFFFFF"
LABEL_ON_LIGHT = "#5A5A63"
LABEL_ON_DARK = "#B9BAC4"
FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT_FALLBACK = "DejaVuSans-Bold.ttf"
SS_BIG = 4                  # supersampling for 128 px and up
SS_SMALL = 8                # supersampling for the small sizes
TILE_MARGIN = 20
TILE_RADIUS = 210
BALL_RADIUS = 360
BALL_CENTER = (512, 380)
WORD_BASELINE = 946
WORD_SIZE = 200
# Detail levels: below LEVEL_FULL no word, below LEVEL_MEDIUM only the ball.
LEVEL_FULL = 64
LEVEL_MEDIUM = 32
SMALL = "small"
MEDIUM = "medium"
FULL = "full"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
# iconset name -> pixels (macOS expects exactly these ten files).
ICONSET = (("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
           ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
           ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
           ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
           ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024))
WINDOW_ICON = 256           # assets/icono/logo.png, used by pygame
LANDING_ICON = 128          # landing/logo.png, shown at 30 CSS px
CHOSEN = "a"                # the proposal that ships (see the sheet)


# --------------------------------------------------------------- geometry
def pentagon(cx, cy, radius, rotation=0.0):
    """Five vertices of a regular pentagon, 0 degrees = pointing up."""
    return [(cx + radius * math.cos(math.radians(rotation + 72 * k - 90)),
             cy + radius * math.sin(math.radians(rotation + 72 * k - 90)))
            for k in range(5)]


def level_for(size):
    """Detail level a raster of `size` pixels can show."""
    if size >= LEVEL_FULL:
        return FULL
    if size >= LEVEL_MEDIUM:
        return MEDIUM
    return SMALL


def tile(colour):
    """Rounded square of the whole icon (the app-tile shape)."""
    return [("rrect", TILE_MARGIN, TILE_MARGIN, SIZE - TILE_MARGIN,
             SIZE - TILE_MARGIN, TILE_RADIUS, colour)]


def ball(level, detail, radius=BALL_RADIUS, center=BALL_CENTER, base=CREAM):
    """Flat ball: a `base` circle with pentagons and seams in `detail`.

    Small sizes keep only the circle: the pattern turns into mud at 16 px.
    """
    cx, cy = center
    ops = [("circle", cx, cy, radius, base)]
    if level == SMALL:
        return ops
    ops += _seams(cx, cy, radius, detail)
    ops.append(("poly", pentagon(cx, cy, radius * 0.40), detail))
    for k in range(5):
        angle = math.radians(-90 + 72 * k)
        px = cx + radius * 0.74 * math.cos(angle)
        py = cy + radius * 0.74 * math.sin(angle)
        ops.append(("poly", pentagon(px, py, radius * 0.17,
                                     -90 + 72 * k), detail))
    return ops


def _seams(cx, cy, radius, colour):
    """Five thick lines between the central pentagon and the border."""
    ops = []
    width = radius * 0.055
    for k in range(5):
        angle = math.radians(-90 + 72 * k + 36)
        r0, r1 = radius * 0.44, radius * 0.86
        ops.append(("line", cx + r0 * math.cos(angle),
                    cy + r0 * math.sin(angle), cx + r1 * math.cos(angle),
                    cy + r1 * math.sin(angle), width, colour))
    return ops


def word(level, colour, baseline=WORD_BASELINE, size=WORD_SIZE):
    """The UNLaM wordmark; only the sizes that can read it get it."""
    if level != FULL:
        return []
    return [("text", 512, baseline, size, colour, "UNLaM")]


# -------------------------------------------------------------- proposals
def propuesta_a(level):
    """A: bordo tile, cream ball, cream wordmark (the solid app icon)."""
    return tile(BORDO) + ball(level, BORDO) + word(level, CREAM)


def propuesta_b(level):
    """B: green tile, bordo ball, cream wordmark (the inverted palette)."""
    ops = tile(VERDE) + ball(level, CREAM, base=BORDO)
    return ops + word(level, CREAM)


def propuesta_c(level):
    """C: ink tile, cream ball, green wordmark (the dark modern one)."""
    return tile(INK) + ball(level, INK) + word(level, VERDE)


PROPUESTAS_DEF = (("a", "A · baldosa bordó", propuesta_a),
                  ("b", "B · sello verde", propuesta_b),
                  ("c", "C · tinta y verde", propuesta_c))


# ------------------------------------------------------------------ raster
def _scaled(points, scale):
    """Polygon points multiplied by the scale of the canvas."""
    return [(x * scale, y * scale) for x, y in points]


def _font(px):
    """Arial Bold, or the first fallback that exists."""
    for path in (FONT_BOLD, FONT_FALLBACK):
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_one(draw, op, scale):
    """Draws one operation on a canvas already scaled by `scale`."""
    kind = op[0]
    if kind == "rrect":
        x0, y0, x1, y1, radius, colour = op[1:]
        box = [x0 * scale, y0 * scale, x1 * scale, y1 * scale]
        draw.rounded_rectangle(box, radius=radius * scale, fill=colour)
    elif kind == "circle":
        cx, cy, radius, colour = op[1:]
        box = [(cx - radius) * scale, (cy - radius) * scale,
               (cx + radius) * scale, (cy + radius) * scale]
        draw.ellipse(box, fill=colour)
    elif kind == "poly":
        draw.polygon(_scaled(op[1], scale), fill=op[2])
    elif kind == "line":
        x0, y0, x1, y1, width, colour = op[1:]
        draw.line([x0 * scale, y0 * scale, x1 * scale, y1 * scale],
                  fill=colour, width=max(1, round(width * scale)))
    elif kind == "text":
        x, y, size, colour, text = op[1:]
        draw.text((x * scale, y * scale), text, fill=colour,
                  font=_font(max(1, round(size * scale))), anchor="ms")
    else:                                   # pragma: no cover
        raise ValueError(kind)


def render(ops, size):
    """Raster of `size` px: drawn big with scaled coordinates, then reduced."""
    supersample = SS_BIG if size >= 128 else SS_SMALL
    canvas = size * supersample
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for op in ops:
        _draw_one(draw, op, canvas / float(SIZE))
    return image.resize((size, size), Image.LANCZOS)


def render_at(builder, size):
    """Raster of `size` px with the detail level that size allows."""
    return render(builder(level_for(size)), size)


# --------------------------------------------------------------------- SVG
def _num(value):
    """Number for the SVG without trailing zeros."""
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _points(points):
    """`x,y x,y ...` for a polygon."""
    return " ".join(f"{_num(x)},{_num(y)}" for x, y in points)


def _svg_one(op):
    """The SVG element of one operation."""
    kind = op[0]
    if kind == "rrect":
        x0, y0, x1, y1, radius, colour = op[1:]
        return (f'  <rect x="{_num(x0)}" y="{_num(y0)}" '
                f'width="{_num(x1 - x0)}" height="{_num(y1 - y0)}" '
                f'rx="{_num(radius)}" fill="{colour}"/>')
    if kind == "circle":
        cx, cy, radius, colour = op[1:]
        return (f'  <circle cx="{_num(cx)}" cy="{_num(cy)}" '
                f'r="{_num(radius)}" fill="{colour}"/>')
    if kind == "poly":
        return f'  <polygon points="{_points(op[1])}" fill="{op[2]}"/>'
    if kind == "line":
        x0, y0, x1, y1, width, colour = op[1:]
        return (f'  <line x1="{_num(x0)}" y1="{_num(y0)}" x2="{_num(x1)}" '
                f'y2="{_num(y1)}" stroke="{colour}" '
                f'stroke-width="{_num(width)}" stroke-linecap="round"/>')
    if kind == "text":
        x, y, size, colour, text = op[1:]
        return (f'  <text x="{_num(x)}" y="{_num(y)}" '
                f'text-anchor="middle" font-family="Arial, Helvetica, '
                f'sans-serif" font-weight="700" font-size="{_num(size)}" '
                f'fill="{colour}">{text}</text>')
    raise ValueError(kind)                  # pragma: no cover


def to_svg(ops, width=SIZE):
    """The same drawing as SVG, scaled to `width` by the viewBox."""
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} '
            f'{SIZE}" width="{width}" height="{width}">')
    return "\n".join([head] + [_svg_one(op) for op in ops] + ["</svg>", ""])


# ------------------------------------------------------------------ sheet
def _caption(draw, x, y, text, colour):
    """Small caption centred at `x`, starting at `y`."""
    draw.text((x, y), text, font=_font(20), fill=colour, anchor="ma")


def _sizes_column(icon_sizes, background):
    """Right column: 256/64/32/16 at real size plus 8x and 4x zooms."""
    width, height, label_h, gap = 256, 1024, 30, 10
    panel = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(panel)
    colour = LABEL_ON_DARK if background == DARK else LABEL_ON_LIGHT
    y = 0
    for size in (256, 64, 32, 16):
        panel.paste(icon_sizes[size], ((width - size) // 2, y),
                    icon_sizes[size])
        _caption(draw, width // 2, y + size + 2, f"{size} px", colour)
        y += size + label_h + gap
    y += 8
    zoom_16 = icon_sizes[16].resize((128, 128), Image.NEAREST)
    zoom_32 = icon_sizes[32].resize((128, 128), Image.NEAREST)
    panel.paste(zoom_16, (0, y), zoom_16)
    panel.paste(zoom_32, (128, y), zoom_32)
    _caption(draw, 64, y + 132, "16 px ×8", colour)
    _caption(draw, 192, y + 132, "32 px ×4", colour)
    return panel


def _panel(icon_sizes, background):
    """Light or dark panel: 1024 tile at real size plus the sizes column."""
    pad, gap = 36, 24
    width = pad + 1024 + gap + 256 + pad
    panel = Image.new("RGB", (width, 1024 + 2 * pad + 34), background)
    panel.paste(icon_sizes[1024], (pad, pad), icon_sizes[1024])
    draw = ImageDraw.Draw(panel)
    colour = LABEL_ON_DARK if background == DARK else LABEL_ON_LIGHT
    _caption(draw, pad + 512, pad + 1024 + 4, "1024 px", colour)
    panel.paste(_sizes_column(icon_sizes, background), (pad + 1024 + gap, pad))
    return panel


def lamina(images):
    """One row per proposal: title, light panel and dark panel."""
    pad = 40
    panels = {}
    for key, _, _ in PROPUESTAS_DEF:
        panels[key] = (_panel(images[key], LIGHT), _panel(images[key], DARK))
    tile_w, tile_h = panels["a"][0].size
    width = pad * 3 + tile_w * 2
    row_h = tile_h + 96
    height = pad + 84 + len(PROPUESTAS_DEF) * row_h
    sheet = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, 22), "Futbol de Cabeza · propuestas de ícono",
              font=_font(34), fill=INK)
    draw.text((pad, 62), "Tamaños reales 1024 / 256 / 64 / 32 / 16 px, "
              "sobre fondo claro y oscuro", font=_font(20),
              fill=LABEL_ON_LIGHT)
    for index, (key, name, _) in enumerate(PROPUESTAS_DEF):
        top = pad + 84 + index * row_h
        draw.text((pad, top), name, font=_font(28), fill=INK)
        for column, panel in enumerate(panels[key]):
            x = pad + column * (tile_w + pad)
            sheet.paste(panel, (x, top + 44))
    return sheet


# ----------------------------------------------------------------- output
def _write_ico(builder, path):
    """Windows .ico with one raster per size (no scaling of a single one)."""
    images = [render_at(builder, size) for size in ICO_SIZES]
    images[-1].save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                    append_images=images[:-1])


def _write_iconset(builder, root):
    """The ten PNGs of the macOS iconset, each drawn at its own size."""
    iconset = os.path.join(root, "mac", "FutbolDeCabeza.iconset")
    os.makedirs(iconset, exist_ok=True)
    for name, size in ICONSET:
        render_at(builder, size).save(os.path.join(iconset, name))


def _write_landing(builder):
    """Favicon, header logo and its SVG for the landing page."""
    landing = os.path.join(ROOT, "landing")
    os.makedirs(landing, exist_ok=True)
    render_at(builder, LANDING_ICON).save(os.path.join(landing, "logo.png"))
    with open(os.path.join(landing, "logo.svg"), "w", encoding="utf-8") as fh:
        fh.write(to_svg(builder(FULL), width=LANDING_ICON))
    with open(os.path.join(landing, "favicon.svg"), "w",
              encoding="utf-8") as fh:
        fh.write(to_svg(builder(SMALL), width=64))


def write_set(builder, name):
    """PNG 1024, SVG, window PNG, .ico, iconset and landing files."""
    png = render_at(builder, SIZE)
    png.save(os.path.join(OUT, f"{name}-1024.png"))
    svg = to_svg(builder(FULL))
    with open(os.path.join(OUT, f"{name}.svg"), "w", encoding="utf-8") as fh:
        fh.write(svg)
    render_at(builder, WINDOW_ICON).save(os.path.join(OUT, f"{name}.png"))
    _write_ico(builder, os.path.join(OUT, "icono.ico"))
    _write_iconset(builder, OUT)
    _write_landing(builder)


def main(argv=None):
    """Generates the three proposals, the sheet and the set of the chosen."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elegida", default=CHOSEN,
                        choices=[key for key, _, _ in PROPUESTAS_DEF])
    args = parser.parse_args(argv)
    os.makedirs(PROPUESTAS, exist_ok=True)
    images = {}
    for key, _, builder in PROPUESTAS_DEF:
        images[key] = {size: render_at(builder, size)
                       for size in (1024, 256, 64, 32, 16)}
        images[key][1024].save(os.path.join(PROPUESTAS,
                                            f"propuesta-{key}-1024.png"))
        with open(os.path.join(PROPUESTAS, f"propuesta-{key}.svg"), "w",
                  encoding="utf-8") as fh:
            fh.write(to_svg(builder(FULL)))
    lamina(images).save(os.path.join(PROPUESTAS, "propuestas.png"))
    chosen = dict((key, builder) for key, _, builder in PROPUESTAS_DEF)
    write_set(chosen[args.elegida], "logo")
    print(f"propuestas: {PROPUESTAS}")
    print(f"lámina: {os.path.join(PROPUESTAS, 'propuestas.png')}")
    print(f"elegida {args.elegida}: {os.path.join(OUT, 'logo-1024.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
