"""Turns the original sprites (assets/originals/<id>.webp) into the game ones.

Each original has the head (with the shirt collar) and a boot stuck at the
bottom right. This script:
  1. finds the boot (dark grey core in the bottom right zone), wraps it
     with its outline and separates it from the head;
  2. reduces both to native pixel art resolution (1 native pixel is about
     one cell of the original drawing), with binary alpha and clean
     colours;
  3. saves assets/characters/<id>.png (head looking to the LEFT, like the
     original), the frames of the rotated boot
     (assets/characters/boot_<angle>.png, rotated at high resolution before
     reducing them) and assets/characters/sprites.json with the centre of
     each head and the turning point (ankle) of the boot.

Usage (from the project root):
    .venv/bin/python tools/import_sprites.py
    .venv/bin/python tools/import_sprites.py --debug   # saves check images
"""
import argparse
import json
import math
import os
import sys

import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "assets", "originals")
OUT_DIR = os.path.join(ROOT, "assets", "characters")
IDS = ("messi", "maradona", "pele", "cr7", "henry", "neymar", "mbappe")
BOOT_FROM = "pele"
# Original pixels per native pixel (head of about 43 native px).
SOURCE_PX = 18.6
# Degrees of the boot frames; + turns the tip backwards.
BOOT_ANGLES = list(range(30, -121, -10))
HEAD_ANCHOR_FROM_TOP = 21.5   # skull centre, from the hair (native px)
OUTLINE = (22, 18, 20)    # colour of the outline (almost black)
OPAQUE = 255              # alpha of an opaque pixel (and top channel value)
WHITE = (255, 255, 255)   # white (to build masks)
CUT_BACK = 60             # px: the cut line starts a bit left of point A...
CUT_REACH = 4000          # ...and the boot zone goes "forever" right and down
MASK_THRESHOLD = 128      # minimum opacity of a pixel of the drawing
MIN_PART = 50             # px: smaller loose parts do not count (stains)
ALPHA_CUT = 120           # when reducing, less opaque pixels become clear
DARK_LIMIT = 58           # darker colours become outline
COLOR_STEP = 8            # colours are rounded by 8 (cleaner palette)
EDGE_LIGHT = 70           # an edge lighter than this gets an outline
# Ankle: at 28 % of the width from the right and 12 % of the height from
# the top.
ANKLE = (0.28, 0.12)
HIDDEN_WINDOW = (8, 8)    # minimum window: pygame needs it for convert_alpha
DEBUG_TINT = (255, 0, 0, 90)   # translucent red: boot zone in --debug images
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))   # 4 neighbours (dx, dy)

# Cut line between the collar and the laces of the boot, in coordinates of
# the original: everything BELOW the line A-B (and right of A) is boot. They
# were chosen looking at the --debug grid; if a sprite changes, its line
# must be adjusted.
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
    """Half plane below the cut line, limited to the boot zone."""
    w, h = src.get_size()
    (ax, ay), (bx, by) = CUTS[cid]
    k = (by - ay) / (bx - ax)
    far, back = CUT_REACH, CUT_BACK
    poly = [(ax - back, ay - k * back), (bx + far, by + k * far),
            (bx + far, h + far), (ax - back, h + far)]
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(s, WHITE, poly)
    return pygame.mask.from_surface(s, MASK_THRESHOLD)


def apply_mask(src, mask, keep=True):
    """Copy of src with alpha 0 outside (keep=True) or inside (keep=False)
    the mask."""
    m = mask if keep else _inverted(mask)
    cut = m.to_surface(setcolor=(*WHITE, OPAQUE), unsetcolor=(*WHITE, 0))
    out = src.copy()
    out.blit(cut, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def _inverted(mask):
    m = mask.copy()
    m.invert()
    return m


def largest_part(surf):
    """Only the biggest connected part of the drawing."""
    m = pygame.mask.from_surface(surf, MASK_THRESHOLD)
    comps = m.connected_components(MIN_PART)
    if not comps:
        return surf
    return apply_mask(surf, max(comps, key=lambda c: c.count()))


def _clean_color(c):
    """Undoes the premultiplied edge; near black becomes outline and the
    rest is rounded to the palette."""
    k = float(OPAQUE) / c.a
    r, g, b = (min(OPAQUE, int(v * k)) for v in (c.r, c.g, c.b))
    if max(r, g, b) < DARK_LIMIT:
        return OUTLINE
    return tuple(min(OPAQUE, (v + COLOR_STEP // 2) // COLOR_STEP * COLOR_STEP)
                 for v in (r, g, b))


def to_native(surf, bb=None):
    """Crops, reduces and cleans: binary alpha, quantized colours, closed
    outline.

    Returns (native surface, cropped rectangle in original coordinates).
    """
    bb = bb or surf.get_bounding_rect(MASK_THRESHOLD)
    crop = surf.subsurface(bb).copy()
    size = (max(1, round(bb.w / SOURCE_PX)), max(1, round(bb.h / SOURCE_PX)))
    small = pygame.transform.smoothscale(crop, size)
    out, solid = _binary(small)
    _close_outline(out, solid)
    return out, bb


def _binary(small):
    """Copy with a margin of 1, binary alpha and clean colours; also the
    set of solid pixels."""
    w, h = small.get_size()
    out = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    solid = set()
    for y in range(h):
        for x in range(w):
            c = small.get_at((x, y))
            if c.a >= ALPHA_CUT:
                out.set_at((x + 1, y + 1), (*_clean_color(c), OPAQUE))
                solid.add((x + 1, y + 1))
    return out, solid


def _close_outline(out, solid):
    """1 native pixel outline where the edge was left without a dark line."""
    w, h = out.get_size()
    for (x, y) in list(solid):
        for dx, dy in NEIGHBOURS:
            n = (x + dx, y + dy)
            if n in solid:
                continue
            c = out.get_at((x, y))
            inside = 0 <= n[0] < w and 0 <= n[1] < h
            if max(c.r, c.g, c.b) > EDGE_LIGHT and inside:
                out.set_at(n, (*OUTLINE, OPAQUE))


def native_point(pt, bb):
    """Point of the original -> coordinates of the cropped native sprite
    (with a margin of 1)."""
    return ((pt[0] - bb.left) / SOURCE_PX + 1, (pt[1] - bb.top) / SOURCE_PX + 1)


def ankle(bb):
    """Ankle: top right of the boot (where the leg would go in)."""
    share_x, share_y = ANKLE
    return bb.right - bb.w * share_x, bb.top + bb.h * share_y


def _padded(boot, bb):
    """The boot on a big canvas (room to rotate) and the margin used."""
    crop = boot.subsurface(bb).copy()
    pad = int(math.hypot(bb.w, bb.h))
    big = pygame.Surface((bb.w + 2 * pad, bb.h + 2 * pad), pygame.SRCALPHA)
    big.blit(crop, (pad, pad))
    return big, pad


def _rotated_pivot(big, rot, pv, ang):
    """Where the pivot ends up inside the rotated image."""
    cx, cy = big.get_width() / 2, big.get_height() / 2
    vx, vy = pv[0] - cx, pv[1] - cy
    a = math.radians(ang)
    rx = vx * math.cos(a) + vy * math.sin(a)
    ry = -vx * math.sin(a) + vy * math.cos(a)
    return rot.get_width() / 2 + rx, rot.get_height() / 2 + ry


def _boot_frame(big, pv, ang):
    """Saves the boot rotated ang degrees; returns its metadata."""
    rot = pygame.transform.rotozoom(big, ang, 1.0)
    rp = _rotated_pivot(big, rot, pv, ang)
    native, rbb = to_native(rot)
    name = f"boot_{ang}.png"
    pygame.image.save(native, os.path.join(OUT_DIR, name))
    return {"file": name, "size": list(native.get_size()),
            "pivot": [round(v, 2) for v in native_point(rp, rbb)]}


def boot_frames(boot, meta_out):
    """Rotates the boot at high resolution around the ankle and reduces
    each frame."""
    bb = boot.get_bounding_rect(MASK_THRESHOLD)
    pivot = ankle(bb)
    big, pad = _padded(boot, bb)
    pv = (pivot[0] - bb.left + pad, pivot[1] - bb.top + pad)
    frames = {str(ang): _boot_frame(big, pv, ang) for ang in BOOT_ANGLES}
    meta_out["boot"] = {"angles": BOOT_ANGLES, "frames": frames}
    return pivot


def _import_character(cid, meta, debug):
    """Head (and boot frames for BOOT_FROM) of one character. Returns the
    original boot pivot of BOOT_FROM, or None."""
    path = os.path.join(SRC_DIR, f"{cid}.webp")
    src = pygame.image.load(path).convert_alpha()
    bm = boot_mask(src, cid)
    head = largest_part(apply_mask(src, bm, keep=False))
    boot = largest_part(apply_mask(src, bm, keep=True))
    head_px, hbb = to_native(head)
    pygame.image.save(head_px, os.path.join(OUT_DIR, f"{cid}.png"))
    boot_pivot = boot_frames(boot, meta) if cid == BOOT_FROM else None
    meta["heads"][cid] = _head_meta(cid, head_px, hbb, boot)
    if debug:
        _save_debug(src, bm, cid)
    print(f"{cid}: cabeza {head_px.get_size()}")
    return boot_pivot


def _head_meta(cid, head_px, hbb, boot):
    """Size and anchor of the head, and where the ankle of ITS boot is
    from it (original composition)."""
    pivot = ankle(boot.get_bounding_rect(MASK_THRESHOLD))
    w, h = head_px.get_size()
    return {"file": f"{cid}.png", "size": [w, h],
            "anchor": [round(w / 2, 2), HEAD_ANCHOR_FROM_TOP],
            "boot_pivot": [round(v, 2) for v in native_point(pivot, hbb)]}


def _save_debug(src, bm, cid):
    dbg = src.copy()
    dbg.blit(bm.to_surface(setcolor=DEBUG_TINT, unsetcolor=(0, 0, 0, 0)),
             (0, 0))
    pygame.image.save(dbg, os.path.join(OUT_DIR, f"_debug_{cid}.png"))


def main():
    """Imports every character found in assets/originals."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode(HIDDEN_WINDOW)
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {"source_px": SOURCE_PX, "heads": {}}
    boot_pivot_src = _import_all(meta, args.debug)
    _save_meta(meta)
    print("listo:", OUT_DIR, "- tobillo del botín (original):",
          boot_pivot_src)


def _save_meta(meta):
    path = os.path.join(OUT_DIR, "sprites.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)


def _import_all(meta, debug):
    """Every character (the boot one first); returns its boot pivot."""
    boot_pivot_src = {}
    for cid in [BOOT_FROM] + [c for c in IDS if c != BOOT_FROM]:
        if not os.path.isfile(os.path.join(SRC_DIR, f"{cid}.webp")):
            print(f"falta {cid}.webp en {SRC_DIR}", file=sys.stderr)
            continue
        boot_pivot_src = (_import_character(cid, meta, debug)
                          or boot_pivot_src)
    return boot_pivot_src


if __name__ == "__main__":
    main()
