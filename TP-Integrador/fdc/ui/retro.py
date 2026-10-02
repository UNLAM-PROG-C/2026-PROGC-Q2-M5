"""Utilidades de dibujo retro: píxeles nítidos, paneles con bisel y botones.

El mundo se dibuja con "píxeles de arte" de PX = 2 píxeles lógicos: los
sprites y el fondo se generan a resolución nativa y se agrandan x2 sin
suavizado.
"""
import pygame

from . import palette as C

PX = 2                  # píxeles lógicos por "píxel de arte" (todo el pixel art se agranda x2)
ALPHA_CUT = 110         # al pixelar, los píxeles con menos opacidad que esto quedan transparentes
MASK_THRESHOLD = 20     # opacidad mínima de un píxel para que cuente en el contorno
DITHER_ALPHA = 90       # opacidad de los puntos de la sombra con trama
BEVEL_LIGHT = 45        # cuánto más clara es la luz del bisel (arriba e izquierda)
BEVEL_DARK = 45         # cuánto más oscura es la sombra del bisel (abajo y derecha)
BOX_SHADOW_ALPHA = 60   # opacidad de la sombra de una caja con bisel
PANEL_SHADOW_ALPHA = 70  # opacidad de la sombra de un panel
PANEL_SHADOW_OFFSET = 3  # píxeles de arte que se corre la sombra de un panel
PANEL_INNER_LINE = 5     # píxeles de arte desde el borde hasta la línea interior del panel
PANEL_INNER_DARKEN = 28  # cuánto más oscura que el fondo es esa línea interior
PANEL_PADDING = 8        # píxeles de arte desde el borde hasta el área útil del panel


def scale_px(surf, k=PX):
    return pygame.transform.scale(surf, (surf.get_width() * k, surf.get_height() * k))


def snap(v, k=PX):
    return int(round(v / k)) * k


def pixelize(surf, native_w, alpha_cut=ALPHA_CUT):
    """Reduce una ilustración suave a pixel art nativo (alfa binario)."""
    w, h = surf.get_size()
    nh = max(1, round(h * native_w / w))
    small = pygame.transform.smoothscale(surf, (native_w, nh))
    out = pygame.Surface((native_w, nh), pygame.SRCALPHA)
    for y in range(nh):
        for x in range(native_w):
            c = small.get_at((x, y))
            if c.a >= alpha_cut:
                k = C.MAX_CHANNEL / c.a          # deshace la mezcla con el fondo transparente
                out.set_at((x, y), (min(C.MAX_CHANNEL, int(c.r * k)), min(C.MAX_CHANNEL, int(c.g * k)),
                                    min(C.MAX_CHANNEL, int(c.b * k)), C.OPAQUE))
    return out


def outline_native(surf, color, width=1):
    """Contorno exterior de 'width' píxeles (en la misma resolución)."""
    w, h = surf.get_size()
    out = pygame.Surface((w + 2 * width, h + 2 * width), pygame.SRCALPHA)
    rgb = tuple(color)[:C.RGB_CHANNELS]
    sil = pygame.mask.from_surface(surf, MASK_THRESHOLD).to_surface(setcolor=(*rgb, C.OPAQUE),
                                                                    unsetcolor=(0, 0, 0, 0))
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx or dy:
                out.blit(sil, (width + dx, width + dy))
    out.blit(surf, (width, width))
    return out


def dither_ellipse(w, h, color=C.SHADOW, alpha=DITHER_ALPHA):
    """Sombra con trama de tablero de ajedrez (estilo 16 bits)."""
    s = pygame.Surface((max(2, w), max(2, h)), pygame.SRCALPHA)
    rx, ry = w / 2, h / 2
    for y in range(h):
        for x in range(w):
            if ((x - rx + 0.5) / rx) ** 2 + ((y - ry + 0.5) / ry) ** 2 <= 1 and (x + y) % 2 == 0:
                s.set_at((x, y), (*color, alpha))
    return s


def bevel_box(surf, rect, face, border=C.INK, light=None, dark=None, shadow=True, b=PX):
    """Caja retro: borde oscuro, luz arriba/izquierda, sombra abajo/derecha."""
    rect = pygame.Rect(rect)
    light = light or tuple(min(C.MAX_CHANNEL, c + BEVEL_LIGHT) for c in face)
    dark = dark or tuple(max(0, c - BEVEL_DARK) for c in face)
    if shadow:
        sh = pygame.Surface(rect.size, pygame.SRCALPHA)
        sh.fill((*C.SHADOW, BOX_SHADOW_ALPHA))
        surf.blit(sh, rect.move(2 * b, 2 * b))
    pygame.draw.rect(surf, border, rect)
    inner = rect.inflate(-2 * b, -2 * b)
    pygame.draw.rect(surf, face, inner)
    pygame.draw.rect(surf, light, (inner.left, inner.top, inner.width, b))
    pygame.draw.rect(surf, light, (inner.left, inner.top, b, inner.height))
    pygame.draw.rect(surf, dark, (inner.left, inner.bottom - b, inner.width, b))
    pygame.draw.rect(surf, dark, (inner.right - b, inner.top, b, inner.height))
    return inner


def panel(surf, rect, face=C.CREAM, border=C.INK, alpha=None):
    """Panel de diálogo: doble borde clásico."""
    rect = pygame.Rect(rect)
    sh = pygame.Surface(rect.size, pygame.SRCALPHA)
    sh.fill((*C.SHADOW, PANEL_SHADOW_ALPHA))
    surf.blit(sh, rect.move(PANEL_SHADOW_OFFSET * PX, PANEL_SHADOW_OFFSET * PX))
    if alpha is not None:
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        layer.fill((*face, alpha))
        surf.blit(layer, rect)
    else:
        pygame.draw.rect(surf, face, rect)
    pygame.draw.rect(surf, border, rect, 2 * PX)
    inner = rect.inflate(-PANEL_INNER_LINE * PX, -PANEL_INNER_LINE * PX)
    pygame.draw.rect(surf, tuple(max(0, c - PANEL_INNER_DARKEN) for c in face), inner, PX)
    return rect.inflate(-PANEL_PADDING * PX, -PANEL_PADDING * PX)
