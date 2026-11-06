"""Icono de Futbol de Cabeza: tres propuestas, la lámina y el set final.

Uso (desde la raíz del repo, con el venv):
    python tools/icono.py            # propuestas + lámina + set final
    python tools/icono.py --solo-lamina

La geometría se escribe una sola vez (coordenadas de 1024) y de ahí salen el
PNG (PIL, 4x y downscale) y el SVG, así el vector y el mapa de bits no se
separan nunca. Paleta: guia-visual.md (crema #F6E7C1, tinta #23252F) más los
dos acentos institucionales de la UNLaM tomados de su sitio (#9D2235 bordó y
#0F9977 verde). Nada de escudo ni de laureles copiados: formas propias.
"""
import argparse
import math
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "icono")
PROPUESTAS = os.path.join(OUT, "propuestas")
SIZE = 1024
SS = 4                      # supersampling del PNG
CREAM = "#F6E7C1"
INK = "#23252F"
BORDO = "#9D2235"
VERDE = "#0F9977"
LIGHT = "#F2F5F0"
DARK = "#23252F"
FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT = "C:/Windows/Fonts/arial.ttf"
# La propuesta que se publica (se elige mirando la lámina).
CHOSEN = "b"


# --------------------------------------------------------------- geometría
def pentagon(cx, cy, radius, rotation=0.0):
    """Cinco vértices de un pentágono regular (grados, 0 = arriba)."""
    return [(cx + radius * math.cos(math.radians(rotation + 72 * k - 90)),
             cy + radius * math.sin(math.radians(rotation + 72 * k - 90)))
            for k in range(5)]


def ellipse_poly(cx, cy, rx, ry, angle):
    """Polígono que aproxima una elipse rotada (para las hojas)."""
    cos_a, sin_a = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    points = []
    for k in range(16):
        t = 2 * math.pi * k / 16
        x, y = rx * math.cos(t), ry * math.sin(t)
        points.append((cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a))
    return points


def _seam(cx, cy, radius, inner, outer, width):
    """Franja fina desde el pentágono central hasta un pentágono de afuera."""
    tip_i = pentagon(cx, cy, inner)[0]
    tip_o = pentagon(cx, cy, inner)[0]
    del tip_i, tip_o
    half = width / 2.0
    angle = math.radians(-90 + outer)
    nx, ny = -math.sin(angle) * half, math.cos(angle) * half
    x0, y0 = cx + inner * math.cos(angle), cy + inner * math.sin(angle)
    x1, y1 = cx + radius * 0.98 * math.cos(angle), cy + radius * 0.98 * math.sin(angle)
    return [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
            (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]


def ball(cx, cy, radius, base=CREAM, detail=BORDO, simple=False):
    """Pelota plana: círculo, pentágono central y cinco de borde.

    `simple` deja solo el pentágono central y los de borde: a 16 px las
    costuras finas se empastan y ensucian la silueta.
    """
    ops = [("circle", cx, cy, radius, base)]
    ops.append(("poly", pentagon(cx, cy, radius * 0.42), detail))
    for k in range(5):
        angle = -90 + 72 * k
        px = cx + radius * 0.74 * math.cos(math.radians(angle))
        py = cy + radius * 0.74 * math.sin(math.radians(angle))
        ops.append(("poly", pentagon(px, py, radius * 0.16, angle), detail))
        if not simple:
            ops.append(("poly", _seam(cx, cy, radius, radius * 0.42, 72 * k,
                                      radius * 0.05), detail))
    return ops


def leaf_poly(cx, cy, length, width, angle):
    """Hoja de laurel puntiaguda (dos curvas que se juntan en las puntas)."""
    cos_a, sin_a = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    points = []
    for k in range(9):                 # borde de arriba, de punta a punta
        t = k / 8.0
        x = -length / 2.0 + length * t
        y = -width * math.sin(math.pi * t) ** 0.75
        points.append((cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a))
    for k in range(9):                 # borde de abajo, de vuelta
        t = 1.0 - k / 8.0
        x = -length / 2.0 + length * t
        y = width * math.sin(math.pi * t) ** 0.75
        points.append((cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a))
    return points


def laurel(cx, cy, radius, colour):
    """Dos ramas de laurel estilizadas: hojas propias, no el escudo oficial."""
    ops = []
    for side in (-1, 1):
        for k in range(5):
            theta = math.radians(74 - 15 * k)
            x = cx + side * radius * math.cos(theta)
            y = cy + radius * math.sin(theta)
            # la hoja sigue la tangente del aro, apuntando hacia arriba
            angle = -side * (16 + 13 * k)
            ops.append(("poly", leaf_poly(x, y, radius * 0.30,
                                          radius * 0.085, angle), colour))
        theta = math.radians(80)
        ops.append(("poly", leaf_poly(cx + side * radius * 0.34,
                                      cy + radius * 0.94, radius * 0.28,
                                      radius * 0.08, -side * 10), colour))
    return ops


def propuesta_a():
    """A: baldosa oscura, pelota crema y aro verde (lo más sobrio)."""
    ops = [("rrect", 32, 32, 992, 992, 232, INK),
           ("ring", 512, 512, 420, 30, VERDE)]
    return ops + ball(512, 512, 356, simple=True)


def propuesta_b():
    """B: disco verde, pelota y laureles crema (referencia al sello UNLaM)."""
    ops = [("circle", 512, 512, 480, VERDE),
           ("ring", 512, 512, 456, 18, CREAM)]
    ops += ball(512, 436, 286, simple=True)
    return ops + laurel(512, 452, 338, CREAM)


def propuesta_c():
    """C: disco bordó, la U de UNLaM y la pelota en la boca."""
    ops = [("circle", 512, 512, 480, BORDO),
           ("circle", 512, 476, 318, CREAM),
           ("circle", 512, 476, 236, BORDO),
           ("poly", [(120, 120), (904, 120), (904, 388), (120, 388)], BORDO)]
    return ops + ball(512, 566, 152, VERDE, CREAM, simple=True)


PROPUESTAS_DEF = (("a", "A · baldosa y pelota", propuesta_a),
                  ("b", "B · laureles UNLaM", propuesta_b),
                  ("c", "C · la U y la pelota", propuesta_c))


# ------------------------------------------------------------------ pintado
def draw_ops(ops, size, scale=1):
    """Dibuja la lista de operaciones en una imagen RGBA de `size` px."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for op in ops:
        kind = op[0]
        if kind == "rrect":
            x0, y0, x1, y1, radius, colour = op[1:]
            draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=colour)
        elif kind == "circle":
            cx, cy, radius, colour = op[1:]
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                         fill=colour)
        elif kind == "ring":
            cx, cy, radius, width, colour = op[1:]
            outer = radius + width / 2.0
            draw.ellipse([cx - outer, cy - outer, cx + outer, cy + outer],
                         outline=colour, width=width)
        elif kind == "poly":
            draw.polygon(op[1], fill=op[2])
        else:                      # pragma: no cover
            raise ValueError(kind)
    return image


def render(ops, size=SIZE, supersample=SS):
    """PNG nítido: se dibuja al cuádruple y se baja con LANCZOS."""
    big = draw_ops(ops, size * supersample)
    return big.resize((size, size), Image.LANCZOS)


# --------------------------------------------------------------------- SVG
def to_svg(ops, size=SIZE):
    """El mismo dibujo en SVG (sin texto ni filtros)."""
    def n(value):
        return f"{value:.1f}".rstrip("0").rstrip(".")

    def points(pts):
        return " ".join(f"{n(x)},{n(y)}" for x, y in pts)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} '
             f'{size}" width="{size}" height="{size}">']
    for op in ops:
        kind = op[0]
        if kind == "rrect":
            x0, y0, x1, y1, radius, colour = op[1:]
            parts.append(f'  <rect x="{n(x0)}" y="{n(y0)}" '
                         f'width="{n(x1 - x0)}" height="{n(y1 - y0)}" '
                         f'rx="{n(radius)}" fill="{colour}"/>')
        elif kind == "circle":
            cx, cy, radius, colour = op[1:]
            parts.append(f'  <circle cx="{n(cx)}" cy="{n(cy)}" '
                         f'r="{n(radius)}" fill="{colour}"/>')
        elif kind == "ring":
            cx, cy, radius, width, colour = op[1:]
            parts.append(f'  <circle cx="{n(cx)}" cy="{n(cy)}" '
                         f'r="{n(radius)}" fill="none" stroke="{colour}" '
                         f'stroke-width="{n(width)}"/>')
        elif kind == "poly":
            parts.append(f'  <polygon points="{points(op[1])}" '
                         f'fill="{op[2]}"/>')
    parts.append("</svg>\n")
    return "\n".join(parts)


# ------------------------------------------------------------------ lámina
def font(path, px):
    """Fuente del sistema, o la de PIL si no está (otra PC)."""
    try:
        return ImageFont.truetype(path, px)
    except OSError:
        return ImageFont.load_default()


def _panel(icon, background, sizes, pad=24):
    """Panel con el ícono a cada tamaño sobre un fondo, con su etiqueta."""
    label_h = 26
    width = max(sizes) + 2 * pad
    height = sum(s + label_h + 14 for s in sizes) + 2 * pad
    panel = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(panel)
    small = font(FONT, 14)
    y = pad
    for size in sizes:
        image = icon.resize((size, size), Image.LANCZOS)
        x = (width - size) // 2
        panel.paste(image, (x, y), image)
        draw.text((width // 2, y + size + 4), f"{size} px",
                  font=small, fill="#8A8A93" if background == DARK else "#5A5A63",
                  anchor="ma")
        y += size + label_h + 14
    return panel


def lamina(images):
    """Tres bloques (uno por propuesta) con 1024, y 256/64/32/16 claro y oscuro."""
    pad, gap = 40, 24
    left = SIZE
    col_w = max(_panel(images["a"], LIGHT, (256, 64, 32, 16)).width,
                _panel(images["a"], DARK, (256, 64, 32, 16)).width)
    block_h = SIZE + 96
    width = pad * 2 + left + gap + col_w * 2 + gap
    height = pad + len(PROPUESTAS_DEF) * (block_h + gap)
    sheet = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(sheet)
    title = font(FONT_BOLD, 30)
    label = font(FONT_BOLD, 24)
    for index, (key, name, _) in enumerate(PROPUESTAS_DEF):
        top = pad + index * (block_h + gap)
        draw.text((pad, top + 10), name, font=label, fill=INK)
        big = Image.new("RGB", (SIZE, SIZE), LIGHT)
        big.paste(images[key], (0, 0), images[key])
        sheet.paste(big, (pad, top + 56))
        x = pad + left + gap
        for panel in [_panel(images[key], LIGHT, (256, 64, 32, 16)),
                      _panel(images[key], DARK, (256, 64, 32, 16))]:
            sheet.paste(panel, (x, top + 56))
            x += col_w + gap
    draw.text((pad, 12), "Propuestas de ícono · tamaños 1024 / 256 / 64 / 32 / 16",
              font=title, fill=INK)
    return sheet


# ------------------------------------------------------------------- salida
def write_set(ops, name):
    """PNG 1024, SVG y el .ico con todos los tamaños de Windows."""
    png = render(ops)
    png.save(os.path.join(OUT, f"{name}-1024.png"))
    with open(os.path.join(OUT, f"{name}.svg"), "w", encoding="utf-8") as fh:
        fh.write(to_svg(ops))
    png.save(os.path.join(OUT, "icono.ico"),
             sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    iconset = os.path.join(OUT, "mac", "FutbolDeCabeza.iconset")
    os.makedirs(iconset, exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        png.resize((size, size), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{size}x{size}.png"))
        png.resize((size * 2, size * 2), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
    # favicon de la landing (32 px nítido) y logo del encabezado
    os.makedirs(os.path.join(ROOT, "landing"), exist_ok=True)
    png.resize((64, 64), Image.LANCZOS).save(
        os.path.join(ROOT, "landing", "logo.png"))


def main(argv=None):
    """Genera las tres propuestas, la lámina y el set de la elegida."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elegida", default=CHOSEN,
                        choices=[key for key, _, _ in PROPUESTAS_DEF])
    args = parser.parse_args(argv)
    os.makedirs(PROPUESTAS, exist_ok=True)
    images = {}
    for key, _, builder in PROPUESTAS_DEF:
        ops = builder()
        png = render(ops)
        images[key] = png
        png.save(os.path.join(PROPUESTAS, f"propuesta-{key}-1024.png"))
        with open(os.path.join(PROPUESTAS, f"propuesta-{key}.svg"), "w",
                  encoding="utf-8") as fh:
            fh.write(to_svg(ops))
    sheet = lamina(images)
    sheet.save(os.path.join(PROPUESTAS, "propuestas.png"))
    chosen = dict((key, builder) for key, _, builder in PROPUESTAS_DEF)
    write_set(chosen[args.elegida](), "logo")
    print(f"propuestas: {PROPUESTAS}")
    print(f"lámina: {os.path.join(PROPUESTAS, 'propuestas.png')}")
    print(f"elegida {args.elegida}: {os.path.join(OUT, 'logo-1024.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
