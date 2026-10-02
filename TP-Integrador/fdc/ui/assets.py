"""Recursos de la interfaz: fuentes, textos en caché y reemplazos por archivo.

Los gráficos se generan por código, pero antes de generar cada uno se busca
un archivo equivalente en assets/ (ver README, "Reemplazar gráficos y
sonidos"). Así se pueden cambiar por ilustraciones propias sin tocar la lógica.
"""
import logging
import os

import pygame

from ..config import ASSET_OVERRIDE_DIR
from . import palette, pixelfont

log = logging.getLogger("fdc.assets")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OVERRIDE_ROOT = os.path.join(ROOT, ASSET_OVERRIDE_DIR)

_texts = {}
TEXT_CACHE_LIMIT = 600      # textos dibujados que se guardan para no volver a generarlos
POINTS_PER_SCALE = 8.0      # "tamaño" en puntos que equivale a escala 1 de la fuente pixel art
TITLE_SHADOW_DARKEN = 90    # cuánto más oscura que el color del título es su sombra


def clear_caches():
    """Se llama al cerrar pygame: las superficies en caché dejan de ser válidas."""
    _texts.clear()
    pixelfont._cache.clear()


def scale_for(size):
    """Traduce el "tamaño" histórico en puntos a la escala de la fuente pixel art."""
    return max(1, int(round(size / POINTS_PER_SCALE)))


def text(txt, size, color=palette.WHITE, outline=palette.INK, outline_px=None,
         kind="ui", shadow=False):
    """Texto en la fuente pixel art propia (nítido, estilo retro)."""
    sc = scale_for(size)
    sh = None
    if shadow:
        sh = tuple(max(0, c - TITLE_SHADOW_DARKEN) for c in color) if kind == "title" else palette.INK
    return pixelfont.render(txt, sc, color, outline=outline, shadow=sh)


def draw_text(surf, txt, size, pos, color=palette.WHITE, anchor="center", **kw):
    img = text(txt, size, color, **kw)
    r = img.get_rect()
    setattr(r, anchor, (round(pos[0]), round(pos[1])))
    surf.blit(img, r)
    return r


def text_width(txt, size):
    return pixelfont.text_width(txt, scale_for(size))


def wrap(txt, size, width, kind="ui"):
    """Parte un texto en líneas que entren en 'width' píxeles."""
    words, lines, cur = txt.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if text_width(test, size) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def override_path(*parts):
    path = os.path.join(OVERRIDE_ROOT, *parts)
    return path if os.path.isfile(path) else None


def load_override_image(*parts):
    """Imagen propia que reemplaza a la generada, si existe."""
    path = override_path(*parts)
    if not path:
        return None
    try:
        return pygame.image.load(path).convert_alpha()
    except pygame.error as exc:
        log.warning("no se pudo cargar %s: %s", path, exc)
        return None
