"""Convierte los sprites originales (assets/originales/<id>.webp) en los que usa el juego.

Cada original trae la cabeza (con el cuello de la camiseta) y un botín pegado
abajo a la derecha. Este script:
  1. detecta el botín (núcleo gris oscuro en la zona inferior derecha),
     lo envuelve con su contorno y lo separa de la cabeza;
  2. reduce ambos a resolución nativa de pixel art (1 píxel nativo ≈ una celda
     del dibujo original), con alfa binario y colores limpios;
  3. guarda assets/personajes/<id>.png (cabeza mirando a la IZQUIERDA, como el
     original), los cuadros del botín rotado (assets/personajes/botin_<ang>.png,
     rotados en alta resolución antes de reducirlos) y assets/personajes/sprites.json
     con el centro de cada cabeza y el punto de giro (tobillo) del botín.

Uso (desde la raíz del proyecto):
    .venv/bin/python tools/importar_sprites.py
    .venv/bin/python tools/importar_sprites.py --depurar   # guarda imágenes de control
"""
import argparse
import json
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "assets", "originales")
OUT_DIR = os.path.join(ROOT, "assets", "personajes")
IDS = ("messi", "maradona", "pele", "cr7", "henry", "neymar", "mbappe")
BOOT_FROM = "pele"
SOURCE_PX = 18.6          # píxeles del original por píxel nativo (cabeza de ~43 px nativos)
BOOT_ANGLES = list(range(30, -121, -10))   # grados; + gira la punta hacia atrás
HEAD_ANCHOR_FROM_TOP = 21.5              # centro del cráneo, medido desde el pelo (px nativos)
OUTLINE = (22, 18, 20)

# Línea de corte entre el cuello y los cordones del botín, en coordenadas del
# original: todo lo que queda DEBAJO de la recta A-B (y a la derecha de A) es
# botín. Se eligieron mirando la grilla de --depurar; si se cambia un sprite,
# hay que ajustar su línea.
CUTS = {
    "pele": ((690, 985), (860, 855)),
    "neymar": ((700, 1000), (870, 870)),
    "mbappe": ((700, 995), (870, 872)),
    "maradona": ((720, 985), (870, 850)),
    "henry": ((700, 985), (860, 850)),
    "cr7": ((700, 992), (860, 862)),
    "messi": ((700, 978), (860, 852)),
}


def boot_mask(src, cid):
    """Semiplano por debajo de la línea de corte, limitado a la zona del botín."""
    w, h = src.get_size()
    (ax, ay), (bx, by) = CUTS[cid]
    k = (by - ay) / (bx - ax)
    far = 4000
    poly = [(ax - 60, ay - k * 60), (bx + far, by + k * far), (bx + far, h + far), (ax - 60, h + far)]
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(s, (255, 255, 255), poly)
    return pygame.mask.from_surface(s, 128)


def apply_mask(src, mask, keep=True):
    """Copia de src con alfa 0 fuera (keep=True) o dentro (keep=False) de la máscara."""
    w, h = src.get_size()
    m = mask if keep else _inverted(mask)
    cut = m.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(255, 255, 255, 0))
    out = src.copy()
    out.blit(cut, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def _inverted(mask):
    m = mask.copy()
    m.invert()
    return m


def largest_part(surf):
    m = pygame.mask.from_surface(surf, 128)
    comps = m.connected_components(50)
    if not comps:
        return surf
    return apply_mask(surf, max(comps, key=lambda c: c.count()))


def to_native(surf, bb=None):
    """Recorta, reduce y limpia: alfa binario, colores cuantizados, contorno cerrado.

    Devuelve (superficie nativa, rectángulo recortado en coordenadas del original).
    """
    bb = bb or surf.get_bounding_rect(128)
    crop = surf.subsurface(bb).copy()
    size = (max(1, round(bb.w / SOURCE_PX)), max(1, round(bb.h / SOURCE_PX)))
    small = pygame.transform.smoothscale(crop, size)
    w, h = size
    out = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    solid = set()
    for y in range(h):
        for x in range(w):
            c = small.get_at((x, y))
            if c.a < 120:
                continue
            k = 255.0 / c.a                      # des-premultiplica el borde
            r, g, b = (min(255, int(v * k)) for v in (c.r, c.g, c.b))
            if max(r, g, b) < 58:
                r, g, b = OUTLINE                # casi negro -> contorno
            else:
                r, g, b = (min(255, (v + 4) // 8 * 8) for v in (r, g, b))
            out.set_at((x + 1, y + 1), (r, g, b, 255))
            solid.add((x + 1, y + 1))
    # contorno de 1 píxel nativo donde el borde quedó sin línea oscura
    for (x, y) in list(solid):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in solid:
                continue
            c = out.get_at((x, y))
            if max(c.r, c.g, c.b) > 70:
                if 0 <= n[0] < w + 2 and 0 <= n[1] < h + 2:
                    out.set_at(n, (*OUTLINE, 255))
    return out, bb


def native_point(pt, bb):
    """Punto del original -> coordenadas del sprite nativo recortado (con margen 1)."""
    return ((pt[0] - bb.left) / SOURCE_PX + 1, (pt[1] - bb.top) / SOURCE_PX + 1)


def boot_frames(boot, meta_out):
    """Rota el botín en alta resolución alrededor del tobillo y reduce cada cuadro."""
    bb = boot.get_bounding_rect(128)
    # tobillo: arriba a la derecha del botín (donde entraría la pierna)
    pivot = (bb.right - bb.w * 0.28, bb.top + bb.h * 0.12)
    crop = boot.subsurface(bb).copy()
    pad = int(math.hypot(bb.w, bb.h))
    big = pygame.Surface((bb.w + 2 * pad, bb.h + 2 * pad), pygame.SRCALPHA)
    big.blit(crop, (pad, pad))
    pv = (pivot[0] - bb.left + pad, pivot[1] - bb.top + pad)
    frames = {}
    for ang in BOOT_ANGLES:
        rot = pygame.transform.rotozoom(big, ang, 1.0)
        # ubicar el pivote dentro de la imagen rotada
        cx, cy = big.get_width() / 2, big.get_height() / 2
        vx, vy = pv[0] - cx, pv[1] - cy
        a = math.radians(ang)
        rx = vx * math.cos(a) + vy * math.sin(a)
        ry = -vx * math.sin(a) + vy * math.cos(a)
        rp = (rot.get_width() / 2 + rx, rot.get_height() / 2 + ry)
        native, rbb = to_native(rot)
        name = f"botin_{ang}.png"
        pygame.image.save(native, os.path.join(OUT_DIR, name))
        frames[str(ang)] = {"file": name, "size": list(native.get_size()),
                            "pivot": [round(v, 2) for v in native_point(rp, rbb)]}
    meta_out["boot"] = {"angles": BOOT_ANGLES, "frames": frames}
    return pivot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depurar", action="store_true")
    args = ap.parse_args()
    pygame.init()
    pygame.display.set_mode((8, 8))
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {"source_px": SOURCE_PX, "heads": {}}
    boot_pivot_src = {}
    for cid in [BOOT_FROM] + [c for c in IDS if c != BOOT_FROM]:
        path = os.path.join(SRC_DIR, f"{cid}.webp")
        if not os.path.isfile(path):
            print(f"falta {path}", file=sys.stderr)
            continue
        src = pygame.image.load(path).convert_alpha()
        bm = boot_mask(src, cid)
        head = largest_part(apply_mask(src, bm, keep=False))
        boot = largest_part(apply_mask(src, bm, keep=True))
        head_px, hbb = to_native(head)
        pygame.image.save(head_px, os.path.join(OUT_DIR, f"{cid}.png"))
        if cid == BOOT_FROM:
            boot_pivot_src = boot_frames(boot, meta)
        # dónde queda el tobillo de SU botín respecto de su cabeza (composición original)
        bbb = boot.get_bounding_rect(128)
        pivot = (bbb.right - bbb.w * 0.28, bbb.top + bbb.h * 0.12)
        w, h = head_px.get_size()
        meta["heads"][cid] = {"file": f"{cid}.png", "size": [w, h],
                              "anchor": [round(w / 2, 2), HEAD_ANCHOR_FROM_TOP],
                              "boot_pivot": [round(v, 2) for v in native_point(pivot, hbb)]}
        if args.depurar:
            dbg = src.copy()
            tint = bm.to_surface(setcolor=(255, 0, 0, 90), unsetcolor=(0, 0, 0, 0))
            dbg.blit(tint, (0, 0))
            pygame.image.save(dbg, os.path.join(OUT_DIR, f"_debug_{cid}.png"))
        print(f"{cid}: cabeza {head_px.get_size()}")
    with open(os.path.join(OUT_DIR, "sprites.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print("listo:", OUT_DIR, "- tobillo del botín (original):", boot_pivot_src)


if __name__ == "__main__":
    main()
