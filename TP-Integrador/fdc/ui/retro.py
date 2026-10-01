"""Utilidades de dibujo retro: píxeles nítidos, paneles con bisel y botones.

El mundo se dibuja con "píxeles de arte" de PX = 2 píxeles lógicos: los
sprites y el fondo se generan a resolución nativa y se agrandan x2 sin
suavizado.
"""
import pygame

from . import palette as C

PX = 2


def scale_px(surf, k=PX):
    return pygame.transform.scale(surf, (surf.get_width() * k, surf.get_height() * k))


def snap(v, k=PX):
    return int(round(v / k)) * k


def pixelize(surf, native_w, alpha_cut=110):
    """Reduce una ilustración suave a pixel art nativo (alfa binario)."""
    w, h = surf.get_size()
    nh = max(1, round(h * native_w / w))
    small = pygame.transform.smoothscale(surf, (native_w, nh))
    out = pygame.Surface((native_w, nh), pygame.SRCALPHA)
    for y in range(nh):
        for x in range(native_w):
            c = small.get_at((x, y))
            if c.a >= alpha_cut:
                k = 255.0 / c.a
                out.set_at((x, y), (min(255, int(c.r * k)), min(255, int(c.g * k)),
                                    min(255, int(c.b * k)), 255))
    return out


def outline_native(surf, color, width=1):
    """Contorno exterior de 'width' píxeles (en la misma resolución)."""
    w, h = surf.get_size()
    out = pygame.Surface((w + 2 * width, h + 2 * width), pygame.SRCALPHA)
    sil = pygame.mask.from_surface(surf, 20).to_surface(setcolor=(*color[:3], 255), unsetcolor=(0, 0, 0, 0))
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx or dy:
                out.blit(sil, (width + dx, width + dy))
    out.blit(surf, (width, width))
    return out


def dither_ellipse(w, h, color=(0, 0, 0), alpha=90):
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
    light = light or tuple(min(255, c + 45) for c in face)
    dark = dark or tuple(max(0, c - 45) for c in face)
    if shadow:
        sh = pygame.Surface(rect.size, pygame.SRCALPHA)
        sh.fill((0, 0, 0, 60))
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
    sh.fill((0, 0, 0, 70))
    surf.blit(sh, rect.move(3 * PX, 3 * PX))
    if alpha is not None:
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        layer.fill((*face, alpha))
        surf.blit(layer, rect)
    else:
        pygame.draw.rect(surf, face, rect)
    pygame.draw.rect(surf, border, rect, 2 * PX)
    inner = rect.inflate(-5 * PX, -5 * PX)
    pygame.draw.rect(surf, tuple(max(0, c - 28) for c in face), inner, PX)
    return rect.inflate(-8 * PX, -8 * PX)
